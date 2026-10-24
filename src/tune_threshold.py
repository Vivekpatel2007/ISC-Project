"""
Validation-Based Threshold Tuning
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

Features:
- Evaluates predicted probabilities strictly on the VALIDATION split.
- Sweeps decision thresholds across [0.05, 0.95] in steps of 0.01.
- Evaluates Balanced Accuracy, Youden's J index, Sensitivity, Specificity, and Macro F1.
- Analyzes clinical trade-offs between False Positives (overdiagnosis) and False Negatives (missed pneumonia).
- Saves threshold settings to results/prediction_threshold.json.
- Updates checkpoint metadata so the .pth file contains the tuned threshold for standalone inference.
- Plots metric curves across thresholds and saves to results/threshold_tuning_curve.png.
"""

import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "model_data"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "densenet121_pneumonia_best.pth"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"


def tune_threshold(model_path: Path, data_dir: Path, results_dir: Path, criterion_name: str = "balanced_accuracy"):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 70)
    print("VALIDATION THRESHOLD TUNING")
    print("=" * 70)
    print(f"Model path:    {model_path.resolve()}")
    print(f"Validation data: {data_dir.resolve() / 'val'}")
    print(f"Selection criteria: {criterion_name}")

    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    class_names = checkpoint.get("class_names", ["NORMAL", "PNEUMONIA"])
    image_size = checkpoint.get("image_size", 224)
    norm = checkpoint.get("normalization", {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]})

    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(norm["mean"], norm["std"]),
    ])

    val_dataset = datasets.ImageFolder(data_dir / "val", transform=transform)
    val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False, num_workers=0)

    # Reconstruct model architecture
    model = models.densenet121(weights=None)
    in_features = model.classifier.in_features
    # Check if classifier has dropout
    if "classifier.1.weight" in checkpoint["model_state_dict"]:
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.2),
            nn.Linear(in_features, len(class_names))
        )
    else:
        model.classifier = nn.Linear(in_features, len(class_names))

    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    all_targets = []
    all_scores = []

    with torch.no_grad():
        for images, labels in val_loader:
            images = images.to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=(device.type == "cuda")):
                logits = model(images)
            probs = torch.softmax(logits.float(), dim=1)[:, 1]
            all_targets.extend(labels.numpy().tolist())
            all_scores.extend(probs.cpu().numpy().tolist())

    y_true = np.array(all_targets)
    scores = np.array(all_scores)
    val_roc_auc = roc_auc_score(y_true, scores)
    print(f"Validation samples: {len(y_true)} (Normal: {sum(y_true == 0)}, Pneumonia: {sum(y_true == 1)})")
    print(f"Validation ROC-AUC: {val_roc_auc:.4f}")

    thresholds = np.arange(0.05, 0.96, 0.01)
    records = []

    best_thresh = 0.50
    best_value = -1.0

    for t in thresholds:
        preds = (scores >= t).astype(int)
        cm = confusion_matrix(y_true, preds, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()

        sens = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        bal_acc = balanced_accuracy_score(y_true, preds)
        macro_f1 = f1_score(y_true, preds, average="macro", zero_division=0)
        youden_j = sens + spec - 1.0

        records.append({
            "threshold": float(t),
            "balanced_accuracy": float(bal_acc),
            "youden_j": float(youden_j),
            "sensitivity": float(sens),
            "specificity": float(spec),
            "macro_f1": float(macro_f1),
            "precision_pneumonia": float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        })

        metric_val = bal_acc if criterion_name == "balanced_accuracy" else youden_j
        if metric_val > best_value:
            best_value = metric_val
            best_thresh = float(t)

    print(f"\nOptimal Validation Threshold: {best_thresh:.2f}")
    best_record = next(r for r in records if abs(r["threshold"] - best_thresh) < 1e-4)
    print(f"  Balanced Accuracy: {best_record['balanced_accuracy']:.4f}")
    print(f"  Sensitivity (Pneumonia Recall): {best_record['sensitivity']:.4f}")
    print(f"  Specificity (Normal Recall):    {best_record['specificity']:.4f}")
    print(f"  Macro F1-Score:                 {best_record['macro_f1']:.4f}")
    print(f"  Youden's J Index:               {best_record['youden_j']:.4f}")

    # Validation confusion matrix at best threshold
    val_preds = (scores >= best_thresh).astype(int)
    cm_best = confusion_matrix(y_true, val_preds, labels=[0, 1])
    print("\nValidation Confusion Matrix at Selected Threshold:")
    print(cm_best)
    print("\nValidation Classification Report:")
    print(classification_report(y_true, val_preds, target_names=class_names, digits=4, zero_division=0))

    # Save threshold json
    settings = {
        "threshold": best_thresh,
        "selection_metric": criterion_name,
        "validation_metric_value": best_value,
        "validation_balanced_accuracy": best_record["balanced_accuracy"],
        "validation_sensitivity": best_record["sensitivity"],
        "validation_specificity": best_record["specificity"],
        "validation_macro_f1": best_record["macro_f1"],
        "validation_roc_auc": float(val_roc_auc),
        "model_file": model_path.name
    }

    thresh_file = results_dir / "prediction_threshold.json"
    with open(thresh_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    print(f"\nSaved threshold configuration to: {thresh_file.resolve()}")

    # Update checkpoint with threshold
    checkpoint["threshold"] = best_thresh
    checkpoint["threshold_metric"] = criterion_name
    checkpoint["threshold_settings"] = settings
    torch.save(checkpoint, model_path)
    print(f"Embedded threshold {best_thresh:.2f} into model checkpoint: {model_path.name}")

    # Plot threshold search curves
    ts = [r["threshold"] for r in records]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(ts, [r["balanced_accuracy"] for r in records], label="Balanced Accuracy", color="blue", lw=2)
    ax.plot(ts, [r["sensitivity"] for r in records], label="Sensitivity (Pneumonia Recall)", color="red", linestyle="--")
    ax.plot(ts, [r["specificity"] for r in records], label="Specificity (Normal Recall)", color="green", linestyle="--")
    ax.plot(ts, [r["macro_f1"] for r in records], label="Macro F1", color="purple", linestyle=":")
    ax.axvline(best_thresh, color="black", linestyle="-.", label=f"Selected Threshold ({best_thresh:.2f})")
    ax.set_title("Validation Threshold Tuning: Diagnostic Metric Trade-Offs")
    ax.set_xlabel("Probability Threshold for PNEUMONIA")
    ax.set_ylabel("Metric Value")
    ax.set_xlim(0.05, 0.95)
    ax.set_ylim(0.0, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left")

    plt.tight_layout()
    plot_file = results_dir / "threshold_tuning_curve.png"
    plt.savefig(plot_file, dpi=150)
    plt.close()
    print(f"Saved threshold tuning plot to: {plot_file.resolve()}")
    return settings


def main():
    parser = argparse.ArgumentParser(description="Tune decision threshold on validation data")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH), help="Path to checkpoint")
    parser.add_argument("--data_dir", type=str, default=str(DEFAULT_DATA_DIR), help="Data directory")
    parser.add_argument("--results_dir", type=str, default=str(DEFAULT_RESULTS_DIR), help="Results directory")
    parser.add_argument("--metric", type=str, default="balanced_accuracy", choices=["balanced_accuracy", "youden_j"])
    args = parser.parse_args()

    tune_threshold(
        model_path=Path(args.model),
        data_dir=Path(args.data_dir),
        results_dir=Path(args.results_dir),
        criterion_name=args.metric
    )


if __name__ == "__main__":
    main()
