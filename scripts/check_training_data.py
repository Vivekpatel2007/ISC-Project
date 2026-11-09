"""Check every prepared image without loading models, training, or changing sources."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_protocol import load_manifest, source_file


def check_images(manifest, root, passes=2, progress=print):
    if passes < 1:
        raise ValueError('Passes must be positive.')
    rows = [(split, row) for split, items in manifest['splits'].items() for row in items]
    scans = []
    for number in range(1, passes + 1):
        problems = []
        for index, (split, row) in enumerate(rows, 1):
            path = source_file(root, row['path'])
            try:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as error:
                problems.append(dict(split=split, path=row['path'], expected_sha256=row['sha256'],
                                     error=f'{type(error).__name__}: {error}'))
            else:
                if actual != row['sha256']:
                    problems.append(dict(split=split, path=row['path'], expected_sha256=row['sha256'],
                                         actual_sha256=actual))
            if index % 1000 == 0:
                progress(f'Pass {number}/{passes}: checked {index}/{len(rows)} images ...')
        scans.append(dict(pass_number=number, checked=len(rows), problems=problems))
        progress(f'Pass {number}/{passes}: {len(problems)} integrity failures.')
    return dict(checked_at=datetime.now(timezone.utc).isoformat(),
                manifest_sha256=manifest['manifest_sha256'], source_root=str(root), scans=scans,
                passed=not any(scan['problems'] for scan in scans))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/prepared/screening-v1/manifest.json')
    parser.add_argument('--passes', type=int, default=2)
    parser.add_argument('--output', type=Path, help='New JSON report path; existing reports are never overwritten')
    args = parser.parse_args(argv)
    if args.passes < 1:
        parser.error('--passes must be positive.')
    output = args.output or ROOT / 'data/review' / (
        'training_integrity_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    if output.exists():
        parser.error('Choose a new report path; existing evidence is preserved.')
    manifest, root = load_manifest(args.manifest, verify_files=False)
    report = check_images(manifest, root, args.passes, progress=lambda message: print(message, flush=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2)
    for path in sorted({row['path'] for scan in report['scans'] for row in scan['problems']}):
        print('FAIL:', path)
    print('Report:', output)
    if not report['passed']:
        print('Do not train or regenerate the manifest to bypass these failures. '
              'Restore exact originals matching the expected hashes, then check again.')
        return 2
    print('PASS: every included source matches the prepared manifest. '
          'No images, manifests, or model checkpoints were changed. No training was started.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
