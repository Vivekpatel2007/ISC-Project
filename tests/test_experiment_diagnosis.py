"""The diagnosis must use verified metadata and the original test operating point."""

import hashlib
import json
import zipfile

import pytest

from scripts.diagnose_experiment import diagnose
from src.data_protocol import digest_json
from src.training import metrics


def fixture_bundle(tmp_path, wrong_test_threshold=False):
    splits, audited = {}, []
    for split in ('train', 'val', 'test'):
        splits[split] = []
        for target, label in enumerate(('NORMAL', 'PNEUMONIA')):
            key = f'{split}-{label}'
            filename = 'IM-0001-0001.jpeg' if target == 0 else 'person1_bacteria_1.jpeg'
            path = f'{split}/{label}/{filename}'
            row = dict(path=path, label=label, sha256=key, pixel_sha256=key, group=key, candidate_subject=key)
            splits[split].append(row)
            audited.append(dict(row, width=100, height=100, bytes=1000 if target else 9000))
    # Unmatched metadata must be excluded, not silently accepted as the matching file.
    audited[0]['sha256'] = 'other-version'
    manifest = dict(schema_version=1, source_root='unused', splits=splits)
    manifest['manifest_sha256'] = digest_json(manifest)
    weights = b'not deserialized'
    sha = hashlib.sha256(weights).hexdigest()
    fixed = metrics([0, 1], [.8, .9], .5)
    test = dict(targets=[0, 1], scores=[.8, .9], paths=[r['path'] for r in splits['test']],
                checkpoint_sha256=sha, metrics=metrics([0, 1], [.8, .9], .95) if wrong_test_threshold else fixed)
    candidate = dict(architecture='densenet121', checkpoint_sha256=sha, validation_at_selected_threshold={'threshold': .5})
    files = {
        'suite/suite_plan.json': json.dumps({'models': ['densenet121']}).encode(),
        'suite/comparison.json': json.dumps({'candidates': [candidate], 'pending_candidates': []}).encode(),
        'suite/densenet121/best.pt': weights,
        'suite/densenet121/split_manifest.json': json.dumps(manifest).encode(),
        'suite/densenet121/validation_predictions.json': json.dumps({'targets': [0, 1], 'scores': [.1, .9]}).encode(),
        'suite/final_test_results.json': json.dumps(test).encode(),
    }
    index = dict(schema_version=1, suite_name='synthetic', files={k: hashlib.sha256(v).hexdigest() for k, v in files.items()})
    archive = tmp_path / 'bundle.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name, payload in files.items():
            z.writestr(name, payload)
        z.writestr('bundle.json', json.dumps(index))
    audit = tmp_path / 'audit.json'
    audit.write_text(json.dumps({'images': audited}))
    return archive, audit


def test_diagnosis_excludes_unmatched_metadata_and_reuses_original_threshold(tmp_path):
    archive, audit = fixture_bundle(tmp_path)
    report = diagnose(archive, audit)
    assert report['split_metadata']['train']['matching_audit_rows'] == 1
    assert report['unmatched_metadata'] == [{'split': 'train', 'path': 'train/NORMAL/IM-0001-0001.jpeg'}]
    assert 'test' not in report['proxy_auc']
    assert report['proxy_auc']['val']['negative_file_bytes'] == 1
    assert report['fixed_threshold_results']['test']['metrics']['threshold'] == .5
    assert report['fixed_threshold_results']['test']['metrics']['confusion_matrix']['FP'] == 1
    assert len(report['fixed_threshold_results']['test']['errors']) == 1


def test_diagnosis_refuses_metrics_generated_with_another_threshold(tmp_path):
    archive, audit = fixture_bundle(tmp_path, wrong_test_threshold=True)
    with pytest.raises(ValueError, match='original threshold'):
        diagnose(archive, audit)
