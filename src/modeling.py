"""Shared preprocessing and small ImageNet-pretrained experiment backbones."""

import hashlib
from pathlib import Path
import re
from urllib.parse import urlsplit

from PIL import Image, ImageOps
import torch
import torch.nn as nn
from torchvision import models, transforms
from torchvision.transforms import InterpolationMode

MODEL_NAMES = ('densenet121', 'efficientnet_b0')
NORMALIZATION = {'mean': [0.485, 0.456, 0.406], 'std': [0.229, 0.224, 0.225]}


class Letterbox:
    """Resize the whole image without stretching anatomy or cropping its field."""
    def __init__(self, size):
        self.size = size

    def __call__(self, image):
        resized = ImageOps.contain(image, (self.size, self.size), method=Image.Resampling.BILINEAR)
        canvas = Image.new(image.mode, (self.size, self.size), 0)
        canvas.paste(resized, ((self.size - resized.width) // 2, (self.size - resized.height) // 2))
        return canvas


def image_transforms(size=224, normalization=None, resize_mode='letterbox', training=False):
    if resize_mode not in {'letterbox', 'stretch'}:
        raise ValueError('resize_mode must be letterbox or stretch.')
    norm = normalization or NORMALIZATION
    operations = [transforms.Grayscale(num_output_channels=3),
                  Letterbox(size) if resize_mode == 'letterbox' else transforms.Resize((size, size))]
    if training:
        operations.extend([
            transforms.RandomAffine(degrees=5, translate=(0.02, 0.02), scale=(0.98, 1.02),
                                    interpolation=InterpolationMode.BILINEAR, fill=0),
            transforms.ColorJitter(brightness=0.08, contrast=0.08),
        ])
    operations.extend([transforms.ToTensor(), transforms.Normalize(norm['mean'], norm['std'])])
    return transforms.Compose(operations)


def build_classifier(name, pretrained=True, dropout=0.2):
    weights = None
    if name == 'densenet121' and pretrained:
        weights = models.DenseNet121_Weights.DEFAULT
    elif name == 'efficientnet_b0' and pretrained:
        weights = models.EfficientNet_B0_Weights.DEFAULT
    if weights:
        filename = Path(urlsplit(weights.url).path).name
        cached = Path(torch.hub.get_dir()) / 'checkpoints' / filename
        expected = re.search(r'-([0-9a-f]+)\.pth$', filename).group(1)
        if cached.exists() and not hashlib.sha256(cached.read_bytes()).hexdigest().startswith(expected):
            raise ValueError(f'Cached ImageNet weights failed their official hash prefix: {cached}')
    if name == 'densenet121':
        model = models.densenet121(weights=weights)
        features = model.classifier.in_features
    elif name == 'efficientnet_b0':
        model = models.efficientnet_b0(weights=weights)
        features = model.classifier[1].in_features
    else:
        raise ValueError(f'Unknown experiment backbone {name}; choose {MODEL_NAMES}.')
    model.classifier = nn.Sequential(nn.Dropout(dropout), nn.Linear(features, 2))
    return model


def set_training_stage(model, head_only=False, freeze_batch_norm=True):
    head_ids = {id(parameter) for parameter in model.classifier.parameters()}
    for parameter in model.parameters():
        parameter.requires_grad_(not head_only or id(parameter) in head_ids)
    model.train()
    if freeze_batch_norm:
        for module in model.modules():
            if isinstance(module, nn.modules.batchnorm._BatchNorm):
                module.eval()
