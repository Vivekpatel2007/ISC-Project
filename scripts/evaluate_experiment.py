"""One final test evaluation of the validation-selected experiment. Never selects or trains."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True, type=Path, help='Completed suite directory under data/experiments/')
    args = parser.parse_args()
    suite = args.suite.resolve()
    if not suite.is_relative_to((ROOT / 'data/experiments').resolve()):
        parser.error('Use a completed local experiment suite under data/experiments/.')
    result_path = suite / 'final_test_results.json'
    if result_path.exists():
        parser.error('Final test results already exist; inspect them instead of repeating model selection on test.')
    comparison = json.loads((suite / 'comparison.json').read_text(encoding='utf-8'))
    if comparison.get('pending_candidates'):
        raise ValueError(f'Finish planned candidates before final test: {comparison["pending_candidates"]}')
    selected = comparison['candidates'][0]
    checkpoint_path = (ROOT / comparison['recommended_checkpoint']).resolve()
    if not checkpoint_path.is_relative_to(suite) or hashlib.sha256(checkpoint_path.read_bytes()).hexdigest() != selected['checkpoint_sha256']:
        raise ValueError('Recommended checkpoint path/hash does not match the validation comparison.')
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    import torch
    from torch.utils.data import DataLoader
    from src.compute import select_device
    from src.data_protocol import load_manifest
    from src.modeling import build_classifier, image_transforms
    from src.training import ManifestDataset, metrics, validate, write_json
    manifest, root = load_manifest(checkpoint_path.parent / 'split_manifest.json')
    checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=True)
    if not checkpoint.get('finalized') or checkpoint['manifest_sha256'] != manifest['manifest_sha256']:
        raise ValueError('Only a finalized candidate with its original split manifest can be evaluated.')
    device = select_device()
    model = build_classifier(checkpoint['architecture'], pretrained=False).to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    transform = image_transforms(checkpoint['image_size'], checkpoint['normalization'], checkpoint['preprocessing']['resize_mode'])
    dataset = ManifestDataset(manifest, root, 'test', transform)
    loader = DataLoader(dataset, batch_size=checkpoint['training_config']['batch_size'], shuffle=False, num_workers=0)
    print(f'Final test only: {len(dataset)} unique manifest images; device={device}; threshold remains {checkpoint["threshold"]:.8f}', flush=True)
    result = validate(model, loader, device, checkpoint['training_config']['mixed_precision'] and device.type == 'cuda')
    report = dict(architecture=checkpoint['architecture'], checkpoint_sha256=selected['checkpoint_sha256'],
                  manifest_sha256=manifest['manifest_sha256'], samples=len(dataset), device=str(device),
                  metrics=metrics(result['targets'], result['scores'], checkpoint['threshold']), loss=result['loss'],
                  targets=result['targets'], scores=result['scores'], paths=[row['path'] for row in dataset.rows],
                  caveat='Image-level results; candidate filename IDs do not establish verified patient independence. No test tuning.')
    write_json(report, result_path)
    comparison['test_evaluated'] = True
    write_json(comparison, suite / 'comparison.json')
    print(json.dumps(report['metrics'], indent=2))
    print(f'Results: {result_path}. No checkpoint or API configuration was changed.')


if __name__ == '__main__':
    main()
