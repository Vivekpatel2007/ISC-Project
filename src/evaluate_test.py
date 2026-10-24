"""
Held-Out Test Set Evaluation
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

Features:
- Evaluates trained DenseNet121 model on the strictly held-out test dataset.
- Uses threshold determined SOLELY from validation data.
- Reports comprehensive metrics:
  * Accuracy, Balanced Accuracy, Macro F1, Weighted F1
  * Per-class Precision, Recall, F1
  * Sensitivity (Pneumonia recall) & Specificity (Normal recall)
  * ROC-AUC and PR-AUC
  * Full confusion matrix (counts & percentages)
- Generates high-resolution confusion matrix plot.
- Exports structured evaluation results to JSON.
- Provides educational clinical error analysis (False Positives vs False Negatives).
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
    accuracy_score,
    average_precision_score,
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
DEFAULT_THRESHOLD_PATH = PROJECT_ROOT / "results" / "prediction_threshold.json"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"


def evaluate_test(model_path: Path, data_dir: Path, threshold_path: Path, results_dir: Path, custom_threshold: float = None):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("=" * 70)
    print("HELD-OUT TEST SET EVALUATION")
    print("=" * 70)
    print(f"Model:          {model_path.resolve()}")
    print(f"Test directory: {data_dir.resolve() / 'test'}")

    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    class_names = checkpoint.get("class_names", ["NORMAL", "PNEUMONIA"])
    image_size = checkpoint.get("image_size", 224)
    norm = checkpoint.get("normalization", {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]})

    # Determine threshold
    if custom_threshold is not None:
        threshold = custom_threshold
        thresh_source = "CLI override"
    elif "threshold" in checkpoint:
        threshold = float(checkpoint["threshold"])
        thresh_source = f"checkpoint metadata ({checkpoint.get('threshold_metric', 'validation')})"
    elif threshold_path.exists():
        with open(threshold_path, "r", encoding="utf-8") as f:
            t_data = json.load(f)
            threshold = float(t_data.get("threshold", 0.50))
            thresh_source = f"results/prediction_threshold.json ({t_data.get('selection_metric', 'validation')})"
    else:
        threshold = 0.50
        thresh_source = "default 0.50"

    print(f"Decision Threshold: {threshold:.2f} (Source: {thresh_source})")

    # Transform
    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(norm["mean"], norm["std"]),
    ])

    test_dataset = datasets.ImageFolder(data_dir / "test", transform=transform)
    test_loader = DataLoader(test_dataset, batch_size=16, shuffle=False, num_workers=0)

    if test_dataset.class_to_idx != checkpoint.get("class_to_idx", {"NORMAL": 0, "PNEUMONIA": 1}):
        raise ValueError("Test set class mapping does not match checkpoint mapping!")

    # Model reconstruction
    model = models.densenet121(weights=None)
    in_features = model.classifier.in_features
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
    all_paths = [s[0] for s in test_dataset.samples]

    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(device)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=(device.type == "cuda")):
                logits = model(images)
            probs = torch.softmax(logits.float(), dim=1)[:, 1]
            all_targets.extend(labels.numpy().tolist())
            all_scores.extend(probs.cpu().numpy().tolist())

    y_true = np.array(all_targets)
    pneumonia_scores = np.array(all_scores)
    y_pred = (pneumonia_scores >= threshold).astype(int)

    # Calculate metrics
    acc = accuracy_score(y_true, y_pred)
    bal_acc = balanced_accuracy_score(y_true, y_pred)
    roc_auc = roc_auc_score(y_true, pneumonia_scores)
    pr_auc = average_precision_score(y_true, pneumonia_scores)

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0  # Pneumonia recall
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0  # Normal recall

    prec_norm = precision_score(y_true, y_pred, pos_label=0, zero_division=0)
    rec_norm = recall_score(y_true, y_pred, pos_label=0, zero_division=0)
    f1_norm = f1_score(y_true, y_pred, pos_label=0, zero_division=0)

    prec_pneu = precision_score(y_true, y_pred, pos_label=1, zero_division=0)
    rec_pneu = recall_score(y_true, y_pred, pos_label=1, zero_division=0)
    f1_pneu = f1_score(y_true, y_pred, pos_label=1, zero_division=0)

    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)

    # Print summary
    print("\n" + "=" * 70)
    print("TEST SET EVALUATION RESULTS")
    print("=" * 70)
    print(f"Overall Accuracy:       {acc * 100:.2f}%")
    print(f"Balanced Accuracy:      {bal_acc * 100:.2f}%")
    print(f"ROC-AUC:                {roc_auc:.4f}")
    print(f"PR-AUC (Pneumonia):     {pr_auc:.4f}")
    print(f"Sensitivity (Pneu Rec): {sensitivity * 100:.2f}% ({tp}/{tp+fn} detected)")
    print(f"Specificity (Norm Rec): {specificity * 100:.2f}% ({tn}/{tn+fp} correct)")
    print(f"Macro F1-Score:         {macro_f1 * 100:.2f}%")
    print(f"Weighted F1-Score:      {weighted_f1 * 100:.2f}%")
    print("-" * 70)
    print("Per-Class Detailed Metrics:")
    print(f"  NORMAL:    Precision = {prec_norm*100:.2f}% | Recall = {rec_norm*100:.2f}% | F1 = {f1_norm*100:.2f}%")
    print(f"  PNEUMONIA: Precision = {prec_pneu*100:.2f}% | Recall = {rec_pneu*100:.2f}% | F1 = {f1_pneu*100:.2f}%")
    print("-" * 70)
    print("Confusion Matrix (rows=True Class, columns=Predicted Class):")
    print(f"                 Pred NORMAL   Pred PNEUMONIA")
    print(f"  True NORMAL    {tn:<13d} {fp:<13d}  (FP = {fp})")
    print(f"  True PNEUMONIA {fn:<13d} {tp:<13d}  (FN = {fn})")
    print("=" * 70)

    # Clinical trade-off explanation
    print("\nClinical Error Trade-Off Analysis:")
    print(f"- False Positives ({fp} cases): Normal patients flagged as Pneumonia.")
    print("  Consequence: Leads to unwarranted antibiotic prescribing, patient distress, and additional imaging.")
    print(f"- False Negatives ({fn} cases): Pneumonia patients flagged as Normal.")
    print("  Consequence: Untreated bacterial/viral pneumonia can lead to rapid respiratory failure and sepsis.")
    print("  Prioritizing Sensitivity (Recall) is essential in medical screening, but extreme imbalance destroys clinical trust.")

    # Save confusion matrix plot
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    fig.colorbar(im, ax=ax)
    ax.set(xticks=[0, 1], yticks=[0, 1],
           xticklabels=["NORMAL", "PNEUMONIA"],
           yticklabels=["NORMAL", "PNEUMONIA"],
           title=f"Test Confusion Matrix (Threshold = {threshold:.2f})\nAccuracy: {acc*100:.1f}% | BalAcc: {bal_acc*100:.1f}%",
           ylabel="True Label", xlabel="Predicted Label")

    for i in range(2):
        for j in range(2):
            total_row = (tn + fp) if i == 0 else (fn + tp)
            pct = (cm[i, j] / total_row) * 100
            ax.text(j, i, f"{cm[i, j]}\n({pct:.1f}%)",
                    ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black",
                    fontsize=12, fontweight="bold")

    plt.tight_layout()
    cm_plot_path = results_dir / "test_confusion_matrix.png"
    plt.savefig(cm_plot_path, dpi=150)
    plt.close()
    print(f"\nSaved confusion matrix figure: {cm_plot_path.resolve()}")

    # Save results JSON
    results_dict = {
        "model_file": model_path.name,
        "threshold": threshold,
        "threshold_source": thresh_source,
        "accuracy": float(acc),
        "balanced_accuracy": float(bal_acc),
        "roc_auc": float(roc_auc),
        "pr_auc": float(pr_auc),
        "sensitivity": float(sensitivity),
        "specificity": float(specificity),
        "normal_precision": float(prec_norm),
        "normal_recall": float(rec_norm),
        "normal_f1": float(f1_norm),
        "pneumonia_precision": float(prec_pneu),
        "pneumonia_recall": float(rec_pneu),
        "pneumonia_f1": float(f1_pneu),
        "macro_f1": float(macro_f1),
        "weighted_f1": float(weighted_f1),
        "confusion_matrix": {
            "TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp),
            "raw": cm.tolist()
        }
    }

    results_json_path = results_dir / "test_evaluation_results.json"
    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(results_dict, f, indent=2)
    print(f"Saved evaluation metrics JSON: {results_json_path.resolve()}")

    return results_dict


def main():
    parser = argparse.ArgumentParser(description="Evaluate model on held-out test set")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH), help="Path to checkpoint")
    parser.add_argument("--data_dir", type=str, default=str(DEFAULT_DATA_DIR), help="Data directory")
    parser.add_argument("--threshold_path", type=str, default=str(DEFAULT_THRESHOLD_PATH), help="Path to threshold JSON")
    parser.add_argument("--results_dir", type=str, default=str(DEFAULT_RESULTS_DIR), help="Results directory")
    parser.add_argument("--threshold", type=float, default=None, help="Explicit probability threshold")
    args = parser.parse_args()

    evaluate_test(
        model_path=Path(args.model),
        data_dir=Path(args.data_dir),
        threshold_path=Path(args.threshold_path),
        results_dir=Path(args.results_dir),
        custom_threshold=args.threshold
    )


if __name__ == "__main__":
    main()
