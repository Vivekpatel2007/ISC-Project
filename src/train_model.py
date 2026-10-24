"""
Training Pipeline for Pneumonia Detection
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

Features:
- Pretrained DenseNet121 with differential learning rates (backbone vs classifier).
- Conservative, clinically grounded chest X-ray augmentations (applied to training only).
- Consistent ImageNet normalization and grayscale-to-3-channel handling.
- Principled class imbalance handling via inverse-frequency class weighting.
- AdamW optimizer with Cosine Annealing learning rate schedule.
- Mixed precision training (torch.amp) with CUDA acceleration.
- Checkpoint selection based on Validation ROC-AUC / Balanced Accuracy.
- Full inference metadata embedded in saved checkpoint.
- Reproducible seeding and comprehensive metric tracking.
"""

import argparse
import copy
import json
import random
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms
from torchvision.models import DenseNet121_Weights
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    precision_score,
    recall_score,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "train_config.json"


def set_seed(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def load_config(config_path: Path) -> dict:
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # Default fallback configuration
    return {
        "model": {"architecture": "densenet121", "pretrained": True, "drop_rate": 0.2},
        "data": {
            "data_dir": "data/model_data",
            "image_size": 224,
            "batch_size": 16,
            "num_workers": 0,
            "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
            "augmentation": {
                "rotation_degrees": 10,
                "translate": [0.04, 0.04],
                "scale": [0.96, 1.04],
                "brightness_jitter": 0.10,
                "contrast_jitter": 0.10,
                "horizontal_flip_prob": 0.30
            }
        },
        "training": {
            "epochs": 15,
            "learning_rate": 1e-4,
            "backbone_lr_ratio": 0.5,
            "weight_decay": 0.01,
            "optimizer": "AdamW",
            "scheduler": "CosineAnnealingLR",
            "scheduler_t_max": 15,
            "scheduler_eta_min": 1e-6,
            "mixed_precision": True,
            "early_stopping": {"enabled": True, "patience": 5, "monitor_metric": "val_roc_auc", "mode": "max"},
            "seed": 42
        },
        "paths": {
            "model_save_path": "models/densenet121_pneumonia_best.pth",
            "history_save_path": "results/training_history.json"
        }
    }


def get_data_transforms(cfg: dict):
    img_size = cfg["data"]["image_size"]
    norm_mean = cfg["data"]["normalization"]["mean"]
    norm_std = cfg["data"]["normalization"]["std"]
    aug_cfg = cfg["data"].get("augmentation", {})

    train_transforms = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((img_size, img_size)),
        transforms.RandomRotation(degrees=aug_cfg.get("rotation_degrees", 10)),
        transforms.RandomAffine(
            degrees=0,
            translate=tuple(aug_cfg.get("translate", [0.04, 0.04])),
            scale=tuple(aug_cfg.get("scale", [0.96, 1.04]))
        ),
        transforms.ColorJitter(
            brightness=aug_cfg.get("brightness_jitter", 0.10),
            contrast=aug_cfg.get("contrast_jitter", 0.10)
        ),
        transforms.RandomHorizontalFlip(p=aug_cfg.get("horizontal_flip_prob", 0.30)),
        transforms.ToTensor(),
        transforms.Normalize(mean=norm_mean, std=norm_std),
    ])

    eval_transforms = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=norm_mean, std=norm_std),
    ])

    return train_transforms, eval_transforms


def build_model(cfg: dict, num_classes: int = 2) -> nn.Module:
    model_cfg = cfg["model"]
    weights = DenseNet121_Weights.DEFAULT if model_cfg.get("pretrained", True) else None
    model = models.densenet121(weights=weights)

    in_features = model.classifier.in_features
    drop_rate = model_cfg.get("drop_rate", 0.2)

    if drop_rate > 0:
        model.classifier = nn.Sequential(
            nn.Dropout(p=drop_rate),
            nn.Linear(in_features, num_classes)
        )
    else:
        model.classifier = nn.Linear(in_features, num_classes)

    return model


