"""Audit a candidate external holdout and reject reuse of the project's known images."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image
from scripts.inspect_checkpoint import ArtifactReader
from src.data_protocol import digest_json, source_file


def prepare(labels_csv, data_root, reference_artifact, output, source_description):
    data_root, output = Path(data_root).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(data_root):
        raise ValueError('Choose a new manifest path outside the source images.')
    if not source_description.strip():
        raise ValueError('Record the actual source and label provenance; independence is not inferred from a folder name.')
    reference = ArtifactReader(reference_artifact)
    try:
        comparison = reference.json('comparison.json')
        selected = comparison['candidates'][0]
        original = reference.json(selected['architecture'] + '/split_manifest.json')
        if (digest_json({k: v for k, v in original.items() if k != 'manifest_sha256'}) != original['manifest_sha256']
                or selected['manifest_sha256'] != original['manifest_sha256']):
            raise ValueError('Reference manifest provenance failed.')
        # Include excluded images: repackaging an unused duplicate is not an external source.
        known = [row for rows in original['splits'].values() for row in rows] + original.get('excluded', [])
        known_bytes = {row['sha256'] for row in known}
        known_pixels = {row['pixel_sha256'] for row in known}
        with Path(labels_csv).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            if not {'path', 'label', 'patient_id', 'source_id'} <= set(reader.fieldnames or []):
                raise ValueError('CSV must have path,label,patient_id,source_id columns.')
            records = list(reader)
        rows, seen_paths, seen_bytes, seen_pixels = [], set(), set(), set()
        for item in records:
            if item['label'] not in {'NORMAL', 'PNEUMONIA'} or not item['patient_id'].strip() or not item['source_id'].strip():
                raise ValueError('Every image needs a supported label and explicit source/patient identifiers.')
            path = source_file(data_root, item['path'])
            relative = path.relative_to(data_root).as_posix()
            if relative in seen_paths:
                raise ValueError('Repeated path in external CSV: ' + relative)
            payload = path.read_bytes()
            byte_hash = hashlib.sha256(payload).hexdigest()
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                if (image.format not in {'PNG', 'JPEG'} or min(image.size) < 32 or max(image.size) > 4096
                        or len(payload) > 20 * 1024**2):
                    raise ValueError('External image does not meet the existing input constraints: ' + relative)
                rgb = image.convert('RGB')
                pixel_hash = hashlib.sha256(f'{rgb.width}x{rgb.height}:RGB:'.encode() + rgb.tobytes()).hexdigest()
                width, height = image.size
            if byte_hash in known_bytes or pixel_hash in known_pixels:
                raise ValueError('Known development/benchmark image reused in candidate external holdout: ' + relative)
            if byte_hash in seen_bytes or pixel_hash in seen_pixels:
                raise ValueError('Duplicate external image; review the cohort instead of silently deduplicating: ' + relative)
            seen_paths.add(relative)
            seen_bytes.add(byte_hash)
            seen_pixels.add(pixel_hash)
            rows.append(dict(path=relative, label=item['label'], patient_id=item['patient_id'].strip(),
                             source_id=item['source_id'].strip(), sha256=byte_hash, pixel_sha256=pixel_hash,
                             width=width, height=height, bytes=len(payload)))
        if {row['label'] for row in rows} != {'NORMAL', 'PNEUMONIA'}:
            raise ValueError('Candidate external validation must contain both classes.')
        manifest = dict(schema_version=1, kind='candidate_external_validation', created_at=datetime.now(timezone.utc).isoformat(),
                        source_root=str(data_root), source_description=source_description,
                        reference_manifest_sha256=original['manifest_sha256'],
                        checkpoint_sha256=selected['checkpoint_sha256'],
                        labels_csv_sha256=hashlib.sha256(Path(labels_csv).read_bytes()).hexdigest(), images=rows,
                        counts={label: sum(row['label'] == label for row in rows) for label in ('NORMAL', 'PNEUMONIA')},
                        source_patient_groups=len({(row['source_id'], row['patient_id']) for row in rows}),
                        independence_status='candidate_only_requires_provenance_and_patient_identity_review',
                        caveat='Exact bytes/decoded pixels do not overlap known images. This does not establish verified '
                               'patient independence, exclude near-duplicates, validate labels, or prove source provenance.')
        manifest['manifest_sha256'] = digest_json(manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as handle:
            json.dump(manifest, handle, indent=2)
        return manifest
    finally:
        reference.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--reference-artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-description', required=True)
    args = parser.parse_args(argv)
    manifest = prepare(args.labels, args.data_dir, args.reference_artifact, args.output, args.source_description)
    print('Prepared candidate external validation:', args.output, '| counts:', manifest['counts'])
    print(manifest['caveat'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
