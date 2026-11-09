"""Exercise the portable notebook, audit adapter, resume routing, and artifact transfer."""

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

from PIL import Image
import pytest

from scripts import experiment_bundle
from src.data_protocol import DatasetIntegrityError


def load_helper(name, relative):
    # The source folder is not a package named "kaggle": do not shadow Kaggle's SDK.
    path = Path(__file__).resolve().parent.parent / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_helper('notebook_builder_test', 'kaggle/build_notebook.py')
runtime = load_helper('notebook_runtime_test', 'kaggle/runtime.py')
ROOT, SOURCES, build_notebook = builder.ROOT, builder.SOURCES, builder.build_notebook


def test_notebook_embeds_current_sources_and_all_cells_compile(tmp_path, monkeypatch):
    notebook = build_notebook()
    assert notebook['nbformat'] == 4
    index = notebook['metadata']['pulmoscan']['source_files_sha256']
    assert set(index) == {*SOURCES, 'src/__init__.py', 'scripts/__init__.py'}
    assert not any(name.startswith(('data/', 'models/', 'secure_data/')) or name.endswith('.env') for name in index)
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            compile(''.join(cell['source']), '<notebook cell>', 'exec')
            assert cell['execution_count'] is None and cell['outputs'] == []
    source = ''.join(notebook['cells'][1]['source'])
    workspace = tmp_path / 'workspace'
    source = source.replace("WORKSPACE = Path('/kaggle/working/pulmoscan_training')", f'WORKSPACE = Path({str(workspace)!r})')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    namespace = {}
    exec(compile(source, '<bootstrap>', 'exec'), namespace)
    for name in SOURCES:
        assert (workspace / name).read_bytes() == (ROOT / name).read_bytes()
    assert (workspace / 'source_index.json').is_file()
    # Same bootstrap is safe to rerun; different code cannot silently replace a resumed run.
    exec(compile(source, '<bootstrap>', 'exec'), {})
    (workspace / 'src/modeling.py').write_bytes(b'changed')
    with pytest.raises(ValueError, match='different code'):
        exec(compile(source, '<bootstrap>', 'exec'), {})


def dataset_folders(root):
    for split in ('train', 'val', 'test'):
        for label in ('NORMAL', 'PNEUMONIA'):
            (root / split / label).mkdir(parents=True, exist_ok=True)
    return root


def test_dataset_detection_selects_one_nested_copy_and_refuses_ambiguity(tmp_path):
    root = dataset_folders(tmp_path / 'pneumonia/chest_xray')
    dataset_folders(root / 'chest_xray')
    assert runtime.discover_dataset(tmp_path) == root
    other = dataset_folders(tmp_path / 'other/chest_xray')
    with pytest.raises(ValueError, match='Multiple datasets'):
        runtime.discover_dataset(tmp_path)
    assert runtime.discover_dataset(tmp_path, other) == other
    with pytest.raises(ValueError, match='directly contain'):
        runtime.discover_dataset(tmp_path, tmp_path)


def test_kaggle_prepare_audits_synthetic_sources_and_preserves_resume_identity(tmp_path):
    source = dataset_folders(tmp_path / 'input/chest_xray')
    for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
        for index in range(12):
            name = f'IM-{index:04d}-0001.jpeg' if target == 0 else f'person{index}_bacteria_1.jpeg'
            Image.new('L', (32 + index, 32), 20 + target * 100 + index).save(source / 'train' / label / name)
        name = 'IM-9999-0001.jpeg' if target == 0 else 'person9999_virus_1.jpeg'
        Image.new('L', (33, 35), 70 + target * 100).save(source / 'test' / label / name)
    workspace = tmp_path / 'workspace'
    (workspace / 'kaggle').mkdir(parents=True)
    (workspace / 'kaggle/train_config.json').write_bytes((ROOT / 'kaggle/train_config.json').read_bytes())
    config, manifest = runtime.prepare(workspace, source)
    original = manifest.read_bytes()
    assert json.loads(config.read_text())['batch_size'] == 16
    assert runtime.prepare(workspace, source) == (config, manifest)
    assert manifest.read_bytes() == original
    with pytest.raises(ValueError, match='different config'):
        runtime.prepare(workspace, source, batch_size=8, accumulation_steps=2)
    row = json.loads(manifest.read_text())['splits']['train'][0]
    (source / row['path']).write_bytes(b'changed')
    with pytest.raises(DatasetIntegrityError, match='Expected SHA-256'):
        runtime.prepare(workspace, source)
    assert manifest.read_bytes() == original