def compute_class_weights(dataset, device):
    targets = np.array(dataset.targets)
    classes = np.unique(targets)
    counts = np.bincount(targets, minlength=len(classes))
    total = len(targets)
    weights = total / (len(classes) * counts.astype(np.float32))
    return torch.tensor(weights, dtype=torch.float32, device=device), counts


def train_epoch(model, loader, criterion, optimizer, scaler, device, use_amp):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0

    for inputs, labels in loader:
        inputs = inputs.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)

        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
            logits = model(inputs)
            loss = criterion(logits, labels)

        if use_amp and scaler is not None:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()

        batch_size = labels.size(0)
        running_loss += loss.item() * batch_size
        preds = logits.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total += batch_size

    epoch_loss = running_loss / total
    epoch_acc = correct / total
    return epoch_loss, epoch_acc


def evaluate(model, loader, criterion, device, use_amp):
    model.eval()
    running_loss = 0.0
    all_preds = []
    all_probs = []
    all_targets = []

    with torch.no_grad():
        for inputs, labels in loader:
            inputs = inputs.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=use_amp):
                logits = model(inputs)
                loss = criterion(logits, labels)

            probs = torch.softmax(logits.float(), dim=1)
            preds = logits.argmax(dim=1)

            running_loss += loss.item() * labels.size(0)
            all_preds.extend(preds.cpu().numpy().tolist())
            all_probs.extend(probs[:, 1].cpu().numpy().tolist())
            all_targets.extend(labels.cpu().numpy().tolist())

    y_true = np.array(all_targets)
    y_pred = np.array(all_preds)
    y_prob = np.array(all_probs)

    total = len(y_true)
    loss = running_loss / total
    acc = float(np.mean(y_true == y_pred))
    bal_acc = float(balanced_accuracy_score(y_true, y_pred))

    try:
        roc_auc = float(roc_auc_score(y_true, y_prob))
    except ValueError:
        roc_auc = 0.5

    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    return {
        "loss": loss,
        "accuracy": acc,
        "balanced_accuracy": bal_acc,
        "roc_auc": roc_auc,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "y_true": y_true,
        "y_pred": y_pred,
        "y_prob": y_prob
    }


