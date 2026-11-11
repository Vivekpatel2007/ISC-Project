"""Protect calibration data separation, frozen decisions, and external-cohort checks."""

import csv
import hashlib
import io
import json
from pathlib import Path
from threading import Lock
import zipfile

import numpy as np
from PIL import Image, PngImagePlugin
import pytest
import torch

from scripts.calibrate_saved_logits import calibrate
from scripts.prepare_external_validation import prepare
from scripts import evaluate_external_validation
from src.data_protocol import digest_json
from src.postprocessing import fit_temperature, probability_quality, probability_to_margin, sigmoid, validate_profile


def test_temperature_fit_improves_fit_nll_without_changing_ranking_or_boundary():
    truth = np.array([0] * 20 + [1] * 20)
    margins = np.array([-10.] * 18 + [5., 10.] + [10.] * 18 + [-5., -10.])
    result = fit_temperature(truth, margins)
    assert result['temperature'] > 1
    assert probability_quality(truth, margins, result['temperature'])['negative_log_likelihood'] < probability_quality(truth, margins)['negative_log_likelihood']
    assert np.array_equal(np.argsort(margins), np.argsort(margins / result['temperature']))
    boundary = probability_to_margin(.9)
    assert np.array_equal(margins >= boundary, sigmoid(margins / result['temperature']) >= sigmoid(boundary / result['temperature']))
    assert np.isfinite(sigmoid([-1000., 1000.])).all()
    for invalid in (0, 1, float('nan'), True, '0.9', None, []):
        with pytest.raises(ValueError):
            probability_to_margin(invalid)


class ExternalTiny(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.register_buffer('scale', torch.tensor(2.))

    def forward(self, inputs):
        value = inputs.mean((1, 2, 3)) * self.scale
        return torch.stack([-value, value], 1)


def pixel_hash(payload):
    with Image.open(io.BytesIO(payload)) as image:
        rgb = image.convert('RGB')
        return hashlib.sha256(f'{rgb.width}x{rgb.height}:RGB:'.encode() + rgb.tobytes()).hexdigest()


def fixtures(tmp_path):
    artifact = tmp_path / 'model'
    folder = artifact / 'densenet121'
    folder.mkdir(parents=True)
    splits = {}
    for split in ('train', 'val', 'calibration', 'test'):
        splits[split] = []
        for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
            for index in range(20):
                key = f'{split}_{label}_{index}'
                splits[split].append(dict(path=key + '.png', label=label, sha256=key, pixel_sha256=key,
                                          candidate_subject=key, group=key))
    known = io.BytesIO()
    Image.new('RGB', (32, 32), (33, 33, 33)).save(known, format='PNG')
    payload = known.getvalue()
    excluded = dict(path='excluded-known.png', label='NORMAL', sha256=hashlib.sha256(payload).hexdigest(),
                    pixel_sha256=pixel_hash(payload), group='excluded', candidate_subject='excluded')
    manifest = dict(schema_version=1, source_root='unavailable-original-source', splits=splits, excluded=[excluded])
    manifest['manifest_sha256'] = digest_json(manifest)
    (folder / 'split_manifest.json').write_text(json.dumps(manifest))
    state = dict(model_state_dict=ExternalTiny().state_dict(), architecture='densenet121', finalized=True,
                 manifest_sha256=manifest['manifest_sha256'], threshold=.9, class_names=['NORMAL', 'PNEUMONIA'],
                 class_to_idx={'NORMAL': 0, 'PNEUMONIA': 1}, image_size=32,
                 normalization={'mean': [.485, .456, .406], 'std': [.229, .224, .225]},
                 preprocessing={'resize_mode': 'letterbox'}, training_config={'mixed_precision': False})
    torch.save(state, folder / 'best.pt')
    sha = hashlib.sha256((folder / 'best.pt').read_bytes()).hexdigest()
    selected = dict(architecture='densenet121', checkpoint_sha256=sha, manifest_sha256=manifest['manifest_sha256'],
                    validation_at_selected_threshold={'threshold': .9})
    (artifact / 'comparison.json').write_text(json.dumps({'candidates': [selected], 'pending_candidates': []}))
    files = {}
    for split in ('calibration', 'val'):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=['path', 'label', 'sha256', 'logit_margin', 'logit_normal', 'logit_pneumonia', 'probability_float32'])
        writer.writeheader()
        for index, row in enumerate(splits[split]):
            target = int(row['label'] == 'PNEUMONIA')
            margin = (-10 if target == 0 else 10) if index % 20 < 18 else (5 if target == 0 else -5)
            writer.writerow(dict(path=row['path'], label=row['label'], sha256=row['sha256'], logit_margin=margin,
                                 logit_normal=0., logit_pneumonia=margin, probability_float32=float(sigmoid(margin))))
        files[split + '_predictions.csv'] = stream.getvalue().encode()
    files['diagnostic_results.json'] = json.dumps(dict(checkpoint_sha256=sha, manifest_sha256=manifest['manifest_sha256'], threshold=.9)).encode()
    files['test_predictions.csv'] = b'Unparsed benchmark data: must never affect this fit'
    return artifact, manifest, sha, payload, files


