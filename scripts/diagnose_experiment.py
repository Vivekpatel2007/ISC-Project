"""Describe an existing result and dataset metadata; never train or search test thresholds."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from sklearn.metrics import roc_auc_score
from scripts.experiment_bundle import verify_bundle
from src.data_protocol import digest_json, validate_boundaries
from src.training import metrics


def family(path):
    name = Path(path).name
    if name.startswith('NORMAL2-IM-'):
        return 'NORMAL2-IM'
    if name.startswith('IM-'):
        return 'IM'
    return 'virus' if '_virus_' in name else 'bacteria' if '_bacteria_' in name else 'unknown'


def diagnose(archive, audit_path):
    index = verify_bundle(archive)
    audit = json.loads(Path(audit_path).read_text(encoding='utf-8'))
    metadata = {row['path']: row for row in audit['images']}
    with zipfile.ZipFile(archive) as source:
        comparison = json.loads(source.read('suite/comparison.json'))
        selected = comparison['candidates'][0]
        prefix = 'suite/' + selected['architecture'] + '/'
        manifest = json.loads(source.read(prefix + 'split_manifest.json'))
        if digest_json({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) != manifest['manifest_sha256']:
            raise ValueError('Prepared manifest digest failed.')
        validate_boundaries(manifest['splits'])
        threshold = selected['validation_at_selected_threshold']['threshold']
        predictions = {'val': json.loads(source.read(prefix + 'validation_predictions.json'))}
        if 'suite/final_test_results.json' in source.namelist():
            predictions['test'] = json.loads(source.read('suite/final_test_results.json'))
        report = dict(suite=index['suite_name'], architecture=selected['architecture'], threshold=threshold,
                      manifest_sha256=manifest['manifest_sha256'],
                      split_counts={split: dict(Counter(row['label'] for row in rows)) for split, rows in manifest['splits'].items()},
                      split_metadata={}, fixed_threshold_results={}, proxy_auc={}, unmatched_metadata=[])
        for split, rows in manifest['splits'].items():
            usable = []
            for row in rows:
                record = metadata.get(row['path'])
                if record and record['sha256'] == row['sha256']:
                    usable.append((row, record))
                else:
                    report['unmatched_metadata'].append(dict(split=split, path=row['path']))
            summary = dict(images=len(rows), matching_audit_rows=len(usable),
                           candidate_groups=len({row['group'] for row in rows}),
                           filename_families=dict(Counter(family(row['path']) for row in rows)), classes={})
            for label in ('NORMAL', 'PNEUMONIA'):
                records = [record for row, record in usable if row['label'] == label]
                if records:
                    summary['classes'][label] = dict(
                        images=len(records), median_bytes=float(np.median([r['bytes'] for r in records])),
                        median_bytes_per_pixel=float(np.median([r['bytes'] / (r['width'] * r['height']) for r in records])),
                        median_aspect_ratio=float(np.median([r['width'] / r['height'] for r in records])))
            report['split_metadata'][split] = summary
            # Fixed, untrained proxy diagnostics on development data only. No test threshold/model search.
            if split in {'train', 'val', 'calibration'} and {r['label'] for r, _ in usable} == {'NORMAL', 'PNEUMONIA'}:
                truth = [int(r['label'] == 'PNEUMONIA') for r, _ in usable]
                report['proxy_auc'][split] = dict(
                    images=len(usable), negative_file_bytes=float(roc_auc_score(truth, [-r['bytes'] for _, r in usable])),
                    negative_bytes_per_pixel=float(roc_auc_score(truth, [-r['bytes'] / (r['width'] * r['height']) for _, r in usable])))
        for split, saved in predictions.items():
            rows = manifest['splits'][split]
            truth = [int(row['label'] == 'PNEUMONIA') for row in rows]
            if saved['targets'] != truth or len(saved['scores']) != len(rows):
                raise ValueError('Saved predictions disagree with the original manifest.')
            if split == 'test':
                if saved['paths'] != [r['path'] for r in rows] or saved['checkpoint_sha256'] != selected['checkpoint_sha256']:
                    raise ValueError('Saved test results refer to different inputs or checkpoint.')
                if saved['metrics'] != metrics(truth, saved['scores'], threshold):
                    raise ValueError('Saved test metrics did not reproduce at the original threshold.')
            result = dict(metrics=metrics(truth, saved['scores'], threshold), filename_families={}, errors=[])
            for cohort in sorted({family(row['path']) for row in rows}):
                pairs = [(row, score) for row, score in zip(rows, saved['scores']) if family(row['path']) == cohort]
                scores = np.array([score for _, score in pairs])
                result['filename_families'][cohort] = dict(
                    images=len(scores), positive_predictions=int((scores >= threshold).sum()),
                    score_quantiles=np.quantile(scores, [0, .25, .5, .75, 1]).tolist())
            for row, score in zip(rows, saved['scores']):
                if bool(score >= threshold) != (row['label'] == 'PNEUMONIA'):
                    result['errors'].append(dict(path=row['path'], label=row['label'], score=score))
            report['fixed_threshold_results'][split] = result
    report['interpretation'] = (
        'File size and bytes per pixel are descriptive encoding/acquisition proxies, not causal proof of '
        'what the CNN learned. Hash-unmatched metadata is excluded from these statistics. No images were '
        'repaired or inferred again, no alternative test thresholds were evaluated, and no model was trained. '
        'The reviewed benchmark must not be presented as a fresh unbiased holdout after further changes.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New report directory; prior reports are preserved')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Choose a new output directory.')
    report = diagnose(args.archive, args.audit)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'diagnosis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Development-only metadata proxy AUC:', json.dumps(report['proxy_auc'], indent=2))
    print('Original fixed-threshold metrics:', json.dumps({k: v['metrics'] for k, v in report['fixed_threshold_results'].items()}, indent=2))
    print('Report:', args.output / 'diagnosis.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
