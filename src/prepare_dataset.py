"""Prepare source-backed, deduplicated, candidate-group-disjoint split manifests."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.audit_dataset import audit_dataset
from src.data_protocol import CLASSES, digest_json, filename_group, plan_splits, source_file


def extract_patient_id(filename, class_name):
    subject = filename_group(filename, class_name)
    if subject is None:
        raise ValueError(f'Cannot infer a candidate subject ID from {filename}')
    return subject


def prepare_dataset(data_dir, output_dir, train_ratio=0.85, random_seed=42, audit_path=None, previous_audit=None,
                    calibration_ratio=0.0):
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError('Output directory is not empty. Use a new experiment directory; existing manifests are preserved.')
    audit_path = Path(audit_path) if audit_path else data_dir / 'review/dataset_audit.json'
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        if Path(audit['data_root']).resolve() != data_dir:
            raise ValueError('Audit data root does not match the requested source.')
    else:
        audit = audit_dataset(data_dir, progress=lambda text: print(text, flush=True))
    actual = {path.relative_to(data_dir).as_posix()
              for split in ('train', 'val', 'test') for label in CLASSES
              for path in (data_dir / split / label).rglob('*') if path.is_file() and not path.name.startswith('.')}
    if actual != {row['path'] for row in audit['images']}:
        raise ValueError('Source file list differs from the audit. Rerun scripts/audit_dataset.py.')
    for index, row in enumerate(audit['images']):
        if hashlib.sha256(source_file(data_dir, row['path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError(f"Source image changed since audit: {row['path']}")
        if (index + 1) % 1000 == 0:
            print(f'Verified {index + 1} audited source files ...', flush=True)
    changes = []
    if previous_audit:
        previous = json.loads(Path(previous_audit).read_text(encoding='utf-8'))
        old = {row['path']: row for row in previous['images']}
        changes = [dict(path=row['path'], previous_sha256=old[row['path']]['sha256'], sha256=row['sha256'])
                   for row in audit['images'] if row['path'] in old and row['sha256'] != old[row['path']]['sha256']]
    plan = plan_splits(audit, train_ratio, random_seed, [row['path'] for row in changes], calibration_ratio)
    root = data_dir.relative_to(ROOT).as_posix() if data_dir.is_relative_to(ROOT) else str(data_dir)
    manifest = dict(schema_version=1, source_root=root, created_at=datetime.now(timezone.utc).isoformat(),
                    source_audit_sha256=audit['manifest_sha256'], changed_sources=changes, **plan)
    manifest['manifest_sha256'] = digest_json(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / 'manifest.json'
    with destination.open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    print(json.dumps({key: plan[key] for key in ('counts', 'exclusions', 'raw_test_images', 'caveat')}, indent=2))
    print(f'Split manifest: {destination}\nSHA-256: {manifest["manifest_sha256"]}')
    print('No images were moved, copied, edited, or used for training.')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', '--data_dir', type=Path, default=Path('data'))
    parser.add_argument('--output-dir', '--output_dir', type=Path, default=Path('data/prepared/screening-v1'))
    parser.add_argument('--train-ratio', '--train_ratio', type=float, default=0.85)
    parser.add_argument('--seed', '--random_seed', type=int, default=42)
    parser.add_argument('--calibration-ratio', type=float, default=0.0,
                        help='Reserve a disjoint threshold holdout in addition to training and model-selection validation')
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--previous-audit', type=Path, help='Quarantine candidate components whose files changed since this audit.')
    parser.add_argument('--patient_grouping', action='store_true', help='Compatibility flag: grouping is always enabled.')
    parser.add_argument('--deduplicate', action='store_true', help='Compatibility flag: exact-pixel deduplication is always enabled.')
    args = parser.parse_args()
    prepare_dataset(args.data_dir, args.output_dir, args.train_ratio, args.seed, args.audit, args.previous_audit,
                    args.calibration_ratio)


if __name__ == '__main__':
    main()
