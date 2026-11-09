"""The diagnostic must report all failures and preserve source data and evidence."""

import hashlib
import json

import pytest

from scripts.check_training_data import check_images, main
from src.data_protocol import digest_json


def test_reports_missing_and_modified_images_on_every_pass_without_changes(tmp_path):
    good = tmp_path / 'good.jpeg'
    bad = tmp_path / 'bad.jpeg'
    good.write_bytes(b'original')
    bad.write_bytes(b'changed')
    expected = hashlib.sha256(b'original').hexdigest()
    manifest = dict(manifest_sha256='saved', splits={'train': [
        dict(path='good.jpeg', sha256=expected), dict(path='bad.jpeg', sha256=expected),
        dict(path='missing.jpeg', sha256=expected)]})
    report = check_images(manifest, tmp_path, passes=2, progress=lambda _: None)
    assert not report['passed']
    assert len(report['scans']) == 2
    for scan in report['scans']:
        assert scan['checked'] == 3
        assert [row['path'] for row in scan['problems']] == ['bad.jpeg', 'missing.jpeg']
        assert scan['problems'][0]['expected_sha256'] == expected
        assert scan['problems'][0]['actual_sha256'] == hashlib.sha256(b'changed').hexdigest()
        assert scan['problems'][1]['error'].startswith('FileNotFoundError:')
    assert bad.read_bytes() == b'changed' and good.read_bytes() == b'original'
    assert not (tmp_path / 'missing.jpeg').exists()


def test_rejects_paths_outside_source_root(tmp_path):
    manifest = dict(splits={'train': [dict(path='../outside.jpeg', sha256='irrelevant')]})
    with pytest.raises(ValueError, match='outside its source root'):
        check_images(manifest, tmp_path, progress=lambda _: None)


def test_cli_checks_manifest_and_writes_new_report_without_overwriting(tmp_path):
    splits = {}
    for split in ('train', 'val', 'test'):
        splits[split] = []
        for label in ('NORMAL', 'PNEUMONIA'):
            key = f'{split}_{label}'
            (tmp_path / key).write_bytes(key.encode())
            splits[split].append(dict(path=key, label=label, sha256=hashlib.sha256(key.encode()).hexdigest(),
                                      pixel_sha256=key, group=key, candidate_subject=key))
    manifest = dict(schema_version=1, source_root=str(tmp_path), splits=splits)
    manifest['manifest_sha256'] = digest_json(manifest)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest))
    report = tmp_path / 'report.json'
    args = ['--manifest', str(path), '--output', str(report)]
    assert main(args) == 0
    assert json.loads(report.read_text())['passed']
    original_report = report.read_bytes()
    with pytest.raises(SystemExit):
        main(args)
    assert report.read_bytes() == original_report
    (tmp_path / 'train_NORMAL').write_bytes(b'changed')
    args[-1] = str(tmp_path / 'failed.json')
    assert main(args) == 2
    assert not json.loads((tmp_path / 'failed.json').read_text())['passed']
    manifest['splits']['train'][0]['sha256'] = 'tampered'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='digest'):
        main(['--manifest', str(path), '--output', str(tmp_path / 'tampered.json')])
