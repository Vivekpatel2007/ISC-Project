"""Run validated local experiments with live terminal/file logs; test inference is separate."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def read_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if 'manifest' not in config or 'accumulation_steps' not in config:
        raise ValueError('Use configs/train_local.json for the manifest-based runner; legacy training configs are historical.')
    for field in ('batch_size', 'accumulation_steps', 'epochs', 'early_stopping_patience', 'log_every_batches'):
        if type(config[field]) is not int or config[field] < 1:
            raise ValueError(f'{field} must be a positive integer.')
    if config['image_size'] != 224 or config['num_workers'] != 0:
        raise ValueError('This validated local profile uses 224px and num_workers=0.')
    if not 0 < config['validation_min_sensitivity'] <= 1:
        raise ValueError('validation_min_sensitivity must be in (0, 1].')
    for field in ('head_learning_rate', 'backbone_learning_rate', 'max_grad_norm'):
        if not math.isfinite(config[field]) or config[field] <= 0:
            raise ValueError(f'{field} must be finite and positive.')
    if type(config['head_warmup_epochs']) is not int or config['head_warmup_epochs'] < 0:
        raise ValueError('head_warmup_epochs must be a nonnegative integer.')
    if not math.isfinite(config['weight_decay']) or config['weight_decay'] < 0:
        raise ValueError('weight_decay must be finite and nonnegative.')
    if config.get('threshold_split', 'val') not in {'val', 'calibration'}:
        raise ValueError('threshold_split must be val or calibration.')
    if config.get('augmentation_profile', 'standard') not in {'standard', 'jpeg_robustness'}:
        raise ValueError('Unknown augmentation_profile.')
    if config.get('ranking_score_space', 'probability') not in {'probability', 'logit_margin'}:
        raise ValueError('ranking_score_space must be probability or logit_margin.')
    return config


def preflight(config, names, manifest, root):
    import torch
    from src.compute import select_device
    from src.modeling import build_classifier, image_transforms
    from src.training import ManifestDataset
    device = select_device()
    print(f'Preflight device: {device}; batch={config["batch_size"]}; effective batch={config["batch_size"] * config["accumulation_steps"]}', flush=True)
    print('Counts:', manifest['counts'], '\nManifest:', manifest['manifest_sha256'], flush=True)
    dataset = ManifestDataset(manifest, root, 'val', image_transforms(config['image_size'], resize_mode=config['resize_mode']))
    indices = [next(index for index, row in enumerate(dataset.rows) if row['label'] == label)
               for label in ('NORMAL', 'PNEUMONIA')]
    batch = torch.stack([dataset[index][0] for index in indices]).to(device)
    for name in names:
        print(f'Checking {name}; trusted ImageNet weights may download on first use ...', flush=True)
        model = build_classifier(name, pretrained=True).to(device).eval()
        with torch.inference_mode(), torch.autocast(device_type=device.type, dtype=torch.float16,
                                                   enabled=config['mixed_precision'] and device.type == 'cuda'):
            logits = model(batch)
        if logits.shape != (2, 2) or not bool(torch.isfinite(logits).all()):
            raise ValueError(f'{name} forward check failed.')
        print(f'PASS {name}: preprocessing and forward inference. No gradients or optimizer steps.', flush=True)
        del model, logits
        if device.type == 'cuda':
            torch.cuda.empty_cache()
    print('Preflight complete. This does not measure training peak memory or model accuracy.', flush=True)


def update_comparison(suite):
    from src.training import write_json
    summaries = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(suite.glob('*/validation_summary.json'))]
    if not summaries:
        return
    if len({row['manifest_sha256'] for row in summaries}) != 1:
        raise ValueError('Cannot compare experiments with different split manifests.')
    spaces = {row.get('selection_metric', 'val_roc_auc') for row in summaries}
    if len(spaces) != 1:
        raise ValueError('Cannot compare probability-AUC and logit-margin-AUC selection scores in one suite.')
    ordered = sorted(summaries, key=lambda row: (-row['selection_metric_value'], row['validation_loss']))
    planned = json.loads((suite / 'suite_plan.json').read_text(encoding='utf-8'))['models']
    pending = sorted(set(planned) - {row['architecture'] for row in ordered})
    selection = ('Validation logit-margin ROC-AUC' if spaces == {'val_logit_margin_auc'} else 'Validation probability ROC-AUC')
    write_json(dict(selection=selection + '; lower validation NLL breaks exact ties. No test selection.',
                    candidates=ordered, pending_candidates=pending,
                    recommended_checkpoint=ordered[0]['checkpoint'], test_evaluated=False),
               suite / 'comparison.json')
    print('\nCompleted validation comparison:', suite / 'comparison.json', flush=True)
    print('Recommended candidate (not deployed):', ordered[0]['checkpoint'], flush=True)
    if pending:
        print('Still planned before final test:', ', '.join(pending), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/train_local.json')
    parser.add_argument('--models', nargs='+', choices=['densenet121', 'efficientnet_b0'])
    parser.add_argument('--check', action='store_true', help='Verify hashes, pretrained weights, and forward passes only; never train')
    parser.add_argument('--epochs', type=int)
    parser.add_argument('--batch-size', '--batch_size', type=int)
    parser.add_argument('--accumulation-steps', type=int)
    parser.add_argument('--run-dir', type=Path, help='New suite folder, or an existing suite to add a previously unstarted model')
    parser.add_argument('--resume', type=Path, help='Resume a trusted local last.pt; restores its original config and RNG')
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    from src.data_protocol import load_manifest
    from src.modeling import MODEL_NAMES
    from src.training import train_candidate

    config = read_config(args.config)
    if args.resume:
        if args.models or args.epochs or args.batch_size or args.accumulation_steps or args.run_dir or args.check:
            parser.error('--resume uses the original run configuration; do not combine it with overrides.')
        args.resume = args.resume.resolve()
        if not args.resume.is_relative_to((ROOT / 'data/experiments').resolve()) or args.resume.name != 'last.pt':
            parser.error('--resume accepts only a trusted local last.pt under data/experiments/.')
        import torch
        state = torch.load(args.resume, map_location='cpu', weights_only=True)
        config = state['config']
        names = [state['architecture']]
        suite = args.resume.resolve().parent.parent
    else:
        for key, value in [('epochs', args.epochs), ('batch_size', args.batch_size), ('accumulation_steps', args.accumulation_steps)]:
            if value is not None:
                if value < 1:
                    parser.error(f'{key} must be positive.')
                config[key] = value
        names = args.models or config['models']
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        suite = (args.run_dir or ROOT / config['output_root'] / stamp).resolve()
    if not names or len(set(names)) != len(names) or any(name not in MODEL_NAMES for name in names):
        parser.error('Choose distinct supported model names.')
    # Artifact locations are separate from the app checkpoint, even for custom run paths.
    if not suite.is_relative_to((ROOT / 'data/experiments').resolve()):
        parser.error('Experiment outputs must stay under data/experiments/.')
    manifest_path = ROOT / config['manifest']
    print('Verifying source image hashes before loading models ...', flush=True)
    manifest, root = load_manifest(manifest_path, verify_files=True, progress=lambda value: print(value, flush=True))
    if config.get('threshold_split', 'val') == 'calibration' and 'calibration' not in manifest['splits']:
        raise ValueError('This profile requires a separate calibration split; prepare a new v2 manifest.')
    if args.check:
        preflight(config, names, manifest, root)
        return 0
    if (suite / 'final_test_results.json').exists():
        raise ValueError('This suite already has final test results. Do not add training candidates after test evaluation.')
    from src.training import write_json
    suite.mkdir(parents=True, exist_ok=True)
    plan_path = suite / 'suite_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8')) if plan_path.exists() else dict(models=[], manifest_sha256=manifest['manifest_sha256'])
    if plan['manifest_sha256'] != manifest['manifest_sha256']:
        raise ValueError('An existing suite must retain its original split manifest.')
    plan['models'] = list(dict.fromkeys([*plan['models'], *names]))
    write_json(plan, plan_path)
    print('Experiment suite:', suite, flush=True)
    for name in names:
        run_dir = suite / name
        if (run_dir / 'validation_summary.json').exists():
            raise ValueError(f'{name} already completed. Start a new suite rather than overwriting it.')
        try:
            train_candidate(name, config, manifest, root, run_dir, args.resume)
        except KeyboardInterrupt:
            print('Training interrupted. Completed epoch checkpoints/logs are preserved.', flush=True)
            return 130
        except RuntimeError as error:
            if 'out of memory' in str(error).lower():
                print('GPU ran out of memory. Keep this log; start a new run with --batch-size 1 --accumulation-steps 16.', flush=True)
            raise
        update_comparison(suite)
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    print('Training/validation finished. Test evaluation and API promotion remain separate.', flush=True)
    return 0


def cli(argv=None):
    from src.data_protocol import DatasetIntegrityError
    try:
        return main(argv)
    except DatasetIntegrityError as error:
        print(f'\nDATASET INTEGRITY FAILURE\n{error}', file=sys.stderr, flush=True)
        print('Training stopped; completed checkpoints are preserved. Check all sources with '
              'scripts/check_training_data.py --manifest <the manifest used by this run>. '
              'Do not regenerate the manifest or silently skip images to bypass the failure. '
              'This error alone does not identify the underlying device or software fault.',
              file=sys.stderr, flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(cli())
