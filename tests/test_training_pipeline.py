"""Test split integrity, preprocessing parity, accumulation, and tiny synthetic resume."""

from collections import Counter
import copy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
from PIL import Image
import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset
from torchvision import transforms

from src.data_protocol import digest_json, load_manifest, plan_splits, validate_boundaries
from src.modeling import Letterbox, NORMALIZATION, image_transforms, set_training_stage
from src import training


def audited_rows():
    rows = []
    for label in ('NORMAL', 'PNEUMONIA'):
        for index in range(10):
            filename = f'IM-{index:04d}-0001.jpeg' if label == 'NORMAL' else f'person{index}_bacteria_1.jpeg'
            rows.append(dict(path=f'train/{label}/{filename}', label=label, split='train',
                             sha256=f'bytes-{label}-{index}', pixel_sha256=f'pixels-{label}-{index}'))
        filename = 'IM-9999-0001.jpeg' if label == 'NORMAL' else 'person9999_bacteria_1.jpeg'
        rows.append(dict(path=f'test/{label}/{filename}', label=label, split='test',
                         sha256=f'test-{label}', pixel_sha256=f'test-pixels-{label}'))
    return dict(images=rows, missing_folders=[], decode_errors=[], api_incompatible_images=[])


def test_reserved_components_remove_transitive_subject_and_duplicate_connections():
    audit = audited_rows()
    audit['images'].extend([
        dict(path='train/PNEUMONIA/person9999_virus_2.jpeg', label='PNEUMONIA', split='train', sha256='a', pixel_sha256='bridge'),
        dict(path='train/PNEUMONIA/person7777_virus_2.jpeg', label='PNEUMONIA', split='train', sha256='b', pixel_sha256='bridge'),
        dict(path='train/PNEUMONIA/person7777_bacteria_3.jpeg', label='PNEUMONIA', split='train', sha256='c', pixel_sha256='other'),
    ])
    result = plan_splits(audit)
    assert result['exclusions']['candidate_or_duplicate_component_reserved_for_test'] == 3
    assert result['splits'] == plan_splits(audit)['splits']
    validate_boundaries(result['splits'])
    assert all(set(Counter(row['label'] for row in rows)) == {'NORMAL', 'PNEUMONIA'} for rows in result['splits'].values())


def test_conflicting_duplicate_labels_are_rejected():
    audit = audited_rows()
    audit['images'][-1]['pixel_sha256'] = audit['images'][0]['pixel_sha256']
    with pytest.raises(ValueError, match='conflicting labels'):
        plan_splits(audit)


def test_changed_source_components_are_excluded_and_test_duplicates_are_recorded():
    audit = audited_rows()
    audit['images'].append(dict(audit['images'][-1], path='test/PNEUMONIA/person9999_virus_2.jpeg'))
    suspect = audit['images'][0]['path']
    result = plan_splits(audit, suspect_paths=[suspect])
    assert result['exclusions']['component_with_changed_source'] == 1
    assert result['exclusions']['duplicate_pixels_within_test'] == 1
    assert all(row['path'] != suspect for rows in result['splits'].values() for row in rows)


def test_letterbox_preserves_full_image_shape_instead_of_stretching():
    result = np.asarray(Letterbox(100)(Image.new('RGB', (100, 50), 'white')))
    assert result.shape == (100, 100, 3)
    assert (result[:25] == 0).all() and (result[75:] == 0).all()
    assert (result[25:75] == 255).all()


def test_legacy_eval_preprocessing_stays_bitwise_equal():
    image = Image.fromarray(np.arange(63 * 91 * 3, dtype=np.uint8).reshape(63, 91, 3))
    previous = transforms.Compose([transforms.Grayscale(3), transforms.Resize((224, 224)),
                                   transforms.ToTensor(), transforms.Normalize(**NORMALIZATION)])
    assert torch.equal(previous(image), image_transforms(resize_mode='stretch')(image))
    assert torch.equal(image_transforms()(image), image_transforms()(image))


class TinyClassifier(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.features = torch.nn.Sequential(torch.nn.Linear(3, 4), torch.nn.BatchNorm1d(4), torch.nn.ReLU())
        self.classifier = torch.nn.Sequential(torch.nn.Dropout(0.1), torch.nn.Linear(4, 2))

    def forward(self, inputs):
        return self.classifier(self.features(inputs.mean((2, 3))))


def test_training_stages_keep_batch_norm_statistics_frozen():
    model = TinyClassifier()
    set_training_stage(model, head_only=True)
    assert not any(parameter.requires_grad for parameter in model.features.parameters())
    assert all(parameter.requires_grad for parameter in model.classifier.parameters())
    assert not model.features[1].training and model.classifier.training
    set_training_stage(model, head_only=False)
    assert all(parameter.requires_grad for parameter in model.parameters())
    assert not model.features[1].training


def test_accumulation_matches_large_weighted_batches_including_partial_window():
    torch.manual_seed(12)
    model = torch.nn.Linear(3, 2)
    expected = copy.deepcopy(model)
    inputs, targets = torch.randn(8, 3), torch.tensor([0, 0, 1, 1, 1, 1, 0, 1])
    weights = torch.tensor([2.0, 0.5])
    config = dict(accumulation_steps=3, max_grad_norm=1e9, log_every_batches=100)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.05)
    training.train_epoch(model, DataLoader(TensorDataset(inputs, targets), batch_size=2), optimizer,
                         torch.amp.GradScaler('cuda', enabled=False), torch.device('cpu'), weights, config, Mock())
    reference = torch.optim.SGD(expected.parameters(), lr=0.05)
    for start, stop in [(0, 6), (6, 8)]:
        reference.zero_grad()
        loss = torch.nn.functional.cross_entropy(expected(inputs[start:stop]), targets[start:stop], weight=weights, reduction='sum') / (stop - start)
        loss.backward()
        reference.step()
    for actual, wanted in zip(model.parameters(), expected.parameters()):
        torch.testing.assert_close(actual, wanted)


