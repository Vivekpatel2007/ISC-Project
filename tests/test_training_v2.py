"""Protect v2 split independence, calibration timing, and inference compatibility."""

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import torch

from src import training
from src.data_protocol import digest_json, plan_splits, validate_boundaries
from src.modeling import RandomJPEGCompression, image_transforms


def audit_rows():
    rows = []
    for label in ('NORMAL', 'PNEUMONIA'):
        for index in range(30):
            name = f'IM-{index:04d}-0001.jpeg' if label == 'NORMAL' else f'person{index}_bacteria_1.jpeg'
            key = f'{label}-{index}'
            rows.append(dict(path=f'train/{label}/{name}', split='train', label=label,
                             sha256=key, pixel_sha256=key))
        name = 'IM-9999-0001.jpeg' if label == 'NORMAL' else 'person9999_virus_1.jpeg'
        rows.append(dict(path=f'test/{label}/{name}', split='test', label=label,
                         sha256=f'test-{label}', pixel_sha256=f'test-{label}'))
    return dict(images=rows, missing_folders=[], decode_errors=[], api_incompatible_images=[])


def test_four_way_group_split_is_deterministic_and_keeps_existing_test_fixed():
    audit = audit_rows()
    old = plan_splits(audit)
    result = plan_splits(audit, train_ratio=.7, calibration_ratio=.15)
    assert result == plan_splits(audit, train_ratio=.7, calibration_ratio=.15)
    assert result['splits']['test'] == old['splits']['test']
    assert set(result['splits']) == {'train', 'val', 'test', 'calibration'}
    assert result['test_role'] == 'previously_reviewed_benchmark'
    validate_boundaries(result['splits'])
    # The boundary validator must actually inspect calibration, not merely train/val/test.
    result['splits']['calibration'][0]['group'] = result['splits']['train'][0]['group']
    with pytest.raises(ValueError, match='group overlap'):
        validate_boundaries(result['splits'])
    with pytest.raises(ValueError, match='Calibration ratio'):
        plan_splits(audit, train_ratio=.85, calibration_ratio=.2)


def test_jpeg_augmentation_preserves_geometry_and_never_changes_eval_transforms():
    image = Image.fromarray(np.random.default_rng(42).integers(0, 256, (63, 91, 3), dtype=np.uint8))
    result = RandomJPEGCompression(probability=1, quality=(40, 40))(image)
    assert result.mode == image.mode and result.size == image.size
    assert not np.array_equal(np.asarray(image), np.asarray(result))
    assert RandomJPEGCompression(probability=0)(image) is image
    assert torch.equal(image_transforms()(image), image_transforms(augmentation_profile='jpeg_robustness')(image))
    augmented = image_transforms(training=True, augmentation_profile='jpeg_robustness')(image)
    assert augmented.shape == (3, 224, 224) and torch.isfinite(augmented).all()


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.features = torch.nn.Conv2d(3, 3, 1)
        self.classifier = torch.nn.Linear(3, 2)

    def forward(self, inputs):
        return self.classifier(self.features(inputs).mean((2, 3)))


def test_threshold_reads_only_calibration_after_model_selection(tmp_path, monkeypatch):
    rows = {split: [] for split in ('train', 'val', 'calibration', 'test')}
    for split in rows:
        for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
            for index in range(2):
                key = f'{split}_{target}_{index}'
                path = tmp_path / (key + '.png')
                Image.new('L', (32, 32), 30 + target * 120 + index).save(path)
                rows[split].append(dict(path=path.name, label=label, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                        pixel_sha256=key, candidate_subject=key, group=key))
    manifest = dict(schema_version=1, source_root=str(tmp_path), splits=rows)
    manifest['manifest_sha256'] = digest_json(manifest)
    config = dict(image_size=32, resize_mode='letterbox', augmentation_profile='jpeg_robustness',
                  threshold_split='calibration', ranking_score_space='logit_margin', batch_size=2, accumulation_steps=2,
                  epochs=2, head_warmup_epochs=0, head_learning_rate=.001, backbone_learning_rate=.0001,
                  weight_decay=.0001, early_stopping_patience=7, early_stopping_min_delta=.0001,
                  freeze_batch_norm=True, mixed_precision=False, max_grad_norm=1., seed=42,
                  log_every_batches=10, validation_min_sensitivity=.95, num_workers=0)
    monkeypatch.setattr(training, 'ROOT', tmp_path)
    monkeypatch.setattr(training, 'select_device', lambda: torch.device('cpu'))
    monkeypatch.setattr(training, 'build_classifier', lambda *_, **__: Tiny())
    calls = []

    def fake_validate(model, loader, device, amp):
        split = loader.dataset.rows[0]['path'].split('_')[0]
        calls.append(split)
        assert split != 'test'
        scores = [.01, .02, .04, .06] if split == 'val' else [.1, .2, .8, .9]
        return dict(loss=.1, targets=[0, 0, 1, 1], scores=scores, roc_auc_logit_margin=1.,
                    **training.metrics([0, 0, 1, 1], scores))

    monkeypatch.setattr(training, 'validate', fake_validate)
    run = tmp_path / 'candidate'
    summary = training.train_candidate('densenet121', config, manifest, tmp_path, run)
    assert calls == ['val', 'val', 'calibration']
    assert summary['selection_metric'] == 'val_logit_margin_auc'
    checkpoint = torch.load(run / 'best.pt', weights_only=True)
    assert checkpoint['threshold_split'] == 'calibration'
    assert checkpoint['threshold_source'].startswith('calibration only')
    assert checkpoint['threshold'] == pytest.approx(.5)
    assert checkpoint['validation_metrics']['sensitivity'] == 0
    assert checkpoint['calibration_metrics']['sensitivity'] == 1
    assert summary['validation_at_selected_threshold']['sensitivity'] == 0
    assert summary['calibration_at_selected_threshold']['sensitivity'] == 1
    assert (run / 'calibration_predictions.json').is_file()
    assert not (run / 'final_test_results.json').exists()


def test_reviewed_benchmark_requires_explicit_diagnostic_flag(tmp_path, monkeypatch):
    from scripts import evaluate_experiment
    from src import data_protocol
    suite = tmp_path / 'data/experiments/example'
    model_dir = suite / 'densenet121'
    model_dir.mkdir(parents=True)
    payload = b'not loaded because the benchmark gate runs first'
    (model_dir / 'best.pt').write_bytes(payload)
    comparison = dict(pending_candidates=[], recommended_checkpoint='data/experiments/example/densenet121/best.pt',
                      candidates=[dict(checkpoint_sha256=hashlib.sha256(payload).hexdigest())])
    (suite / 'comparison.json').write_text(json.dumps(comparison))
    monkeypatch.setattr(evaluate_experiment, 'ROOT', tmp_path)
    monkeypatch.setattr(data_protocol, 'load_manifest', lambda _: ({'test_role': 'previously_reviewed_benchmark'}, tmp_path))
    monkeypatch.setattr(evaluate_experiment.sys, 'argv', ['evaluate_experiment.py', '--suite', str(suite)])
    with pytest.raises(ValueError, match='already reviewed'):
        evaluate_experiment.main()
