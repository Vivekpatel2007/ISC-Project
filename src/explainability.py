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


def describe_heatmap(normalized, target_class):
    """Deterministic spatial notes, not generated radiological findings.

    Compare up to nine coarse displayed-image sections. Select at most three
    with >=45% of the strongest section's mean normalized contribution.
    These sections are a reading aid, not detected lesions.
    """
    if target_class not in {'NORMAL', 'PNEUMONIA'}:
        raise ValueError('Invalid description target class.')
    if (normalized.ndim != 2 or not normalized.size or not np.isfinite(normalized).all()
            or normalized.min() < 0 or normalized.max() > 1):
        raise ValueError('Descriptions require a finite normalized contribution map.')
    base = dict(summary_basis='gradcam_spatial_v1', coordinate_system='displayed_image')
    if float(np.ptp(normalized)) <= np.finfo(np.float32).eps * 16:
        return dict(**base, regions=[], distribution='none',
                    summary=f'The model returned {target_class}, but this heatmap has no spatially informative '
                            'positive contribution pattern. There are no image regions to describe reliably.')
    height, width = normalized.shape
    rows, columns = min(3, height), min(3, width)
    ys = np.linspace(0, height, rows + 1, dtype=int)
    xs = np.linspace(0, width, columns + 1, dtype=int)
    vertical = {1: ['full-height'], 2: ['upper', 'lower'], 3: ['upper', 'middle', 'lower']}[rows]
    horizontal = {1: ['full-width'], 2: ['left', 'right'], 3: ['left', 'center', 'right']}[columns]
    candidates = []
    for row in range(rows):
        for column in range(columns):
            x0, x1, y0, y1 = int(xs[column]), int(xs[column + 1]), int(ys[row]), int(ys[row + 1])
            section = normalized[y0:y1, x0:x1]
            # Pick an actual near-peak pixel closest to the high-value pixels'
            # centroid. The marker never points at an unsupported gap between peaks.
            near_peak = np.argwhere(section >= float(section.max()) * .95)
            center = near_peak.mean(axis=0)
            point = near_peak[np.square(near_peak - center).sum(axis=1).argmin()]
            candidates.append(dict(location=f'{vertical[row]}-{horizontal[column]}',
                                   bounds=[x0 / width, y0 / height, x1 / width, y1 / height],
                                   marker=[(x0 + int(point[1]) + .5) / width, (y0 + int(point[0]) + .5) / height],
                                   mean=float(section.mean())))
    candidates.sort(key=lambda item: -item['mean'])  # Stable row/column ordering breaks ties.
    strongest = candidates[0]['mean']
    selected = [item for item in candidates if item['mean'] >= .45 * strongest][:3]
    regions = []
    for number, item in enumerate(selected, 1):
        rank = 'strongest' if number == 1 else ('second-strongest' if number == 2 else 'third-strongest')
        regions.append(dict(id=number, location=item['location'], title=f"{item['location'].capitalize()} image section",
                            bounds=item['bounds'], marker=item['marker'],
                            description=f'This section has the {rank} average contribution to the '
                                        f'{target_class} score among the image sections compared. Number {number} '
                                        'marks a location with a high contribution inside this section.'))
    broad = float(np.mean(normalized >= .5)) >= .5
    locations = ', '.join(region['location'] for region in regions)
    section_label = 'section' if len(regions) == 1 else 'sections'
    summary = (f'For the {target_class} output, stronger positive contributions appear in the {locations} '
               f'{section_label} of the displayed image. ' +
               ('The higher-contribution pattern is broadly spread across the image. ' if broad else '') +
               'The numbered notes describe the contribution map; they do not identify which medical finding is present.')
    return dict(**base, regions=regions, distribution='broad' if broad else 'concentrated', summary=summary)


def aligned_heatmap(cam, image, image_size, resize_mode, target_class=None):
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
    narrative = describe_heatmap(normalized, target_class) if target_class is not None else {}
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
    return dict(**narrative, heatmap_png_base64=base64.b64encode(buffer.getvalue()).decode('ascii'),
                status=status, content_box=list(box), width=image.width, height=image.height)