def test_notebook_resume_skips_completed_and_routes_incomplete_candidates(tmp_path, monkeypatch):
    from scripts import train_models
    config = tmp_path / 'config.json'
    config.write_bytes((ROOT / 'kaggle/train_config.json').read_bytes())
    suite = tmp_path / 'data/experiments/example'
    dense = suite / 'densenet121'
    dense.mkdir(parents=True)
    (suite / 'suite_plan.json').write_text(json.dumps({'models': ['densenet121', 'efficientnet_b0']}))
    (dense / 'last.pt').write_bytes(b'synthetic placeholder, never loaded')
    calls = []
    monkeypatch.setattr(train_models, 'cli', lambda args: calls.append(args) or 0)
    runtime.run_or_resume(tmp_path, config, 'example')
    assert calls[0] == ['--resume', str(dense / 'last.pt')]
    assert '--models' in calls[1] and 'efficientnet_b0' in calls[1]
    calls.clear()
    (dense / 'validation_summary.json').write_text('{}')
    runtime.run_or_resume(tmp_path, config, 'example')
    assert len(calls) == 1 and 'efficientnet_b0' in calls[0]
    (suite / 'efficientnet_b0').mkdir()
    with pytest.raises(ValueError, match='before a complete epoch'):
        runtime.run_or_resume(tmp_path, config, 'example')


def completed_suite(tmp_path, monkeypatch):
    # Fake checkpoint bytes are never deserialized: this test verifies transfer, not model quality.
    producer = tmp_path / 'producer'
    monkeypatch.setattr(experiment_bundle, 'ROOT', producer)
    for name in SOURCES:
        path = producer / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    suite = producer / 'data/experiments/kaggle-example'
    candidates = []
    for name in ('densenet121', 'efficientnet_b0'):
        folder = suite / name
        folder.mkdir(parents=True)
        payload = name.encode()
        (folder / 'best.pt').write_bytes(payload)
        (folder / 'last.pt').write_bytes(b'resume')
        (folder / 'train.log').write_text('synthetic log')
        candidates.append(dict(architecture=name, checkpoint_sha256=hashlib.sha256(payload).hexdigest()))
    (suite / 'suite_plan.json').write_text(json.dumps({'models': [row['architecture'] for row in candidates]}))
    (suite / 'comparison.json').write_text(json.dumps(dict(candidates=candidates, pending_candidates=[], test_evaluated=False)))
    return suite


def test_bundle_round_trip_preserves_model_bytes_without_overwriting_app(tmp_path, monkeypatch):
    suite = completed_suite(tmp_path, monkeypatch)
    output = tmp_path / 'models.zip'
    experiment_bundle.export_suite(suite, output)
    receipt = experiment_bundle.verify_bundle(output)
    assert not receipt['test_evaluated']
    assert 'suite/densenet121/last.pt' not in receipt['files']
    with pytest.raises(ValueError, match='new archive path'):
        experiment_bundle.export_suite(suite, output)
    consumer = tmp_path / 'consumer'
    monkeypatch.setattr(experiment_bundle, 'ROOT', consumer)
    live = consumer / 'models/live.pth'
    live.parent.mkdir(parents=True)
    live.write_bytes(b'keep current app model')
    imported = experiment_bundle.import_bundle(output)
    assert (imported / 'densenet121/best.pt').read_bytes() == b'densenet121'
    assert (imported / 'training_source/src/modeling.py').is_file()
    assert live.read_bytes() == b'keep current app model'
    with pytest.raises(ValueError, match='already exists'):
        experiment_bundle.import_bundle(output)


def test_bundle_rejects_changed_weights_and_unsafe_paths(tmp_path, monkeypatch):
    suite = completed_suite(tmp_path, monkeypatch)
    good = experiment_bundle.export_suite(suite, tmp_path / 'good.zip', include_resume=True)
    assert 'suite/densenet121/last.pt' in experiment_bundle.verify_bundle(good)['files']
    for filename, name, payload in [('corrupt.zip', 'suite/densenet121/best.pt', b'tampered'),
                                    ('unsafe.zip', '../outside.json', b'{}')]:
        output = tmp_path / filename
        with zipfile.ZipFile(good) as source, zipfile.ZipFile(output, 'w') as target:
            for info in source.infolist():
                target.writestr(info.filename, payload if info.filename == name else source.read(info))
            if name.startswith('../'):
                target.writestr(name, payload)
        with pytest.raises(ValueError, match='checksum failure|Unsafe bundle path'):
            experiment_bundle.verify_bundle(output)


def test_local_cli_reports_integrity_failure_without_claiming_device_cause(monkeypatch, capsys):
    from scripts import train_models
    def fail(_):
        raise DatasetIntegrityError('source changed; expected digest differs')
    monkeypatch.setattr(train_models, 'main', fail)
    assert train_models.cli([]) == 2
    output = capsys.readouterr().err
    assert 'DATASET INTEGRITY FAILURE' in output
    assert 'check_training_data.py' in output
    assert 'does not identify' in output
