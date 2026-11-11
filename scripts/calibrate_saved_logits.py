"""Fit one postprocessing scalar on calibration-only CSVs; never read benchmark scores."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

from scripts.inspect_checkpoint import ArtifactReader, verify_diagnostics
from src.data_protocol import digest_json, validate_boundaries
from src.postprocessing import fit_temperature, probability_quality, probability_to_margin, sigmoid


def calibration_partition(rows, seed=2026, check_ratio=.3):
    fit, check = [], []
    for label in ('NORMAL', 'PNEUMONIA'):
        indices = [index for index, row in enumerate(rows) if row['label'] == label]
        groups = [rows[index]['group'] for index in indices]
        if len(set(groups)) < 2:
            raise ValueError('Need at least two groups in each class for an independent temperature-check subset.')
        splitter = GroupShuffleSplit(n_splits=64, test_size=check_ratio, random_state=seed)
        a, b = min(splitter.split(indices, groups=groups), key=lambda pair: abs(len(pair[1]) - len(indices) * check_ratio))
        fit.extend(indices[index] for index in a)
        check.extend(indices[index] for index in b)
    if {rows[i]['group'] for i in fit} & {rows[i]['group'] for i in check}:
        raise ValueError('Temperature fit/check group overlap.')
    return sorted(fit), sorted(check)


def read_rows(archive, filename, manifest_rows):
    rows = list(csv.DictReader(io.StringIO(archive.read(filename).decode('utf-8'))))
    if len(rows) != len(manifest_rows):
        raise ValueError('Diagnostic CSV count differs from the original manifest.')
    margins, labels, probabilities = [], [], []
    for row, original in zip(rows, manifest_rows):
        if any(row[key] != original[key] for key in ('path', 'sha256', 'label')):
            raise ValueError('Diagnostic paths/hashes/labels differ from the original manifest.')
        margin, normal, pneumonia, probability = (float(row[key]) for key in
                                                 ('logit_margin', 'logit_normal', 'logit_pneumonia', 'probability_float32'))
        if not np.isfinite([margin, normal, pneumonia, probability]).all() or not 0 <= probability <= 1 or abs(margin - (pneumonia - normal)) > 1e-10:
            raise ValueError('Diagnostic logit margin is inconsistent.')
        margins.append(margin)
        labels.append(int(row['label'] == 'PNEUMONIA'))
        probabilities.append(probability)
    return np.asarray(labels), np.asarray(margins), np.asarray(probabilities)


def calibrate(diagnostic_zip, model_artifact, output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new output directory; earlier profiles are preserved.')
    verified = verify_diagnostics(diagnostic_zip)
    artifact = ArtifactReader(model_artifact)
    try:
        if artifact.path.is_dir() and output.is_relative_to(artifact.path):
            raise ValueError('Keep new profiles outside the original model artifacts.')
        comparison = artifact.json('comparison.json')
        selected = comparison['candidates'][0]
        manifest = artifact.json(selected['architecture'] + '/split_manifest.json')
        if (manifest.get('schema_version') != 1 or digest_json({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) != manifest['manifest_sha256']
                or selected['checkpoint_sha256'] != verified['checkpoint_sha256']
                or manifest['manifest_sha256'] != verified['manifest_sha256']):
            raise ValueError('Diagnostic/model provenance does not match.')
        validate_boundaries(manifest['splits'])
        if 'calibration' not in manifest['splits']:
            raise ValueError('Use a model with a separate calibration split.')
        original_threshold = selected['validation_at_selected_threshold']['threshold']
        boundary = probability_to_margin(original_threshold)
        with zipfile.ZipFile(diagnostic_zip) as archive:
            report = json.loads(archive.read('diagnostic_results.json'))
            if report['threshold'] != original_threshold:
                raise ValueError('The diagnostic used a different original decision threshold.')
            # Test CSVs and benchmark statistics are never used for fitting or assessment.
            cal = read_rows(archive, 'calibration_predictions.csv', manifest['splits']['calibration'])
            val = read_rows(archive, 'val_predictions.csv', manifest['splits']['val'])
        fit, check = calibration_partition(manifest['splits']['calibration'])
        fitting = fit_temperature(cal[0][fit], cal[1][fit])
        temperature = fitting['temperature']
        assessments = {}
        for name, labels, margins, probabilities in [
            ('temperature_fit', cal[0][fit], cal[1][fit], cal[2][fit]),
            ('temperature_check', cal[0][check], cal[1][check], cal[2][check]),
            ('model_selection_validation', *val),
        ]:
            assessments[name] = dict(before=probability_quality(labels, margins),
                                     after=probability_quality(labels, margins, temperature),
                                     decisions_changed_by_margin_representation=int(((margins >= boundary) != (probabilities >= original_threshold)).sum()))
        profile = dict(schema_version=1, kind='experimental_temperature_scaling', created_at=datetime.now(timezone.utc).isoformat(),
                       checkpoint_sha256=selected['checkpoint_sha256'], manifest_sha256=manifest['manifest_sha256'],
                       diagnostic_archive_sha256=hashlib.sha256(Path(diagnostic_zip).read_bytes()).hexdigest(),
                       temperature=temperature, fitting=fitting, original_probability_threshold=original_threshold,
                       decision_policy='preserve_original_margin_boundary', decision_margin_threshold=boundary,
                       transformed_probability_threshold=float(sigmoid(boundary / temperature)),
                       fit_split='subset of original calibration only', seed=2026,
                       fit_paths=[manifest['splits']['calibration'][i]['path'] for i in fit],
                       check_paths=[manifest['splits']['calibration'][i]['path'] for i in check],
                       deployment_status='experimental_not_promoted', independent_validation_required=True,
                       caveat='The check subset is held out from temperature fitting, but its images were used in the earlier '
                              'threshold-fitting experiment. It is not a fresh external holdout. Temperature scaling does not '
                              'change ranking or repair errors at the preserved decision boundary.')
        check_result = assessments['temperature_check']
        assessments['check_improved_nll'] = check_result['after']['negative_log_likelihood'] < check_result['before']['negative_log_likelihood']
        output.mkdir(parents=True, exist_ok=False)
        (output / 'postprocessing_profile.json').write_text(json.dumps(profile, indent=2), encoding='utf-8')
        (output / 'development_assessment.json').write_text(json.dumps(assessments, indent=2), encoding='utf-8')
        print('Temperature:', temperature, '| original margin decision boundary preserved:', boundary)
        print('Temperature-check NLL:', check_result['before']['negative_log_likelihood'], '->', check_result['after']['negative_log_likelihood'])
        print('No benchmark scores used, no neural model trained, no model or API configuration changed.')
        return profile, assessments
    finally:
        artifact.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostics', required=True, type=Path)
    parser.add_argument('--model-artifact', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    calibrate(args.diagnostics, args.model_artifact, args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
