"""
Inference Engine Service
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

Features:
1. Pure In-Memory Inference: Raw bytes are decoded directly from memory via io.BytesIO.
   Plaintext images are NEVER written to the filesystem.
2. Rigid Format & Integrity Validation: Does not trust filenames or client MIME types;
   decodes bytes strictly using PIL to verify genuine image content and dimensions.
3. Checkpoint Conformity: Uses exact saved metadata from models/densenet121_pneumonia_best.pth:
   - Architecture: DenseNet121 with Dropout(0.20)
   - Classes: ['NORMAL', 'PNEUMONIA']
   - Image size: 224x224
   - Normalization: ImageNet mean [0.485, 0.456, 0.406], std [0.229, 0.224, 0.225]
   - Validation-tuned decision threshold: 0.40
4. Mandatory Clinical Disclaimer: Every prediction output explicitly reinforces that
   the output is an educational AI-assisted screening tool, NOT a definitive diagnosis.
"""

import io
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torchvision import models, transforms

from src.api.config import (
    ALLOWED_IMAGE_FORMATS,
    MAX_IMAGE_DIMENSION,
    MIN_IMAGE_DIMENSION,
    MODEL_CHECKPOINT_PATH,
)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
DISCLAIMER_TEXT = (
    "AI-assisted screening output for clinical decision support. "
    "Not a standalone or definitive medical diagnosis. "
    "Clinical review and correlation by a qualified radiologist or physician is required."
)


class ModelInferenceError(Exception):
    """Raised when an error occurs during image validation, preprocessing, or inference."""
    pass


class InvalidImagePayloadError(ModelInferenceError):
    """Raised when input bytes fail image validation or are not a valid radiograph."""
    pass


class DenseNetInferenceEngine:
    def __init__(self, checkpoint_path: Union[str, Path] = MODEL_CHECKPOINT_PATH):
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Model checkpoint not found at: {self.checkpoint_path.resolve()}")

        self.device = DEVICE
        self._load_model()

    def _load_model(self) -> None:
        """Load weights, architecture, and inference metadata from checkpoint."""
        ckpt = torch.load(self.checkpoint_path, map_location=self.device, weights_only=False)

        self.class_names = ckpt.get("class_names", ["NORMAL", "PNEUMONIA"])
        self.class_to_idx = ckpt.get("class_to_idx", {"NORMAL": 0, "PNEUMONIA": 1})
        self.image_size = ckpt.get("image_size", 224)
        self.norm = ckpt.get("normalization", {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]})
        self.threshold = float(ckpt.get("threshold", 0.40))
        self.best_epoch = ckpt.get("best_epoch", 5)

        # Reconstruct DenseNet121 architecture matching training pipeline
        model = models.densenet121(weights=None)
        in_features = model.classifier.in_features
        if "classifier.1.weight" in ckpt["model_state_dict"]:
            model.classifier = nn.Sequential(
                nn.Dropout(p=0.2),
                nn.Linear(in_features, len(self.class_names))
            )
        else:
            model.classifier = nn.Linear(in_features, len(self.class_names))

        model.load_state_dict(ckpt["model_state_dict"])
        model.to(self.device)
        model.eval()
        self.model = model

        # Standardized eval transformation
        self.transform = transforms.Compose([
            transforms.Grayscale(num_output_channels=3),
            transforms.Resize((self.image_size, self.image_size)),
            transforms.ToTensor(),
            transforms.Normalize(self.norm["mean"], self.norm["std"]),
        ])

    def validate_and_decode_image(self, image_bytes: bytes) -> Image.Image:
        """
        Validate image headers, format, and dimensions purely in memory.

        Raises:
            InvalidImagePayloadError: If decoding fails or format/dimensions are disallowed.
        """
        if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) < 32:
            raise InvalidImagePayloadError("Invalid image payload: payload is empty or too short.")

        try:
            pil_img = Image.open(io.BytesIO(image_bytes))
            # Force verification of internal image integrity
            pil_img.verify()

            # Reopen because verify() consumes file pointer in PIL
            pil_img = Image.open(io.BytesIO(image_bytes))
        except Exception as e:
            raise InvalidImagePayloadError(f"Malformed or unreadable image file: {type(e).__name__}") from None

        # Verify genuine image format (from headers, not extension or MIME)
        detected_format = pil_img.format
        if detected_format not in ALLOWED_IMAGE_FORMATS:
            raise InvalidImagePayloadError(
                f"Unsupported image format: '{detected_format}'. Allowed formats: {ALLOWED_IMAGE_FORMATS}"
            )

        w, h = pil_img.size
        if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
            raise InvalidImagePayloadError(
                f"Image dimensions ({w}x{h}) are too small for diagnostic analysis. Minimum is {MIN_IMAGE_DIMENSION}px."
            )
        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            raise InvalidImagePayloadError(
                f"Image dimensions ({w}x{h}) exceed maximum permitted size ({MAX_IMAGE_DIMENSION}px)."
            )

        return pil_img.convert("RGB")

    def predict(
        self,
        image_bytes: bytes,
        custom_threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Run inference on in-memory decrypted image bytes.

        Returns:
            Dictionary with prediction class, confidence scores, threshold, and clinical disclaimer.
        """
        pil_img = self.validate_and_decode_image(image_bytes)
        input_tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        threshold = custom_threshold if custom_threshold is not None else self.threshold

        with torch.no_grad():
            with torch.autocast(device_type=self.device.type, dtype=torch.float16, enabled=(self.device.type == "cuda")):
                logits = self.model(input_tensor)
            probs = torch.softmax(logits.float(), dim=1).squeeze().cpu().numpy()

        # Class 0: NORMAL, Class 1: PNEUMONIA
        prob_normal = float(probs[0])
        prob_pneumonia = float(probs[1])

        predicted_class = "PNEUMONIA" if prob_pneumonia >= threshold else "NORMAL"
        confidence = prob_pneumonia if predicted_class == "PNEUMONIA" else prob_normal

        return {
            "prediction": predicted_class,
            "confidence": round(confidence, 4),
            "pneumonia_probability": round(prob_pneumonia, 4),
            "normal_probability": round(prob_normal, 4),
            "threshold_applied": round(threshold, 2),
            "model_architecture": "densenet121",
            "model_epoch": self.best_epoch,
            "device": str(self.device),
            "disclaimer": DISCLAIMER_TEXT
        }
