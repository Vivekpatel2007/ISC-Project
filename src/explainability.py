"""On-demand Grad-CAM for the supported DenseNet; no hooks, updates, or disk images."""

import base64
import io

import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn.functional as F

LAYER = 'features.denseblock4'
LIMITATION = ('Grad-CAM highlights relative positive contributions to a class score. '
              'It is not a lesion segmentation, confirmed pneumonia location, causal explanation, '
              'or measure of diagnostic certainty. Clinical review is required.')


def densenet_gradcam(model, inputs, target_class, threshold):
    """Use the exact DenseNet forward operations; only the final feature tensor needs gradients.

    Detaching the prefix avoids retaining the full DenseNet training graph. autograd.grad
    never populates parameter .grad fields. The caller serializes this with predictions.
    """
    if any(module.training for module in model.modules()):
        raise ValueError('Explanations require the model in evaluation mode.')
    layers = list(model.features.named_children())
    if [name for name, _ in layers[-2:]] != ['denseblock4', 'norm5']:
        raise ValueError('Unsupported DenseNet feature layout.')
    with torch.inference_mode(False), torch.enable_grad(), torch.autocast(
            device_type=inputs.device.type, dtype=torch.float16, enabled=inputs.device.type == 'cuda'):
        with torch.no_grad():
            features = inputs
            for _, module in layers[:-1]:
                features = module(features)
        features = features.detach().requires_grad_(True)
        out = F.relu(model.features.norm5(features), inplace=False)
        logits = model.classifier(torch.flatten(F.adaptive_avg_pool2d(out, (1, 1)), 1))
        if logits.shape != (1, 2) or not bool(torch.isfinite(logits).all()):
            raise ValueError('Non-finite or invalid explanation scores.')
        probabilities = torch.softmax(logits.float(), dim=1)
        predicted = 1 if float(probabilities[0, 1].detach()) >= threshold else 0
        if target_class != predicted:
            raise ExplanationMismatch('The current model decision differs. Run screening again before explaining.')
        gradients, = torch.autograd.grad(logits[0, target_class], features)
        if not bool(torch.isfinite(gradients).all()):
            raise ValueError('Non-finite explanation gradients.')
        weights = gradients.float().mean(dim=(2, 3), keepdim=True)
        cam = F.relu((weights * features.detach().float()).sum(dim=1, keepdim=True))
        if not bool(torch.isfinite(cam).all()):
            raise ValueError('Non-finite explanation map.')
        cam = F.interpolate(cam, size=inputs.shape[-2:], mode='bilinear', align_corners=False)
    return cam[0, 0].detach().cpu().numpy(), logits.detach(), probabilities.detach()


class ExplanationMismatch(ValueError):
    """A fresh screening result is required before generating this explanation."""


def aligned_heatmap(cam, image, image_size, resize_mode):
    """Remove actual Pillow letterboxing, then restore the source image geometry."""
    if cam.shape != (image_size, image_size) or not np.isfinite(cam).all():
        raise ValueError('Invalid heatmap dimensions or values.')
    box = (0, 0, image_size, image_size)
    if resize_mode == 'letterbox':
        width, height = ImageOps.contain(image, (image_size, image_size), method=Image.Resampling.BILINEAR).size
        left, top = (image_size - width) // 2, (image_size - height) // 2
        box = (left, top, left + width, top + height)
    elif resize_mode != 'stretch':
        raise ValueError('Unsupported explanation preprocessing.')
    cropped = cam[box[1]:box[3], box[0]:box[2]]
    minimum, maximum = float(cropped.min()), float(cropped.max())
    informative = maximum > 0 and maximum - minimum > np.finfo(np.float32).eps * max(maximum, 1e-20) * 16
    status = 'available' if informative else 'no_spatial_signal'
    normalized = (cropped - minimum) / (maximum - minimum) if informative else np.zeros_like(cropped)
    restored = np.asarray(Image.fromarray(normalized.astype(np.float32)).resize(image.size, Image.Resampling.BILINEAR))
    # Yellow -> orange -> red, with transparent zero contribution. A separate UI
    # opacity slider controls the entire overlay. Intensity is relative per image.
    rgba = np.empty((*restored.shape, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = np.rint(225 * (1 - restored)).astype(np.uint8)
    rgba[..., 2] = np.rint(70 * (1 - restored)).astype(np.uint8)
    rgba[..., 3] = np.rint(255 * restored).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgba).save(buffer, format='PNG')
    return dict(heatmap_png_base64=base64.b64encode(buffer.getvalue()).decode('ascii'),
                status=status, content_box=list(box), width=image.width, height=image.height)
