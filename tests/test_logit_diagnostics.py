"""Test numerical saturation, frozen decisions, read-only inspection, and notebook safety."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
from PIL import Image
import pytest
import torch
from torch.utils.data import DataLoader, TensorDataset

from scripts import inspect_checkpoint
from src.data_protocol import DatasetIntegrityError, digest_json
from src.scoring import collect_logits, metrics, score_logits


def test_margin_auc_retains_order_when_probabilities_saturate_without_changing_decisions():
    logits = [[0., 20.], [0., 21.], [0., 30.], [0., 31.]]
    result = score_logits([0, 0, 1, 1], logits, .9999873042106628)
    assert result['scores'] == [1., 1., 1., 1.]
    assert result['metrics_at_saved_threshold']['roc_auc'] == .5
    assert result['roc_auc_logit_margin'] == 1.
    assert result['metrics_at_saved_threshold']['confusion_matrix'] == dict(TN=0, FP=2, FN=0, TP=2)
    assert result['loss_from_logits'] == pytest.approx(10.25)
    assert np.isfinite(result['log_probabilities']).all()


def test_score_validation_and_original_device_probabilities_are_preserved():
    result = score_logits([0, 1], [[0., 20.], [0., 30.]], .99, [.98, 1.])
    assert result['metrics_at_saved_threshold']['accuracy'] == 1
    assert result['scores'][0] == pytest.approx(.98)
    for labels, logits in [([0, 1], [[0., float('inf')], [0., 1.]]), ([0, 1], [[0., 1., 2.]]),
                           ([0, 0], [[0., 1.], [0., 2.]])]:
        with pytest.raises(ValueError):
            score_logits(labels, logits, .5)
    with pytest.raises(ValueError, match='probability'):
        score_logits([0, 1], [[0., 1.], [0., 2.]], .5, [float('nan'), .8])


def test_collector_never_enables_gradients_or_updates_parameters():
    model = torch.nn.Linear(2, 2)
    before = {key: value.clone() for key, value in model.state_dict().items()}
    model.train()
    inputs, targets = torch.randn(4, 2), torch.tensor([0, 0, 1, 1])
    actual, logits, probabilities = collect_logits(model, DataLoader(TensorDataset(inputs, targets), batch_size=2),
                                                  torch.device('cpu'), progress=lambda _: None)
    assert actual == targets.tolist() and len(logits) == len(probabilities) == 4
    assert not model.training and all(parameter.grad is None for parameter in model.parameters())
    assert all(torch.equal(value, before[key]) for key, value in model.state_dict().items())


class FrozenTiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer('offset', torch.tensor(30.))

    def forward(self, inputs):
        margin = self.offset + 2 * inputs.mean((1, 2, 3))
        return torch.stack([torch.zeros_like(margin), margin], 1)


def diagnostic_source(tmp_path):
    artifact = tmp_path / 'saved-suite'
    model_dir = artifact / 'densenet121'
    model_dir.mkdir(parents=True)
    data = tmp_path / 'source-images'
    data.mkdir()
    splits = {}
    for split_index, split in enumerate(('train', 'val', 'calibration', 'test')):
        splits[split] = []
        for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
            for index in range(2):
                key = f'{split}_{target}_{index}'
                path = data / (key + '.png')
                Image.new('L', (32 + index, 32), 20 + target * 80 + 5 * split_index + index).save(path)
                splits[split].append(dict(path=path.name, label=label, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                          pixel_sha256=key, group=key, candidate_subject=key))
    manifest = dict(schema_version=1, source_root='/original/read-only/mount', splits=splits)
    manifest['manifest_sha256'] = digest_json(manifest)
    (model_dir / 'split_manifest.json').write_text(json.dumps(manifest))
    state = dict(architecture='densenet121', manifest_sha256=manifest['manifest_sha256'], threshold=.9,
                 finalized=True, threshold_split='calibration', class_names=['NORMAL', 'PNEUMONIA'],
                 class_to_idx={'NORMAL': 0, 'PNEUMONIA': 1}, image_size=32,
                 normalization={'mean': [.485, .456, .406], 'std': [.229, .224, .225]},
                 preprocessing={'resize_mode': 'letterbox'}, training_config={'mixed_precision': False},
                 model_state_dict=FrozenTiny().state_dict())
    torch.save(state, model_dir / 'best.pt')
    sha = hashlib.sha256((model_dir / 'best.pt').read_bytes()).hexdigest()
    selected = dict(architecture='densenet121', manifest_sha256=manifest['manifest_sha256'],
                    checkpoint_sha256=sha, validation_at_selected_threshold={'threshold': .9})
    (artifact / 'comparison.json').write_text(json.dumps({'candidates': [selected], 'pending_candidates': []}))
    (artifact / 'suite_plan.json').write_text(json.dumps({'models': ['densenet121']}))
    predictions = {'targets': [0, 0, 1, 1], 'scores': [1., 1., 1., 1.]}
    (model_dir / 'validation_predictions.json').write_text(json.dumps(predictions))
    (model_dir / 'calibration_predictions.json').write_text(json.dumps(predictions))
    final = dict(predictions, paths=[row['path'] for row in splits['test']], checkpoint_sha256=sha,
                 manifest_sha256=manifest['manifest_sha256'])
    (artifact / 'final_test_results.json').write_text(json.dumps(final))
    return artifact, data, manifest


def test_full_inspection_changes_no_artifacts_and_exports_verified_csvs(tmp_path, monkeypatch):
    artifact, data, manifest = diagnostic_source(tmp_path)
    monkeypatch.setattr(inspect_checkpoint, 'build_classifier', lambda *_, **__: FrozenTiny())
    original = {path: path.read_bytes() for path in artifact.rglob('*') if path.is_file()}
    report = inspect_checkpoint.inspect(artifact, data, tmp_path / 'diagnostic', True, 2, 'cpu', plots=True)
    assert set(report['splits']) == {'val', 'calibration', 'test'}
    assert report['original_source_root'] == '/original/read-only/mount'
    assert report['verified_source_root'] == str(data)
    for result in report['splits'].values():
        assert result['roc_auc_logit_margin'] == 1
        assert result['metrics_at_saved_threshold']['roc_auc'] == .5
        assert result['reference_comparison']['changed_decisions_at_saved_threshold'] == 0
    assert report['splits']['test']['evaluation_role'] == 'previously_reviewed_benchmark'
    assert all(path.read_bytes() == payload for path, payload in original.items())
    assert (tmp_path / 'diagnostic/false_positive_examples.png').exists()
    archive = inspect_checkpoint.export_diagnostics(tmp_path / 'diagnostic', tmp_path / 'diagnostic.zip')
    assert inspect_checkpoint.verify_diagnostics(archive)['kind'] == 'fixed_checkpoint_diagnostic'
    with zipfile.ZipFile(archive) as z:
        index = json.loads(z.read('diagnostic_bundle.json'))
        for name, sha in index['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == sha
        assert 'test_predictions.csv' in z.namelist()
    corrupt = tmp_path / 'corrupt-diagnostic.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, 'w') as target:
        for info in source.infolist():
            target.writestr(info.filename, b'changed' if info.filename == 'test_predictions.csv' else source.read(info))
    with pytest.raises(ValueError, match='checksum mismatch'):
        inspect_checkpoint.verify_diagnostics(corrupt)
    with pytest.raises(ValueError, match='new diagnostic'):
        inspect_checkpoint.inspect(artifact, data, tmp_path / 'diagnostic', plots=False)


def test_inspection_requires_original_bytes_and_preserves_benchmark_opt_out(tmp_path, monkeypatch):
    artifact, data, manifest = diagnostic_source(tmp_path)
    monkeypatch.setattr(inspect_checkpoint, 'build_classifier', lambda *_, **__: FrozenTiny())
    report = inspect_checkpoint.inspect(artifact, data, tmp_path / 'development-only', False, 2, 'cpu', plots=False)
    assert set(report['splits']) == {'val', 'calibration'}
    assert not (tmp_path / 'development-only/test_predictions.csv').exists()
    with pytest.raises(ValueError, match='outside the source'):
        inspect_checkpoint.inspect(artifact, data, data / 'bad-output', plots=False)
    row = manifest['splits']['train'][0]
    (data / row['path']).write_bytes(b'changed source')
    with pytest.raises(DatasetIntegrityError, match='changed after preparation'):
        inspect_checkpoint.inspect(artifact, data, tmp_path / 'must-not-exist', plots=False)
    assert not (tmp_path / 'must-not-exist').exists()


def test_artifact_zip_and_unpacked_folder_are_discovered_as_the_same_checkpoint(tmp_path):
    artifact, _, _ = diagnostic_source(tmp_path)
    inputs = tmp_path / 'kaggle-inputs'
    inputs.mkdir()
    files = {'suite/' + p.relative_to(artifact).as_posix(): p.read_bytes()
             for p in artifact.rglob('*') if p.is_file()}
    index = dict(schema_version=1, suite_name='test-suite',
                 files={name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()})
    archive = inputs / 'pulmoscan_models.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name, payload in files.items():
            z.writestr(name, payload)
        z.writestr('bundle.json', json.dumps(index))
    unpacked = inputs / 'unpacked'
    for name, payload in files.items():
        target = unpacked / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (unpacked / 'bundle.json').write_text(json.dumps(index))
    path = Path(__file__).resolve().parent.parent / 'kaggle/diagnostic_runtime.py'
    spec = importlib.util.spec_from_file_location('diagnostic_runtime_test', path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    assert runtime.discover_artifact(inputs, 'test-suite') == unpacked
    reader = inspect_checkpoint.ArtifactReader(archive)
    try:
        assert reader.json('comparison.json')['candidates'][0]['architecture'] == 'densenet121'
    finally:
        reader.close()
    with pytest.raises(ValueError, match='Attach the saved'):
        runtime.discover_artifact(inputs, 'missing-suite')


def load_builder():
    path = Path(__file__).resolve().parent.parent / 'kaggle/build_diagnostics_notebook.py'
    spec = importlib.util.spec_from_file_location('diagnostic_builder_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_notebook_embeds_no_training_entrypoints_and_bootstrap_is_checked(tmp_path, monkeypatch):
    builder = load_builder()
    notebook = builder.build_notebook()
    assert notebook['metadata']['pulmoscan']['mode'] == 'fixed_checkpoint_diagnostic'
    index = notebook['metadata']['pulmoscan']['source_files_sha256']
    assert 'src/training.py' not in index and 'scripts/train_models.py' not in index
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            compile(source, '<diagnostic notebook>', 'exec')
            assert 'train_candidate(' not in source and 'train_models.py' not in source and '.backward(' not in source
    source = ''.join(notebook['cells'][1]['source'])
    workspace = tmp_path / 'diagnostic-workspace'
    source = source.replace("WORKSPACE = Path('/kaggle/working/pulmoscan_diagnostics')", f'WORKSPACE = Path({str(workspace)!r})')
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    exec(compile(source, '<bootstrap>', 'exec'), {})
    assert (workspace / 'src/scoring.py').read_bytes() == (builder.ROOT / 'src/scoring.py').read_bytes()
    (workspace / 'src/scoring.py').write_bytes(b'changed')
    with pytest.raises(ValueError, match='different code'):
        exec(compile(source, '<bootstrap>', 'exec'), {})
