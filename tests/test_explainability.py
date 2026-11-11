"""Analytical, geometry, and model-sensitivity checks for Grad-CAM."""

import base64
from collections import OrderedDict
import io

import numpy as np
from PIL import Image, ImageOps
import pytest
import torch
from torch import nn

from src.explainability import aligned_heatmap, densenet_gradcam, ExplanationMismatch


class AnalyticalDenseNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(OrderedDict([
            ('denseblock4', nn.Identity()), ('norm5', nn.Identity()),
        ]))
        self.classifier = nn.Linear(2, 2, bias=False)
        with torch.no_grad():
            self.classifier.weight.copy_(torch.eye(2))
        self.eval()

    def forward(self, inputs):
        values = torch.relu(self.features(inputs))
        return self.classifier(values.mean(dim=(2, 3)))


def fixture_inputs():
    return torch.tensor([[[[3., 0.], [0., 0.]], [[0., 0.], [0., 2.]]]])


def test_analytic_location_and_high_region_occlusion_reduce_target_logit():
    model, inputs = AnalyticalDenseNet(), fixture_inputs()
    cam, logits, _ = densenet_gradcam(model, inputs, 0, .5)
    assert np.argmax(cam) == 0 and cam[0, 0] > 0
    assert torch.equal(logits, model(inputs))
    occluded = inputs.clone(); occluded[:, :, 0, 0] = 0
    assert model(occluded)[0, 0] < logits[0, 0]
    # A different classifier target responds to the other region.
    other, _, _ = densenet_gradcam(model, inputs, 1, 0.)
    assert np.argmax(other) == 3


def test_saturated_probability_still_has_raw_logit_gradients():
    model = AnalyticalDenseNet()
    with torch.no_grad():
        model.classifier.weight[0] *= 1000
    cam, _, probabilities = densenet_gradcam(model, fixture_inputs(), 0, .5)
    assert float(probabilities[0, 0]) == 1.
    assert np.isfinite(cam).all() and cam.max() > 0


def test_classifier_weight_change_changes_the_map_without_changing_the_input():
    model, inputs = AnalyticalDenseNet(), fixture_inputs()
    first, _, _ = densenet_gradcam(model, inputs, 0, 1.)
    with torch.no_grad():
        model.classifier.weight[0].copy_(torch.tensor([0., 1.]))
    changed, _, _ = densenet_gradcam(model, inputs, 0, 1.)
    assert np.argmax(first) != np.argmax(changed)


def test_frozen_model_and_existing_parameter_gradients_are_preserved():
    model = AnalyticalDenseNet()
    for parameter in model.parameters():
        parameter.grad = torch.ones_like(parameter)
        parameter.requires_grad_(False)
    weights = {k: v.clone() for k, v in model.state_dict().items()}
    flags = [module.training for module in model.modules()]
    rng = torch.get_rng_state().clone()
    densenet_gradcam(model, fixture_inputs(), 0, .5)
    assert all(torch.equal(value, model.state_dict()[key]) for key, value in weights.items())
    assert flags == [module.training for module in model.modules()]
    assert torch.equal(rng, torch.get_rng_state())
    assert all(not p.requires_grad and torch.equal(p.grad, torch.ones_like(p)) for p in model.parameters())
    assert not any(module._forward_hooks or module._backward_hooks for module in model.modules())


def test_changed_decision_and_training_mode_are_rejected():
    model = AnalyticalDenseNet()
    with pytest.raises(ExplanationMismatch):
        densenet_gradcam(model, fixture_inputs(), 1, .5)
    model.train()
    with pytest.raises(ValueError, match='evaluation'):
        densenet_gradcam(model, fixture_inputs(), 0, .5)


@pytest.mark.parametrize('shape', [(100, 100), (413, 173), (173, 413), (4096, 64), (64, 4096)])
def test_letterbox_crop_matches_actual_preprocessing_and_source_dimensions(shape):
    size = 224
    source = Image.new('RGB', shape)
    width, height = ImageOps.contain(source, (size, size)).size
    left, top = (size - width) // 2, (size - height) // 2
    cam = np.zeros((size, size), dtype=np.float32)
    # A horizontal gradient in the actual image rectangle; padded areas have
    # much larger values to detect accidental normalization before cropping.
    cam[:] = 100
    cam[top:top + height, left:left + width] = np.linspace(0, 1, width)[None, :]
    result = aligned_heatmap(cam, source, size, 'letterbox')
    assert result['content_box'] == [left, top, left + width, top + height]
    with Image.open(io.BytesIO(base64.b64decode(result['heatmap_png_base64']))) as overlay:
        assert overlay.size == shape and overlay.mode == 'RGBA'
        pixels = np.asarray(overlay)
        # Bilinear downsampling averages boundary pixels slightly.
        assert pixels[shape[1] // 2, 0, 3] <= 2
        assert pixels[shape[1] // 2, -1, 3] >= 253


@pytest.mark.parametrize('value', [0., 1.])
def test_constant_maps_return_a_transparent_overlay_without_fake_highlights(value):
    result = aligned_heatmap(np.full((224, 224), value, dtype=np.float32), Image.new('RGB', (100, 200)), 224, 'stretch')
    assert result['status'] == 'no_spatial_signal'
    with Image.open(io.BytesIO(base64.b64decode(result['heatmap_png_base64']))) as overlay:
        assert not np.asarray(overlay)[..., 3].any()


def test_real_densenet_forward_is_identical_and_model_state_is_unchanged():
    from torchvision.models import densenet121
    model = densenet121(weights=None).eval()
    model.classifier = nn.Linear(model.classifier.in_features, 2).eval()
    inputs = torch.linspace(-1., 1., 3 * 64 * 64).reshape(1, 3, 64, 64)
    with torch.no_grad():
        expected = model(inputs)
    target = int(torch.softmax(expected, dim=1)[0, 1] >= .5)
    state = {key: value.clone() for key, value in model.state_dict().items()}
    _, actual, _ = densenet_gradcam(model, inputs, target, .5)
    assert torch.equal(expected, actual)
    assert all(torch.equal(value, model.state_dict()[key]) for key, value in state.items())
    assert all(parameter.grad is None for parameter in model.parameters())
