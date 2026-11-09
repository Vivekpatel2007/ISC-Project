"""Audit local images and split overlap without moving files or training a model."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import io
from itertools import combinations
import json
from pathlib import Path
import sys

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data_protocol import filename_group

SPLITS = ('train', 'val', 'test')
CLASSES = ('NORMAL', 'PNEUMONIA')


def audit_dataset(root, progress=print):
    root = Path(root).resolve()
    rows, errors, missing = [], [], []
    counts = {split: {label: 0 for label in CLASSES} for split in SPLITS}
    for split in SPLITS:
        for label in CLASSES:
            folder = root / split / label
            if not folder.is_dir():
                missing.append(f'{split}/{label}')
                continue
            for path in sorted(folder.rglob('*')):
                if not path.is_file() or path.name.startswith('.'):
                    continue
                relative = path.relative_to(root).as_posix()
                try:
                    payload = path.read_bytes()
                    with Image.open(io.BytesIO(payload)) as image:
                        image.load()  # JPEG verify() alone does not fully decode pixels.
                        rgb = image.convert('RGB')
                        pixels = hashlib.sha256(
                            f'{rgb.width}x{rgb.height}:RGB:'.encode() + rgb.tobytes()
                        ).hexdigest()
                        row = dict(path=relative, split=split, label=label, bytes=len(payload),
                                   sha256=hashlib.sha256(payload).hexdigest(), pixel_sha256=pixels,
                                   width=image.width, height=image.height, format=image.format, mode=image.mode,
                                   candidate_subject=filename_group(path.name, label))
                    rows.append(row)
                    counts[split][label] += 1
                    if len(rows) % 500 == 0:
                        progress(f'Audited {len(rows)} images ...')
                except (OSError, ValueError, Image.DecompressionBombError) as error:
                    errors.append(dict(path=relative, error=f'{type(error).__name__}: {error}'))

    duplicates = {}
    for field in ('sha256', 'pixel_sha256'):
        groups = defaultdict(list)
        for row in rows:
            groups[row[field]].append(row)
        duplicates[field] = [
            dict(hash=digest, paths=[row['path'] for row in group],
                 splits=sorted({row['split'] for row in group}),
                 labels=sorted({row['label'] for row in group}))
            for digest, group in groups.items() if len(group) > 1
        ]

    overlap = {}
    for left, right in combinations(SPLITS, 2):
        subjects = {}
        for label in CLASSES:
            sets = [{row['candidate_subject'] for row in rows
                     if row['split'] == split and row['label'] == label and row['candidate_subject']}
                    for split in (left, right)]
            shared = sorted(sets[0] & sets[1])
            subjects[label] = dict(count=len(shared), examples=shared[:10])
        overlap[f'{left}/{right}'] = dict(
            candidate_subjects=subjects,
            byte_duplicate_groups=sum(left in g['splits'] and right in g['splits'] for g in duplicates['sha256']),
            pixel_duplicate_groups=sum(left in g['splits'] and right in g['splits'] for g in duplicates['pixel_sha256']),
        )
    incompatible = [row['path'] for row in rows
                    if row['format'] not in {'JPEG', 'PNG'}
                    or min(row['width'], row['height']) < 32 or max(row['width'], row['height']) > 4096
                    or row['bytes'] > 20 * 1024**2]
    # Binding relative filenames to hashes records exactly which downloaded files were audited.
    manifest = '\n'.join(f"{row['path']}:{row['sha256']}" for row in rows)
    return dict(
        created_at=datetime.now(timezone.utc).isoformat(), data_root=str(root),
        counts=counts, total_images=len(rows), total_bytes=sum(row['bytes'] for row in rows),
        missing_folders=missing, decode_errors=errors, api_incompatible_images=incompatible,
        modes=dict(Counter(row['mode'] for row in rows)),
        manifest_sha256=hashlib.sha256(manifest.encode()).hexdigest(),
        overlaps=overlap, duplicates=duplicates,
        unrecognized_subject_filenames=sum(row['candidate_subject'] is None for row in rows),
        interpretation='Filename subject groups are candidates, not verified patient identities. '
                       'Hash checks detect exact bytes/pixels, not near-duplicates or provenance.',
        images=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('data/review/dataset_audit.json'))
    args = parser.parse_args()
    report = audit_dataset(args.data_dir, progress=lambda value: print(value, flush=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    for key in ('counts', 'total_images', 'total_bytes', 'missing_folders', 'decode_errors',
                'api_incompatible_images', 'overlaps', 'unrecognized_subject_filenames', 'manifest_sha256'):
        print(f'{key}: {json.dumps(report[key])}')
    print(f'Report written to {args.output}. No source images were changed.')
    return int(bool(report['missing_folders'] or report['decode_errors'] or not report['total_images']))


if __name__ == '__main__':
    raise SystemExit(main())