def test_validation_threshold_targets_recall_without_access_to_test_data():
    result = training.choose_threshold([0, 0, 1, 1], [0.1, 0.4, 0.5, 0.9], 0.95)
    assert result['balanced_accuracy'] == 1 and result['sensitivity'] == 1
    assert 0.4 < result['threshold'] < 0.5


def tiny_manifest(tmp_path):
    rows = {'train': [], 'val': [], 'test': []}
    for split_index, split in enumerate(rows):
        for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
            for index in range(2):
                path = tmp_path / f'{split}_{target}_{index}.png'
                Image.new('L', (32, 32), 30 + 80 * target + 3 * index + 7 * split_index).save(path)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                rows[split].append(dict(path=path.name, label=label, sha256=digest,
                                        pixel_sha256=f'{split}-{target}-{index}', candidate_subject=path.stem, group=path.stem))
    manifest = dict(schema_version=1, source_root=str(tmp_path), splits=rows)
    manifest['manifest_sha256'] = digest_json(manifest)
    return manifest


def test_modified_images_and_manifest_tampering_stop_training(tmp_path):
    manifest = tiny_manifest(tmp_path)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    load_manifest(path)
    dataset = training.ManifestDataset(manifest, tmp_path, 'train', image_transforms(32))
    assert dataset[0][0].shape == (3, 32, 32)
    (tmp_path / manifest['splits']['train'][0]['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed after preparation'):
        dataset[0]
    with pytest.raises(ValueError, match='changed after preparation'):
        load_manifest(path)
    manifest['splits']['train'][0]['label'] = 'PNEUMONIA'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='digest'):
        load_manifest(path)


def test_tiny_synthetic_checkpoint_resume_matches_uninterrupted_run(tmp_path, monkeypatch):
    # Only this tiny synthetic network is optimized in tests; no real-image/backbone training.
    manifest = tiny_manifest(tmp_path)
    config = dict(image_size=32, resize_mode='letterbox', batch_size=2, accumulation_steps=2,
                  epochs=2, head_warmup_epochs=0, head_learning_rate=0.001, backbone_learning_rate=0.0001,
                  weight_decay=0.0001, early_stopping_patience=7, early_stopping_min_delta=0.0001,
                  freeze_batch_norm=True, mixed_precision=False, max_grad_norm=1.0, seed=42,
                  log_every_batches=10, validation_min_sensitivity=0.95, num_workers=0)
    monkeypatch.setattr(training, 'ROOT', tmp_path)
    monkeypatch.setattr(training, 'select_device', lambda: torch.device('cpu'))
    monkeypatch.setattr(training, 'build_classifier', lambda *_, **__: TinyClassifier())
    original = training.train_epoch
    calls = 0

    def interrupt_after_one(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt()
        return original(*args, **kwargs)

    monkeypatch.setattr(training, 'train_epoch', interrupt_after_one)
    resumed = tmp_path / 'resumed'
    with pytest.raises(KeyboardInterrupt):
        training.train_candidate('densenet121', config, manifest, tmp_path, resumed)
    assert torch.load(resumed / 'last.pt', weights_only=True)['epoch'] == 1
    monkeypatch.setattr(training, 'train_epoch', original)
    training.train_candidate('densenet121', config, manifest, tmp_path, resumed, resumed / 'last.pt')
    training.train_candidate('densenet121', config, manifest, tmp_path, tmp_path / 'uninterrupted')
    actual = torch.load(resumed / 'best.pt', weights_only=True)
    expected = torch.load(tmp_path / 'uninterrupted/best.pt', weights_only=True)
    assert actual['finalized'] and actual['threshold_source'].startswith('validation only')
    for key in actual['model_state_dict']:
        torch.testing.assert_close(actual['model_state_dict'][key], expected['model_state_dict'][key], rtol=0, atol=0)


def test_comparison_records_unfinished_candidates_and_ranks_by_validation(tmp_path):
    from scripts.train_models import update_comparison
    (tmp_path / 'suite_plan.json').write_text(json.dumps({'models': ['densenet121', 'efficientnet_b0']}))
    for index, name in enumerate(('densenet121', 'efficientnet_b0')):
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'validation_summary.json').write_text(json.dumps(dict(
            architecture=name, manifest_sha256='same', selection_metric_value=0.9 + index * 0.01,
            validation_loss=0.3, checkpoint=f'{name}/best.pt')))
        update_comparison(tmp_path)
        comparison = json.loads((tmp_path / 'comparison.json').read_text())
        assert comparison['pending_candidates'] == (['efficientnet_b0'] if index == 0 else [])
    assert comparison['recommended_checkpoint'] == 'efficientnet_b0/best.pt'


def test_final_evaluation_rejects_pending_candidate_before_loading_checkpoint(tmp_path, monkeypatch):
    from scripts import evaluate_experiment
    suite = tmp_path / 'data/experiments/example'
    suite.mkdir(parents=True)
    (suite / 'comparison.json').write_text(json.dumps({'pending_candidates': ['efficientnet_b0']}))
    monkeypatch.setattr(evaluate_experiment, 'ROOT', tmp_path)
    monkeypatch.setattr(evaluate_experiment.sys, 'argv', ['evaluate_experiment.py', '--suite', str(suite)])
    with pytest.raises(ValueError, match='Finish planned candidates'):
        evaluate_experiment.main()