def diagnostic_zip(path, files, sha, manifest_sha):
    index = dict(schema_version=1, kind='fixed_checkpoint_diagnostic', checkpoint_sha256=sha, manifest_sha256=manifest_sha,
                 files={name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()})
    with zipfile.ZipFile(path, 'w') as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
        archive.writestr('diagnostic_bundle.json', json.dumps(index))


def test_profile_is_independent_of_benchmark_scores_and_binds_to_checkpoint(tmp_path):
    artifact, manifest, sha, _, files = fixtures(tmp_path)
    first, second = tmp_path / 'first.zip', tmp_path / 'second.zip'
    diagnostic_zip(first, files, sha, manifest['manifest_sha256'])
    profile, assessment = calibrate(first, artifact, tmp_path / 'first-output')
    files['test_predictions.csv'] = b'Entirely different and intentionally invalid benchmark CSV'
    diagnostic_zip(second, files, sha, manifest['manifest_sha256'])
    other, other_assessment = calibrate(second, artifact, tmp_path / 'second-output')
    assert profile['temperature'] == other['temperature']
    assert profile['fit_paths'] == other['fit_paths'] and assessment == other_assessment
    assert not set(profile['fit_paths']) & set(profile['check_paths'])
    assert len(profile['fit_paths']) + len(profile['check_paths']) == 40
    assert validate_profile(profile, sha) is profile
    with pytest.raises(ValueError, match='another checkpoint'):
        validate_profile(profile, 'wrong-model')
    with pytest.raises(ValueError, match='original decision'):
        validate_profile(dict(profile, decision_margin_threshold=42.), sha)


def external_csv(tmp_path):
    root = tmp_path / 'external'
    root.mkdir()
    for name, value in [('normal.png', 50), ('pneumonia.png', 190)]:
        Image.new('RGB', (40, 36), (value, value, value)).save(root / name)
    labels = tmp_path / 'labels.csv'
    labels.write_text('path,label,patient_id,source_id\nnormal.png,NORMAL,patient-a,new-source\npneumonia.png,PNEUMONIA,patient-b,new-source\n')
    return root, labels


def test_external_manifest_refuses_excluded_reference_pixels_and_duplicate_images(tmp_path):
    artifact, _, _, known, _ = fixtures(tmp_path)
    root, labels = external_csv(tmp_path)
    with Image.open(io.BytesIO(known)) as image:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('different_encoding', 'same pixels')
        image.save(root / 'normal.png', pnginfo=metadata)
    with pytest.raises(ValueError, match='Known development/benchmark'):
        prepare(labels, root, artifact, tmp_path / 'rejected.json', 'New candidate cohort, source review pending')
    assert not (tmp_path / 'rejected.json').exists()


