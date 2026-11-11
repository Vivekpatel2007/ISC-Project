"""Evaluate one fixed checkpoint/profile on an audited candidate external cohort; never fit."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import torch
from torch.utils.data import DataLoader

from scripts.inspect_checkpoint import ArtifactReader, DiagnosticDataset
from src.compute import select_device
from src.data_protocol import digest_json, read_verified_image
from src.modeling import build_classifier, image_transforms
from src.postprocessing import probability_quality, probability_to_margin, validate_profile
from src.scoring import collect_logits, metrics, score_logits


def evaluate(artifact_path, manifest_path, output, profile_path=None, device_preference='auto', batch_size=16):
    if batch_size < 1:
        raise ValueError('Batch size must be positive.')
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Choose a new output directory; previous evaluations are preserved.')
    manifest_bytes = Path(manifest_path).read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get('kind') != 'candidate_external_validation' or manifest.get('schema_version') != 1
            or digest_json({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) != manifest['manifest_sha256']):
        raise ValueError('Candidate external manifest failed validation.')
    data_root = Path(manifest['source_root']).resolve()
    if output.is_relative_to(data_root):
        raise ValueError('Keep outputs outside the source cohort.')
    artifact = ArtifactReader(artifact_path)
    try:
        if artifact.path.is_dir() and output.is_relative_to(artifact.path):
            raise ValueError('Keep outputs outside the original artifacts.')
        comparison = artifact.json('comparison.json')
        if comparison.get('pending_candidates'):
            raise ValueError('Freeze a completed model selection before evaluating external data.')
        selected = comparison['candidates'][0]
        checkpoint_bytes = artifact.read(selected['architecture'] + '/best.pt')
        sha = hashlib.sha256(checkpoint_bytes).hexdigest()
        if sha != selected['checkpoint_sha256'] or sha != manifest['checkpoint_sha256']:
            raise ValueError('External protocol was prepared for a different checkpoint.')
        if selected['manifest_sha256'] != manifest['reference_manifest_sha256']:
            raise ValueError('External protocol references a different development manifest.')
        state = torch.load(io.BytesIO(checkpoint_bytes), map_location='cpu', weights_only=True)
        if (not state.get('finalized') or state['architecture'] != selected['architecture']
                or state['class_names'] != ['NORMAL', 'PNEUMONIA'] or state['class_to_idx'] != {'NORMAL': 0, 'PNEUMONIA': 1}
                or state['manifest_sha256'] != selected['manifest_sha256']):
            raise ValueError('Checkpoint metadata is inconsistent.')
        threshold = state['threshold']
        boundary = probability_to_margin(threshold)
        temperature, profile_sha = 1., None
        if profile_path:
            payload = Path(profile_path).read_bytes()
            profile = validate_profile(json.loads(payload), sha)
            if profile['manifest_sha256'] != selected['manifest_sha256'] or profile['original_probability_threshold'] != threshold:
                raise ValueError('Profile changed the frozen source or decision threshold.')
            temperature = profile['temperature']
            profile_sha = hashlib.sha256(payload).hexdigest()
        rows = manifest['images']
        if {row['label'] for row in rows} != {'NORMAL', 'PNEUMONIA'}:
            raise ValueError('External cohort requires both classes.')
        for row in rows:
            read_verified_image(data_root, row)
        device = select_device(device_preference)
        model = build_classifier(state['architecture'], pretrained=False).to(device).eval()
        model.load_state_dict(state['model_state_dict'], strict=True)
        transform = image_transforms(state['image_size'], state['normalization'], state['preprocessing']['resize_mode'])
        loader = DataLoader(DiagnosticDataset(rows, data_root, transform), batch_size=batch_size, shuffle=False, num_workers=0)
        truth, logits, probabilities = collect_logits(model, loader, device, state['training_config']['mixed_precision'] and device.type == 'cuda')
        scores = score_logits(truth, logits, threshold, probabilities)
        margin_metrics = metrics(truth, scores['margins'], boundary)
        report = dict(schema_version=1, evaluation_role='candidate_external_validation',
                      created_at=datetime.now(timezone.utc).isoformat(), checkpoint_sha256=sha,
                      development_manifest_sha256=selected['manifest_sha256'], external_manifest_sha256=manifest['manifest_sha256'],
                      profile_sha256=profile_sha, temperature=temperature, images=len(rows),
                      original_probability_metrics=scores['metrics_at_saved_threshold'],
                      raw_margin_metrics=dict(margin_metrics, decision_space='logit_margin'),
                      probability_quality=probability_quality(truth, scores['margins'], temperature),
                      decision_changes_from_legacy_rounding=int(((np.asarray(scores['margins']) >= boundary)
                                                               != (np.asarray(probabilities) >= threshold)).sum()),
                      device=str(device), torch=str(torch.__version__),
                      independence_status=manifest['independence_status'], source_description=manifest['source_description'],
                      caveat='No fitting, threshold tuning, model selection, or deployment occurred. Source/patient independence '
                             'and label quality need review; the manifest alone does not establish clinical validation.')
        output.mkdir(parents=True, exist_ok=False)
        (output / 'external_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (output / 'external_predictions.json').write_text(json.dumps(dict(
            paths=[row['path'] for row in rows], labels=truth, logits=logits, margins=scores['margins'], probabilities_float32=probabilities), indent=2), encoding='utf-8')
        return report
    finally:
        artifact.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-artifact', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--batch-size', type=int, default=16)
    args = parser.parse_args(argv)
    report = evaluate(args.model_artifact, args.manifest, args.output, args.profile, args.device, args.batch_size)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    main()
