"""Export, verify, or import completed experiments; never deploy or deserialize weights."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 4 * 1024**3


def safe_relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError(f'Unsafe bundle path: {name}')
    return path


def export_suite(suite, output, include_resume=False):
    suite, output = Path(suite).resolve(), Path(output).resolve()
    if not suite.is_relative_to((ROOT / 'data/experiments').resolve()):
        raise ValueError('Export only experiment suites under data/experiments/.')
    if output.exists() or output.is_relative_to(suite):
        raise ValueError('Choose a new archive path outside the suite.')
    comparison = json.loads((suite / 'comparison.json').read_text(encoding='utf-8'))
    plan = json.loads((suite / 'suite_plan.json').read_text(encoding='utf-8'))
    if comparison.get('pending_candidates') or set(plan['models']) != {r['architecture'] for r in comparison['candidates']}:
        raise ValueError('Complete every planned candidate before exporting a model bundle.')
    for row in comparison['candidates']:
        safe_relative(row['architecture'])
        checkpoint = (suite / row['architecture'] / 'best.pt').resolve()
        if not checkpoint.is_relative_to(suite) or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != row['checkpoint_sha256']:
            raise ValueError('Checkpoint differs from its completed validation summary.')
    files = {}
    for path in sorted(suite.rglob('*')):
        if path.is_symlink():
            raise ValueError('Linked files are not exported.')
        if path.is_file() and (path.suffix == '.json' or path.name == 'train.log'
                               or path.name == 'best.pt' or (include_resume and path.name == 'last.pt')):
            files['suite/' + path.relative_to(suite).as_posix()] = path
    # Include the exact training implementation, without app secrets, patient data, or local images.
    for relative in ('src/data_protocol.py', 'src/modeling.py', 'src/scoring.py', 'src/training.py', 'src/compute.py',
                     'src/prepare_dataset.py', 'scripts/train_models.py', 'scripts/audit_dataset.py',
                     'scripts/evaluate_experiment.py', 'scripts/check_training_data.py', 'scripts/experiment_bundle.py',
                     'scripts/diagnose_experiment.py'):
        files['source/' + relative] = ROOT / relative
    index = dict(schema_version=1, suite_name=suite.name, created_at=datetime.now(timezone.utc).isoformat(),
                 includes_resume=include_resume, test_evaluated=bool(comparison.get('test_evaluated')),
                 deployment='Not deployed. Review architecture, preprocessing, metrics, and threshold before API integration.',
                 files={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects a previous download/export from replacement.
    with output.open('xb') as handle:
        with zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, path in files.items():
                archive.write(path, name)
            archive.writestr('bundle.json', json.dumps(index, indent=2))
    verify_bundle(output)
    return output


def verify_bundle(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names) or sum(entry.file_size for entry in entries) > MAX_BYTES:
            raise ValueError('Duplicate entries or oversized experiment bundle.')
        for name in names:
            safe_relative(name)
        if 'bundle.json' not in names or archive.getinfo('bundle.json').file_size > 1024**2:
            raise ValueError('Missing or oversized bundle index.')
        index = json.loads(archive.read('bundle.json'))
        suite_name = index.get('suite_name', '')
        if index.get('schema_version') != 1 or len(safe_relative(suite_name).parts) != 1 or suite_name in {'.', '..'}:
            raise ValueError('Unsupported bundle schema or suite name.')
        if set(names) != {'bundle.json', *index['files']}:
            raise ValueError('Archive contents do not match the checksum index.')
        for name, expected in index['files'].items():
            if not (name.startswith('suite/') or name.startswith('source/')):
                raise ValueError('Unexpected bundle entry.')
            digest = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b''):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError(f'Bundle checksum failure: {name}')
        comparison = json.loads(archive.read('suite/comparison.json'))
        plan = json.loads(archive.read('suite/suite_plan.json'))
        candidates = comparison['candidates']
        if not candidates or comparison.get('pending_candidates') or set(plan['models']) != {r['architecture'] for r in candidates}:
            raise ValueError('Bundle contains an incomplete experiment suite.')
        for row in candidates:
            if row['architecture'] not in {'densenet121', 'efficientnet_b0'}:
                raise ValueError('Unsupported candidate architecture.')
            if index['files'].get(f"suite/{row['architecture']}/best.pt") != row['checkpoint_sha256']:
                raise ValueError('Checkpoint index disagrees with validation results.')
    return index


def import_bundle(path):
    index = verify_bundle(path)
    parent = ROOT / 'data/experiments'
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / index['suite_name']
    if destination.exists():
        raise ValueError('This suite already exists locally; nothing was replaced.')
    staging = Path(tempfile.mkdtemp(prefix='.import-', dir=parent))
    try:
        with zipfile.ZipFile(path) as archive:
            # No extractall: every member has already passed containment and checksum checks.
            for name in index['files']:
                relative = safe_relative(name)
                target = staging.joinpath(*relative.parts[1:]) if relative.parts[0] == 'suite' else staging / 'training_source' / Path(*relative.parts[1:])
                if not target.resolve().is_relative_to(staging.resolve()):
                    raise ValueError('Import target escaped its staging directory.')
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open('xb') as output:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: source.read(1024**2), b''):
                        output.write(chunk)
                        digest.update(chunk)
                if digest.hexdigest() != index['files'][name]:
                    raise ValueError('Archive changed during import.')
        (staging / 'import_receipt.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
        os.rename(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export')
    export.add_argument('--suite', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--include-resume', action='store_true')
    for command in ('verify', 'import'):
        child = sub.add_parser(command)
        child.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'export':
        print('Verified model bundle:', export_suite(args.suite, args.output, args.include_resume))
    elif args.command == 'verify':
        index = verify_bundle(args.archive)
        print('PASS bundle checksums:', index['suite_name'])
    else:
        print('Imported experiment:', import_bundle(args.archive))
        print('The current API model and .env are unchanged. Kaggle source paths remain recorded as provenance; '
              'do not edit the manifest merely to evaluate against a different local dataset.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
