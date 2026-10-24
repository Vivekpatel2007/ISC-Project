"""
Prediction Visualization & Explainability Tool
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

This tool loads a trained model checkpoint and generates visual diagnostic cards
for sample chest X-rays, including:
- Original radiographic image
- Predicted class & probability scores
- Ground truth label (if available)
- Grad-CAM heatmap highlighting lung regions responsible for the prediction
"""

import argparse
import json
from pathlib import Path
from PIL import Image
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models, transforms

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DEFAULT_MODEL = PROJECT_ROOT / "models" / "densenet121_pneumonia_best.pth"
DEFAULT_OUT_DIR = PROJECT_ROOT / "results" / "diagnostics" / "predictions_visualized"


class DenseNetGradCAM:
    def __init__(self, model, image_size=224):
        self.model = model
        self.image_size = image_size

    def generate_cam(self, input_tensor, target_class=1):
        self.model.eval()
        self.model.zero_grad()

        features = self.model.features(input_tensor)
        features.retain_grad()

        out = F.relu(features, inplace=False)
        out = F.adaptive_avg_pool2d(out, (1, 1))
        out = torch.flatten(out, 1)
        logits = self.model.classifier(out)

        score = logits[:, target_class]
        score.backward()

        gradients = features.grad
        weights = torch.mean(gradients, dim=[2, 3], keepdim=True)
        cam = torch.sum(weights * features, dim=1, keepdim=True)
        cam = F.relu(cam)

        cam = F.interpolate(cam, size=(self.image_size, self.image_size), mode="bilinear", align_corners=False)
        cam = cam.squeeze().cpu().detach().numpy()
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return cam, logits


def load_model(checkpoint_path: Path):
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")

    ckpt = torch.load(checkpoint_path, map_location=DEVICE, weights_only=False)
    class_names = ckpt.get("class_names", ["NORMAL", "PNEUMONIA"])
    image_size = ckpt.get("image_size", 224)
    threshold = ckpt.get("threshold", 0.5)

    model = models.densenet121(weights=None)
    in_features = model.classifier.in_features
    if "classifier.1.weight" in ckpt["model_state_dict"]:
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.2),
            nn.Linear(in_features, len(class_names))
        )
    else:
        model.classifier = nn.Linear(in_features, len(class_names))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(DEVICE)
    model.eval()

    transform = transforms.Compose([
        transforms.Grayscale(num_output_channels=3),
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    return model, transform, class_names, threshold, image_size


def plot_single_prediction(image_path: Path, model, transform, class_names, threshold, image_size, out_path: Path, true_label=None):
    pil_img = Image.open(image_path).convert("RGB")
    resized_pil = pil_img.resize((image_size, image_size))

    tensor = transform(pil_img).unsqueeze(0).to(DEVICE)
    grad_cam = DenseNetGradCAM(model, image_size=image_size)

    # First forward to get predicted class
    with torch.no_grad():
        with torch.autocast(device_type=DEVICE.type, dtype=torch.float16, enabled=(DEVICE.type == "cuda")):
            out = model(tensor)
        probs = F.softmax(out.float(), dim=1).squeeze().cpu().numpy()

    pneu_prob = probs[1]
    pred_class = "PNEUMONIA" if pneu_prob >= threshold else "NORMAL"
    target_class_idx = 1 if pred_class == "PNEUMONIA" else 0

    cam_map, _ = grad_cam.generate_cam(tensor, target_class=target_class_idx)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))

    # 1. Original Image
    axes[0].imshow(resized_pil)
    axes[0].set_title(f"Input Chest X-Ray\nFile: {image_path.name}", fontsize=10)
    axes[0].axis("off")

    # 2. Grad-CAM Heatmap
    im2 = axes[1].imshow(cam_map, cmap="jet")
    axes[1].set_title(f"Grad-CAM Heatmap\n(Evidence for {pred_class})", fontsize=10)
    axes[1].axis("off")
    fig.colorbar(im2, ax=axes[1], fraction=0.046, pad=0.04)

    # 3. Superimposed Overlay
    axes[2].imshow(resized_pil)
    axes[2].imshow(cam_map, cmap="jet", alpha=0.45)
    title_text = f"Prediction: {pred_class} (P={pneu_prob:.1%})\nThreshold: {threshold:.2f}"
    if true_label:
        match_str = "CORRECT" if pred_class == true_label else "INCORRECT"
        title_text += f"\nGround Truth: {true_label} [{match_str}]"
    axes[2].set_title(title_text, fontsize=10, fontweight="bold",
                     color="green" if (true_label and pred_class == true_label) else ("red" if true_label else "black"))
    axes[2].axis("off")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    plt.close()
    return pred_class, pneu_prob


def main():
    parser = argparse.ArgumentParser(description="Visualize Chest X-Ray Model Predictions & Grad-CAM")
    parser.add_argument("--image", type=str, help="Path to single image file")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL), help="Path to model checkpoint")
    parser.add_argument("--out_dir", type=str, default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument("--threshold", type=float, default=None, help="Custom probability threshold")
    parser.add_argument("--test_samples", type=int, default=5, help="Number of test images to sample and plot")
    args = parser.parse_args()

    model_path = Path(args.model)
    model, transform, class_names, default_thresh, img_sz = load_model(model_path)
    threshold = args.threshold if args.threshold is not None else default_thresh

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.image:
        img_path = Path(args.image)
        out_file = out_dir / f"prediction_{img_path.stem}.png"
        pred, prob = plot_single_prediction(img_path, model, transform, class_names, threshold, img_sz, out_file)
        print(f"Processed: {img_path.name} -> Predicted: {pred} (P={prob:.3f}) | Saved to {out_file}")
    else:
        # Sample test images
        print(f"Visualizing {args.test_samples} test samples...")
        for cls in ["NORMAL", "PNEUMONIA"]:
            cls_folder = PROJECT_ROOT / "data" / "model_data" / "test" / cls
            if cls_folder.exists():
                samples = list(cls_folder.glob("*.*"))[:args.test_samples]
                for s in samples:
                    out_file = out_dir / f"test_{cls}_{s.stem}.png"
                    pred, prob = plot_single_prediction(s, model, transform, class_names, threshold, img_sz, out_file, true_label=cls)
                    print(f"  {cls} | {s.name} -> Pred: {pred} ({prob:.3f})")
        print(f"\nAll visualization cards saved in: {out_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
