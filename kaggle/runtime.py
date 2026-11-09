"""Small Kaggle adapter around the same audited preparation and training pipeline."""

import json
from pathlib import Path
import shutil


def discover_dataset(input_root, explicit=None):
    def valid(root):
        return all((root / split / label).is_dir()
                   for split in ('train', 'val', 'test') for label in ('NORMAL', 'PNEUMONIA'))

    if explicit:
        root = Path(explicit).resolve()
        if not valid(root):
            raise ValueError('DATA_ROOT must directly contain train/, val/, and test/ with both class folders.')
        return root
    roots = sorted({path.parent.resolve() for path in Path(input_root).rglob('train') if valid(path.parent)},
                   key=lambda path: (len(path.parts), str(path)))
    if not roots:
        raise ValueError('Attach paultimothymooney/chest-xray-pneumonia with Add Input, or set DATA_ROOT explicitly.')
    shallowest = [root for root in roots if len(root.parts) == len(roots[0].parts)]
    if len(shallowest) != 1:
        raise ValueError('Multiple datasets match. Set DATA_ROOT to one of: ' + ', '.join(map(str, shallowest)))
    if len(roots) > 1:
        print('Nested dataset copies found; using one root only:', shallowest[0], flush=True)
    return shallowest[0]


def check_environment(require_gpu=True):
    import sys
    import torch
    import torchvision
    from src.compute import select_device
    if tuple(int(part) for part in torch.__version__.split('+')[0].split('.')[:2]) < (2, 5):
        raise RuntimeError('Use a Kaggle runtime with torch >= 2.5 and its matching torchvision. Do not install Windows CUDA wheels here.')
    device = select_device('cuda' if require_gpu else 'auto')
    print('Python:', sys.version.split()[0], '| torch:', torch.__version__, '| torchvision:', torchvision.__version__)
    print('Device:', device, '| CUDA runtime:', torch.version.cuda, flush=True)
    if device.type == 'cuda':
        print('GPU:', torch.cuda.get_device_name(device), '| VRAM GiB:',
              round(torch.cuda.get_device_properties(device).total_memory / 1024**3, 1), flush=True)
        print('One GPU is used. Candidates run sequentially; a second GPU is not used automatically.', flush=True)
    return device


def restore_previous(previous, workspace):
    previous, workspace = Path(previous).resolve(), Path(workspace).resolve()
    if (workspace / 'data').exists():
        raise ValueError('This workspace already has data/; leave RESUME_SOURCE=None to keep using it.')
    if not (previous / 'data/prepared/kaggle-v1/manifest.json').is_file():
        raise ValueError('RESUME_SOURCE must point to the saved pulmoscan_training workspace, not an individual model.')
    if (previous / 'source_index.json').read_bytes() != (workspace / 'source_index.json').read_bytes():
        raise ValueError('The saved run used different source code. Resume with its original notebook version.')
    for relative in ('data/prepared', 'data/review', 'data/experiments'):
        source = previous / relative
        if source.exists():
            shutil.copytree(source, workspace / relative)
    config = previous / 'configs/kaggle_resolved.json'
    if config.exists():
        shutil.copy2(config, workspace / 'configs/kaggle_resolved.json')
    print('Restored previous artifacts; original source/manifest identity remains unchanged.', flush=True)


def prepare(workspace, data_root, batch_size=16, accumulation_steps=1, epochs=25):
    from scripts.audit_dataset import audit_dataset
    from scripts.train_models import read_config
    from src.data_protocol import load_manifest
    from src.prepare_dataset import prepare_dataset
    workspace, data_root = Path(workspace).resolve(), Path(data_root).resolve()
    manifest_path = workspace / 'data/prepared/kaggle-v1/manifest.json'
    if manifest_path.exists():
        manifest, original_root = load_manifest(manifest_path)
        if original_root.resolve() != data_root:
            raise ValueError('The saved manifest refers to a different input mount. Reattach the original dataset at its original path.')
        print('Reusing the verified original manifest:', manifest['manifest_sha256'])
    else:
        audit_path = workspace / 'data/review/kaggle_dataset_audit.json'
        if audit_path.exists():
            raise ValueError('An earlier incomplete preparation exists. Preserve it and use a new workspace instead of overwriting evidence.')
        audit = audit_dataset(data_root, progress=lambda message: print(message, flush=True))
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        with audit_path.open('x', encoding='utf-8') as handle:
            json.dump(audit, handle, indent=2)
        manifest = prepare_dataset(data_root, manifest_path.parent, audit_path=audit_path)
    config = json.loads((workspace / 'kaggle/train_config.json').read_text(encoding='utf-8'))
    config.update(batch_size=batch_size, accumulation_steps=accumulation_steps, epochs=epochs)
    config_path = workspace / 'configs/kaggle_resolved.json'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        if json.loads(config_path.read_text(encoding='utf-8')) != config:
            raise ValueError('This workspace already has a different config. Keep the original settings when resuming.')
    else:
        # Validate before saving: no optimizer or pretrained model is loaded here.
        candidate = workspace / 'configs/kaggle_candidate.json'
        candidate.write_text(json.dumps(config, indent=2), encoding='utf-8')
        read_config(candidate)
        candidate.rename(config_path)
    print('Prepared counts:', manifest['counts'], flush=True)
    print('Config:', config_path, flush=True)
    return config_path, manifest_path


def run_or_resume(workspace, config_path, run_name):
    from scripts.train_models import cli, read_config
    workspace = Path(workspace).resolve()
    if not run_name or Path(run_name).name != run_name or run_name in {'.', '..'} or '\\' in run_name:
        raise ValueError('RUN_NAME must be one folder name.')
    suite = workspace / 'data/experiments' / run_name
    config = read_config(config_path)
    if not suite.exists():
        code = cli(['--config', str(config_path), '--run-dir', str(suite)])
        if code:
            raise RuntimeError(f'Training stopped with exit code {code}; inspect the output and saved train.log.')
        return suite
    plan = json.loads((suite / 'suite_plan.json').read_text(encoding='utf-8'))
    if plan['models'] != config['models']:
        raise ValueError('Saved candidate plan differs; keep the original config when resuming.')
    for name in config['models']:
        folder = suite / name
        if (folder / 'validation_summary.json').exists():
            print('Already completed:', name, flush=True)
            continue
        if (folder / 'last.pt').exists():
            command = ['--resume', str(folder / 'last.pt')]
        elif folder.exists():
            raise ValueError(f'{name} stopped before a complete epoch. Choose a new RUN_NAME; existing files are preserved.')
        else:
            command = ['--config', str(config_path), '--models', name, '--run-dir', str(suite)]
        code = cli(command)
        if code:
            raise RuntimeError(f'Training stopped with exit code {code}; inspect the output and saved train.log.')
    return suite