def test_external_evaluation_has_no_fitting_and_preserves_source_artifacts(tmp_path, monkeypatch):
    artifact, original, sha, _, files = fixtures(tmp_path)
    root, labels = external_csv(tmp_path)
    manifest_path = tmp_path / 'external-manifest.json'
    manifest = prepare(labels, root, artifact, manifest_path, 'Synthetic test source, not real patient data')
    assert manifest['counts'] == {'NORMAL': 1, 'PNEUMONIA': 1}
    assert manifest['independence_status'].startswith('candidate_only')
    before = (artifact / 'densenet121/best.pt').read_bytes()
    monkeypatch.setattr(evaluate_external_validation, 'select_device', lambda _: torch.device('cpu'))
    monkeypatch.setattr(evaluate_external_validation, 'build_classifier', lambda *_, **__: ExternalTiny())
    report = evaluate_external_validation.evaluate(artifact, manifest_path, tmp_path / 'external-report')
    assert report['evaluation_role'] == 'candidate_external_validation'
    assert report['profile_sha256'] is None and report['temperature'] == 1
    assert (artifact / 'densenet121/best.pt').read_bytes() == before
    archive = tmp_path / 'diagnostic.zip'
    diagnostic_zip(archive, files, sha, original['manifest_sha256'])
    profile, _ = calibrate(archive, artifact, tmp_path / 'calibration')
    calibrated = evaluate_external_validation.evaluate(artifact, manifest_path, tmp_path / 'profile-external-report',
                                                        tmp_path / 'calibration/postprocessing_profile.json')
    assert calibrated['temperature'] == profile['temperature']
    assert calibrated['profile_sha256']
    assert calibrated['raw_margin_metrics'] == report['raw_margin_metrics']
    with pytest.raises(ValueError, match='new output'):
        evaluate_external_validation.evaluate(artifact, manifest_path, tmp_path / 'external-report')


def test_api_adds_stable_score_details_without_changing_legacy_prediction():
    from src.api.model_service import DenseNetInferenceEngine
    engine = object.__new__(DenseNetInferenceEngine)
    engine.device = torch.device('cpu')
    engine.threshold, engine.best_epoch = .4, 5
    engine._prediction_lock = Lock()
    engine.validate_and_decode_image = lambda _: Image.new('RGB', (32, 32))
    engine.transform = lambda _: torch.zeros(3, 32, 32)
    engine.model = lambda _: torch.tensor([[0., 30.]])
    result = engine.predict(b'synthetic')
    assert result['prediction'] == 'PNEUMONIA' and result['pneumonia_probability'] == 1
    assert result['logit_margin'] == 30 and result['log_probability_normal'] == pytest.approx(-30)
    assert result['probabilities_calibrated'] is False


def test_validation_exposes_margin_auc_when_probability_order_is_lost():
    from torch.utils.data import DataLoader, TensorDataset
    from src.training import validate
    logits = torch.tensor([[0., 20.], [0., 21.], [0., 30.], [0., 31.]])
    loader = DataLoader(TensorDataset(logits, torch.tensor([0, 0, 1, 1])), batch_size=2)
    result = validate(torch.nn.Identity(), loader, torch.device('cpu'), False)
    assert result['roc_auc'] == .5 and result['roc_auc_logit_margin'] == 1


def test_comparison_refuses_mixed_ranking_score_spaces(tmp_path):
    from scripts.train_models import update_comparison
    for name, space in [('densenet121', 'val_roc_auc'), ('efficientnet_b0', 'val_logit_margin_auc')]:
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'validation_summary.json').write_text(json.dumps(dict(
            manifest_sha256='same', selection_metric=space, selection_metric_value=.9, validation_loss=.1)))
    with pytest.raises(ValueError, match='probability-AUC and logit-margin'):
        update_comparison(tmp_path)


def test_external_manifest_rejects_new_cohort_duplicates(tmp_path):
    artifact, _, _, _, _ = fixtures(tmp_path)
    root, labels = external_csv(tmp_path)
    with Image.open(root / 'normal.png') as image:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('new-container', 'same pixels')
        image.save(root / 'pneumonia.png', pnginfo=metadata)
    with pytest.raises(ValueError, match='Duplicate external image'):
        prepare(labels, root, artifact, tmp_path / 'duplicate-manifest.json', 'Synthetic duplicate test')
