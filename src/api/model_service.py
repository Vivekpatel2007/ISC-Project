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
import logging
import math
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
from PIL import Image
import torch
import torch.nn as nn
from torchvision import models
from src.compute import device_preference, select_device
from src.modeling import image_transforms

from src.api.config import (
    ALLOWED_IMAGE_FORMATS,
    MAX_IMAGE_DIMENSION,
    MIN_IMAGE_DIMENSION,
    MODEL_CHECKPOINT_PATH,
)

# Pillow decompression bomb protection: limit total pixels to MAX_IMAGE_DIMENSION^2 (16,777,216 px)
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION

logger = logging.getLogger(__name__)
DISCLAIMER_TEXT = (
    "AI-assisted screening output for clinical decision support. "
    "Not a standalone or definitive medical diagnosis. "
    "Clinical review and correlation by a qualified radiologist or physician is required."
)


class ModelInferenceError(Exception):
    """Raised when an error occurs during image validation, preprocessing, or inference."""
    pass


class InvalidImagePayloadError(ModelInferenceError):
    """Raised for invalid image files; this does not verify chest X-ray suitability."""
    pass


def validate_threshold(value):
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        raise ModelInferenceError("Decision threshold must be a finite number between 0 and 1.") from None
    if isinstance(value, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ModelInferenceError("Decision threshold must be a finite number between 0 and 1.")
    return threshold


class DenseNetInferenceEngine:
    def __init__(self, checkpoint_path: Union[str, Path] = MODEL_CHECKPOINT_PATH):
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Model checkpoint not found at: {self.checkpoint_path.resolve()}")

        self.device = select_device()
        self._prediction_lock = Lock()
        self._load_model()

    def _load_model(self) -> None:
        """Load weights, architecture, and inference metadata from checkpoint."""
        ckpt = torch.load(self.checkpoint_path, map_location="cpu", weights_only=True)

        if not isinstance(ckpt, dict) or not isinstance(ckpt.get("model_state_dict"), dict):
            raise ModelInferenceError("Checkpoint must contain model_state_dict.")
        if ckpt.get("architecture", "densenet121") != "densenet121":
            raise ModelInferenceError("Checkpoint architecture must be densenet121.")

        self.class_names = ckpt.get("class_names", ["NORMAL", "PNEUMONIA"])
        self.class_to_idx = ckpt.get("class_to_idx", {"NORMAL": 0, "PNEUMONIA": 1})
        if self.class_names != ["NORMAL", "PNEUMONIA"] or self.class_to_idx != {"NORMAL": 0, "PNEUMONIA": 1}:
            raise ModelInferenceError("Checkpoint class order must be NORMAL=0, PNEUMONIA=1.")
        self.image_size = ckpt.get("image_size", 224)
        if type(self.image_size) is not int or not MIN_IMAGE_DIMENSION <= self.image_size <= MAX_IMAGE_DIMENSION:
            raise ModelInferenceError("Checkpoint image_size is outside the supported image dimensions.")
        self.norm = ckpt.get("normalization", {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]})
        try:
            mean, std = self.norm["mean"], self.norm["std"]
            valid_norm = len(mean) == len(std) == 3 and all(math.isfinite(float(value)) for value in [*mean, *std])
            valid_norm = valid_norm and all(float(value) > 0 for value in std)
        except (TypeError, ValueError, KeyError):
            valid_norm = False
        if not valid_norm:
            raise ModelInferenceError("Checkpoint normalization requires three finite means and positive standard deviations.")
        self.threshold = validate_threshold(ckpt.get("threshold", 0.40))
        self.preprocessing = ckpt.get("preprocessing", {"resize_mode": "stretch"})
        if not isinstance(self.preprocessing, dict) or self.preprocessing.get("resize_mode") not in {"stretch", "letterbox"}:
            raise ModelInferenceError("Checkpoint preprocessing resize_mode must be stretch or letterbox.")
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
        model.eval()
        try:
            model.to(self.device)
            if self.device.type == "cuda":
                # Verify the actual architecture and precision before accepting requests.
                with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
                    model(torch.zeros(1, 3, self.image_size, self.image_size, device=self.device))
                torch.cuda.synchronize(self.device)
        except RuntimeError:
            if self.device.type != "cuda" or device_preference() != "auto":
                raise
            logger.warning("CUDA model initialization failed; using CPU instead.", exc_info=True)
            self.device = torch.device("cpu")
            model.to(self.device)
        self.model = model

        # Standardized eval transformation
        self.transform = image_transforms(self.image_size, self.norm, self.preprocessing["resize_mode"])

    def validate_and_decode_image(self, image_bytes: bytes) -> Image.Image:
        """
        Validate image headers, format, and dimensions purely in memory.

        Raises:
            InvalidImagePayloadError: If decoding fails or format/dimensions are disallowed.
        """
        if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) < 32:
            raise InvalidImagePayloadError("Invalid image payload: payload is empty or too short.")

        try:
            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                detected_format = pil_img.format
                if detected_format not in ALLOWED_IMAGE_FORMATS:
                    raise InvalidImagePayloadError(
                        f"Unsupported image format: '{detected_format}'. Allowed formats: {ALLOWED_IMAGE_FORMATS}"
                    )
                w, h = pil_img.size
                if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                    raise InvalidImagePayloadError(
                        f"Image dimensions ({w}x{h}) are too small. Minimum is {MIN_IMAGE_DIMENSION}px."
                    )
                if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                    raise InvalidImagePayloadError(
                        f"Image dimensions ({w}x{h}) exceed maximum permitted size ({MAX_IMAGE_DIMENSION}px)."
                    )
                pil_img.verify()
            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                pil_img.load()
                return pil_img.convert("RGB")
        except InvalidImagePayloadError:
            raise
        except Image.DecompressionBombError:
            raise InvalidImagePayloadError("Image decompression bomb detected: pixel count exceeds maximum safe limit.") from None
        except Exception as e:
            raise InvalidImagePayloadError(f"Malformed or unreadable image file: {type(e).__name__}") from None

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
        threshold = validate_threshold(custom_threshold if custom_threshold is not None else self.threshold)
        pil_img = self.validate_and_decode_image(image_bytes)
        input_tensor = self.transform(pil_img).unsqueeze(0)

        # Bound activation/workspace memory when API worker threads share this model.
        with self._prediction_lock, torch.no_grad():
            input_tensor = input_tensor.to(self.device)
            with torch.autocast(device_type=self.device.type, dtype=torch.float16, enabled=(self.device.type == "cuda")):
                logits = self.model(input_tensor)
            if logits.shape != (1, 2) or not bool(torch.isfinite(logits).all()):
                raise ModelInferenceError("Model returned invalid or non-finite class scores.")
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
            "threshold_applied": round(threshold, 8),
            "model_architecture": "densenet121",
            "model_epoch": self.best_epoch,
            "device": str(self.device),
            "disclaimer": DISCLAIMER_TEXT
        }