def main():
    parser = argparse.ArgumentParser(description="Train Pneumonia Detection Model")
    parser.add_argument("--config", type=str, default=str(CONFIG_PATH), help="Path to config JSON")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs")
    parser.add_argument("--batch_size", type=int, default=None, help="Override batch size")
    parser.add_argument("--lr", type=float, default=None, help="Override learning rate")
    parser.add_argument("--save_path", type=str, default=None, help="Override checkpoint save path")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    if args.epochs is not None: cfg["training"]["epochs"] = args.epochs
    if args.batch_size is not None: cfg["data"]["batch_size"] = args.batch_size
    if args.lr is not None: cfg["training"]["learning_rate"] = args.lr
    if args.save_path is not None: cfg["paths"]["model_save_path"] = args.save_path

    set_seed(cfg["training"]["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 70)
    print("PNEUMONIA DETECTION: IMPROVED TRAINING PIPELINE")
    print("=" * 70)
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")

    data_dir = PROJECT_ROOT / cfg["data"]["data_dir"]
    train_dir = data_dir / "train"
    val_dir = data_dir / "val"
    test_dir = data_dir / "test"

    train_tf, eval_tf = get_data_transforms(cfg)
    train_ds = datasets.ImageFolder(train_dir, transform=train_tf)
    val_ds = datasets.ImageFolder(val_dir, transform=eval_tf)
    test_ds = datasets.ImageFolder(test_dir, transform=eval_tf)

    class_names = train_ds.classes
    class_to_idx = train_ds.class_to_idx
    print(f"Classes: {class_to_idx}")
    print(f"Images: Train={len(train_ds)}, Val={len(val_ds)}, Test={len(test_ds)}")

    batch_size = cfg["data"]["batch_size"]
    num_workers = cfg["data"]["num_workers"]
    pin_mem = (device.type == "cuda")

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=pin_mem)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=pin_mem)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=pin_mem)

    # Class weights for loss
    class_weights, counts = compute_class_weights(train_ds, device)
    print(f"Training counts: {dict(zip(class_names, counts.tolist()))}")
    print(f"Computed loss weights: {dict(zip(class_names, [round(w.item(), 3) for w in class_weights]))}")
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    # Model architecture
    model = build_model(cfg, num_classes=len(class_names)).to(device)

    # Differential learning rate: lower on backbone, higher on classifier
    backbone_ratio = cfg["training"].get("backbone_lr_ratio", 0.5)
    base_lr = cfg["training"]["learning_rate"]
    weight_decay = cfg["training"].get("weight_decay", 0.01)

    classifier_params = list(model.classifier.parameters())
    classifier_ids = list(map(id, classifier_params))
    backbone_params = [p for p in model.parameters() if id(p) not in classifier_ids]

    optimizer = torch.optim.AdamW([
        {"params": backbone_params, "lr": base_lr * backbone_ratio},
        {"params": classifier_params, "lr": base_lr}
    ], weight_decay=weight_decay)

    epochs = cfg["training"]["epochs"]
    scheduler_name = cfg["training"].get("scheduler", "CosineAnnealingLR")
    if scheduler_name == "CosineAnnealingLR":
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer,
            T_max=cfg["training"].get("scheduler_t_max", epochs),
            eta_min=float(cfg["training"].get("scheduler_eta_min", 1e-6))
        )
    else:
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="max", factor=0.5, patience=2)

    use_amp = cfg["training"].get("mixed_precision", True) and (device.type == "cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    # Early stopping and checkpoint tracking
    es_cfg = cfg["training"].get("early_stopping", {})
    es_enabled = es_cfg.get("enabled", True)
    patience = es_cfg.get("patience", 5)
    monitor = es_cfg.get("monitor_metric", "val_roc_auc")
    mode = es_cfg.get("mode", "max")

    best_score = -float("inf") if mode == "max" else float("inf")
    best_epoch = 0
    best_state_dict = None
    best_metrics = {}
    wait = 0

    history = {
        "train_loss": [], "train_acc": [],
        "val_loss": [], "val_acc": [],
        "val_balanced_acc": [], "val_roc_auc": [],
        "val_macro_f1": [], "lr": []
    }

    model_save_path = PROJECT_ROOT / cfg["paths"]["model_save_path"]
    model_save_path.parent.mkdir(parents=True, exist_ok=True)
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("\nStarting training loop...")
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        tr_loss, tr_acc = train_epoch(model, train_loader, criterion, optimizer, scaler, device, use_amp)
        val_eval = evaluate(model, val_loader, criterion, device, use_amp)

        current_lr = optimizer.param_groups[1]["lr"]
        if isinstance(scheduler, torch.optim.lr_scheduler.CosineAnnealingLR):
            scheduler.step()
        elif isinstance(scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
            scheduler.step(val_eval["roc_auc"])

        history["train_loss"].append(tr_loss)
        history["train_acc"].append(tr_acc)
        history["val_loss"].append(val_eval["loss"])
        history["val_acc"].append(val_eval["accuracy"])
        history["val_balanced_acc"].append(val_eval["balanced_accuracy"])
        history["val_roc_auc"].append(val_eval["roc_auc"])
        history["val_macro_f1"].append(val_eval["macro_f1"])
        history["lr"].append(current_lr)

        elapsed = time.time() - t0
        print(f"Epoch {epoch:02d}/{epochs:02d} [{elapsed:.1f}s] | "
              f"Tr Loss: {tr_loss:.4f} Acc: {tr_acc:.4f} | "
              f"Val Loss: {val_eval['loss']:.4f} Acc: {val_eval['accuracy']:.4f} "
              f"BalAcc: {val_eval['balanced_accuracy']:.4f} AUC: {val_eval['roc_auc']:.4f} | LR: {current_lr:.2e}")

        # Checkpoint evaluation based on monitor metric
        current_metric = val_eval["roc_auc"] if monitor == "val_roc_auc" else (
            val_eval["balanced_accuracy"] if monitor == "val_balanced_acc" else val_eval["loss"]
        )

        improved = (current_metric > best_score) if mode == "max" else (current_metric < best_score)
        if improved:
            best_score = current_metric
            best_epoch = epoch
            best_state_dict = copy.deepcopy(model.state_dict())
            best_metrics = {
                "epoch": epoch,
                "val_loss": val_eval["loss"],
                "val_accuracy": val_eval["accuracy"],
                "val_balanced_accuracy": val_eval["balanced_accuracy"],
                "val_roc_auc": val_eval["roc_auc"],
                "val_macro_f1": val_eval["macro_f1"]
            }
            wait = 0

            # Save checkpoint with comprehensive metadata
            checkpoint_payload = {
                "model_state_dict": best_state_dict,
                "architecture": cfg["model"]["architecture"],
                "class_names": class_names,
                "class_to_idx": class_to_idx,
                "image_size": cfg["data"]["image_size"],
                "normalization": cfg["data"]["normalization"],
                "best_epoch": best_epoch,
                "selection_metric": monitor,
                "selection_metric_value": best_score,
                "validation_metrics": best_metrics,
                "training_config": cfg
            }
            torch.save(checkpoint_payload, model_save_path)
            print(f"  --> Saved new best checkpoint at Epoch {epoch} ({monitor}: {best_score:.4f}) -> {model_save_path.name}")
        else:
            wait += 1
            if es_enabled and wait >= patience:
                print(f"\n[Early Stopping] No improvement in {monitor} for {patience} consecutive epochs. Stopping.")
                break

    total_time = (time.time() - start_time) / 60.0
    print("\n" + "=" * 70)
    print(f"Training completed in {total_time:.2f} minutes.")
    print(f"Best Checkpoint: Epoch {best_epoch} ({monitor} = {best_score:.4f})")
    print(f"Model saved to: {model_save_path.resolve()}")
    print("=" * 70)

    # Save history JSON
    history_file = PROJECT_ROOT / cfg["paths"]["history_save_path"]
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    # Plot training curves
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # 1. Loss
    axes[0].plot(history["train_loss"], label="Train Loss", color="blue")
    axes[0].plot(history["val_loss"], label="Val Loss", color="red")
    axes[0].axvline(best_epoch - 1, color="green", linestyle="--", label=f"Best Ep ({best_epoch})")
    axes[0].set_title("Training & Validation Loss")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()

    # 2. Accuracy
    axes[1].plot(history["train_acc"], label="Train Acc", color="blue")
    axes[1].plot(history["val_acc"], label="Val Acc", color="red")
    axes[1].plot(history["val_balanced_acc"], label="Val Balanced Acc", color="orange", linestyle=":")
    axes[1].axvline(best_epoch - 1, color="green", linestyle="--", label=f"Best Ep ({best_epoch})")
    axes[1].set_title("Accuracy Curves")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Accuracy")
    axes[1].legend()

    # 3. ROC-AUC & LR
    ax3 = axes[2]
    ax3.plot(history["val_roc_auc"], label="Val ROC-AUC", color="purple")
    ax3.axvline(best_epoch - 1, color="green", linestyle="--", label=f"Best Ep ({best_epoch})")
    ax3.set_title("Validation ROC-AUC")
    ax3.set_xlabel("Epoch")
    ax3.set_ylabel("ROC-AUC")
    ax3.legend(loc="lower right")

    plt.tight_layout()
    plt.savefig(results_dir / "training_curves_improved.png", dpi=150)
    plt.close()
    print(f"Saved training curves to {results_dir / 'training_curves_improved.png'}")


if __name__ == "__main__":
    main()
