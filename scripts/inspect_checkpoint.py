"""Inference-only inspection of a fixed checkpoint; no training or threshold search."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset

from scripts.experiment_bundle import safe_relative, verify_bundle
from src.compute import select_device
from src.data_protocol import CLASSES, digest_json, read_verified_image, source_file, validate_boundaries
from src.modeling import build_classifier, image_transforms
from src.scoring import collect_logits, metrics, score_logits


class ArtifactReader:
    """Read our ZIP, an unpacked bundle, or a saved notebook's suite without executing its sources."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.archive = None
        if self.path.is_file():
            self.index = verify_bundle(self.path)
            self.archive = zipfile.ZipFile(self.path)
            self.suite_name = self.index['suite_name']
            self.verification = 'All indexed ZIP members verified; original source files are not executed.'
        else:
            self.folder = self.path / 'suite' if (self.path / 'suite/comparison.json').is_file() else self.path
            if not (self.folder / 'comparison.json').is_file():
                raise ValueError('Use a model ZIP, unpacked bundle root, or suite directory containing comparison.json.')
            index_path = self.path / 'bundle.json'
            self.suite_name = (json.loads(index_path.read_text(encoding='utf-8'))['suite_name']
                               if index_path.is_file() else self.folder.name)
            self.verification = 'Directory input: selected checkpoint hash, manifest digest, and saved prediction consistency verified.'

    def read(self, relative):
        parts = safe_relative(relative).parts
        if self.archive:
            return self.archive.read('suite/' + '/'.join(parts))
        target = self.folder.joinpath(*parts).resolve()
        if not target.is_relative_to(self.folder.resolve()):
            raise ValueError('Artifact path escaped the source suite.')
        return target.read_bytes()

    def exists(self, relative):
        safe_relative(relative)
        if self.archive:
            return 'suite/' + relative in self.archive.namelist()
        return (self.folder / relative).is_file()

    def json(self, relative):
        return json.loads(self.read(relative))

    def close(self):
        if self.archive:
            self.archive.close()


class DiagnosticDataset(Dataset):
    def __init__(self, rows, root, transform):
        self.rows, self.root, self.transform = rows, root, transform

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        with Image.open(io.BytesIO(read_verified_image(self.root, row))) as image:
            image.load()
            rgb = image.convert('RGB')
        return self.transform(rgb), CLASSES.index(row['label'])


def compare_reference(saved, rows, scores, threshold):
    targets = [CLASSES.index(row['label']) for row in rows]
    if saved['targets'] != targets or len(saved['scores']) != len(rows):
        raise ValueError('Saved reference predictions disagree with manifest ordering or labels.')
    if 'paths' in saved and saved['paths'] != [row['path'] for row in rows]:
        raise ValueError('Saved reference paths disagree with the original manifest.')
    original = np.asarray(saved['scores'])
    current = np.asarray(scores)
    return dict(images=len(rows), max_probability_difference=float(np.abs(current - original).max()),
                changed_decisions_at_saved_threshold=int(((current >= threshold) != (original >= threshold)).sum()),
                original_probability_metrics=metrics(targets, original, threshold))


def write_records(path, rows, result, threshold):
    fields = ['path', 'label', 'predicted_at_saved_threshold', 'sha256', 'probability_float32',
              'logit_normal', 'logit_pneumonia', 'logit_margin', 'log_probability_normal',
              'log_probability_pneumonia', 'negative_log_likelihood']
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows):
            writer.writerow(dict(path=row['path'], label=row['label'], sha256=row['sha256'],
                                 predicted_at_saved_threshold=CLASSES[int(result['scores'][index] >= threshold)],
                                 probability_float32=result['scores'][index],
                                 logit_normal=result['logits'][index][0], logit_pneumonia=result['logits'][index][1],
                                 logit_margin=result['margins'][index],
                                 log_probability_normal=result['log_probabilities'][index][0],
                                 log_probability_pneumonia=result['log_probabilities'][index][1],
                                 negative_log_likelihood=result['nll'][index]))


def make_plots(output, root, rows_by_split, results, threshold):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(results), figsize=(5 * len(results), 4), squeeze=False)
    for axis, (split, result) in zip(axes[0], results.items()):
        for target, label in enumerate(CLASSES):
            margins = [margin for y, margin in zip(result['targets'], result['margins']) if y == target]
            axis.hist(margins, bins=30, alpha=.55, label=label)
        axis.set(title=split, xlabel='Logit(PNEUMONIA) - logit(NORMAL)', ylabel='Images')
        axis.legend()
    fig.suptitle('Fixed checkpoint: raw margin distributions (no threshold fitting)')
    fig.tight_layout()
    fig.savefig(output / 'logit_distributions.png', dpi=140)
    plt.close(fig)
    split = 'test' if 'test' in results else 'calibration' if 'calibration' in results else 'val'
    result = results[split]
    indices = [index for index, target in enumerate(result['targets'])
               if target == 0 and result['scores'][index] >= threshold]
    indices = sorted(indices, key=lambda index: result['margins'][index], reverse=True)[:12]
    if not indices:
        return
    fig, axes = plt.subplots((len(indices) + 3) // 4, 4, figsize=(14, 3.3 * ((len(indices) + 3) // 4)), squeeze=False)
    for axis in axes.flat:
        axis.axis('off')
    for axis, index in zip(axes.flat, indices):
        row = rows_by_split[split][index]
        with Image.open(io.BytesIO(read_verified_image(root, row))) as image:
            image.load()
            image = image.convert('L')
            image.thumbnail((400, 400))
            axis.imshow(np.asarray(image), cmap='gray', vmin=0, vmax=255)
        axis.set_title(f"{Path(row['path']).name}\nLabel NORMAL; saved-cut prediction PNEUMONIA\n"
                       f"score={result['scores'][index]:.8g}; margin={result['margins'][index]:.2f}", fontsize=8)
    fig.suptitle(f'{split}: false positives at the unchanged threshold; highest margins first')
    fig.tight_layout()
    fig.savefig(output / 'false_positive_examples.png', dpi=140)
    plt.close(fig)


def inspect(artifact_path, data_root, output, include_reviewed_benchmark=False, batch_size=16,
            device_preference='auto', precision='saved', plots=True):
    if type(batch_size) is not int or batch_size < 1 or precision not in {'saved', 'fp32'}:
        raise ValueError('Use a positive batch size and precision saved or fp32.')
    output, data_root = Path(output).resolve(), Path(data_root).resolve()
    if output.exists():
        raise ValueError('Choose a new diagnostic output directory; prior reports are preserved.')
    source = ArtifactReader(artifact_path)
    try:
        if output.is_relative_to(data_root) or (source.path.is_dir() and output.is_relative_to(source.path)):
            raise ValueError('Diagnostic outputs must stay outside the source dataset and original artifacts.')
        comparison = source.json('comparison.json')
        if comparison.get('pending_candidates') or not comparison.get('candidates'):
            raise ValueError('Use the completed validation-selected experiment.')
        selected = comparison['candidates'][0]
        name = selected['architecture']
        if name not in {'densenet121', 'efficientnet_b0'}:
            raise ValueError('Unsupported selected model architecture.')
        prefix = name + '/'
        checkpoint_bytes = source.read(prefix + 'best.pt')
        if hashlib.sha256(checkpoint_bytes).hexdigest() != selected['checkpoint_sha256']:
            raise ValueError('Selected checkpoint differs from the validation comparison.')
        manifest = source.json(prefix + 'split_manifest.json')
        if digest_json({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) != manifest['manifest_sha256']:
            raise ValueError('Original manifest digest failed.')
        validate_boundaries(manifest['splits'])
        if selected['manifest_sha256'] != manifest['manifest_sha256']:
            raise ValueError('Selected candidate and source manifest differ.')
        print('Verifying original source bytes at the requested input mount; manifest is unchanged ...', flush=True)
        for index, row in enumerate(row for rows in manifest['splits'].values() for row in rows):
            read_verified_image(data_root, row)
            if (index + 1) % 1000 == 0:
                print('Verified source images:', index + 1, flush=True)
        state = torch.load(io.BytesIO(checkpoint_bytes), map_location='cpu', weights_only=True)
        threshold = state['threshold']
        if (not state.get('finalized') or state['architecture'] != name
                or state['manifest_sha256'] != manifest['manifest_sha256']
                or threshold != selected['validation_at_selected_threshold']['threshold']
                or state['class_names'] != list(CLASSES) or state['class_to_idx'] != {'NORMAL': 0, 'PNEUMONIA': 1}):
            raise ValueError('Checkpoint metadata does not match the selected candidate.')
        device = select_device(device_preference)
        amp = bool(precision == 'saved' and state['training_config']['mixed_precision'] and device.type == 'cuda')
        model = build_classifier(name, pretrained=False).to(device).eval()
        model.load_state_dict(state['model_state_dict'], strict=True)
        transform = image_transforms(state['image_size'], state['normalization'], state['preprocessing']['resize_mode'])
        splits = [split for split in ('val', 'calibration') if split in manifest['splits']]
        if include_reviewed_benchmark:
            splits.append('test')
        output.mkdir(parents=True, exist_ok=False)
        report = dict(schema_version=1, created_at=datetime.now(timezone.utc).isoformat(), suite=source.suite_name,
                      architecture=name, checkpoint_sha256=selected['checkpoint_sha256'],
                      manifest_sha256=manifest['manifest_sha256'], original_source_root=manifest['source_root'],
                      verified_source_root=str(data_root), artifact_verification=source.verification,
                      threshold=threshold, threshold_split=state.get('threshold_split', 'val'),
                      device=str(device), precision_requested=precision, amp_enabled=amp,
                      torch=str(torch.__version__), original_training_environment=state.get('environment'),
                      runtime=dict(python=platform.python_version(), torch=str(torch.__version__),
                                   cuda_runtime=torch.version.cuda,
                                   gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None,
                                   packages={package: version(package) for package in ('torchvision', 'Pillow', 'numpy', 'scikit-learn')}),
                      evaluation_role='fixed_checkpoint_diagnostic', splits={},
                      restrictions='No model fitting, threshold search, model selection, deployment, or original-artifact changes. '
                                   'Any test results use a previously reviewed benchmark, not a fresh independent holdout.')
        results, rows_by_split = {}, {}
        for split in splits:
            print(f'Inspecting {split}; model and threshold fixed; no training ...', flush=True)
            rows = manifest['splits'][split]
            dataset = DiagnosticDataset(rows, data_root, transform)
            loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
            targets, logits, probabilities = collect_logits(model, loader, device, amp)
            result = score_logits(targets, logits, threshold, probabilities)
            results[split], rows_by_split[split] = result, rows
            filename = split + '_predictions.csv'
            write_records(output / filename, rows, result, threshold)
            summary = {key: value for key, value in result.items()
                       if key not in {'targets', 'scores', 'logits', 'margins', 'log_probabilities', 'nll'}}
            summary.update(images=len(rows), records_file=filename,
                           evaluation_role='previously_reviewed_benchmark' if split == 'test' else 'development_diagnostic')
            reference = {'val': prefix + 'validation_predictions.json',
                         'calibration': prefix + 'calibration_predictions.json', 'test': 'final_test_results.json'}[split]
            if source.exists(reference):
                saved = source.json(reference)
                if split == 'test' and (saved['checkpoint_sha256'] != selected['checkpoint_sha256']
                                         or saved['manifest_sha256'] != manifest['manifest_sha256']):
                    raise ValueError('Original benchmark reference uses a different checkpoint or manifest.')
                summary['reference_comparison'] = compare_reference(saved, rows, result['scores'], threshold)
            report['splits'][split] = summary
        if plots:
            try:
                make_plots(output, data_root, rows_by_split, results, threshold)
            except ImportError:
                report['plot_note'] = 'matplotlib unavailable; CSV and JSON diagnostics are complete.'
        (output / 'diagnostic_results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        lines = ['# Fixed-checkpoint logit diagnosis', '',
                 f'Model: {name}. Saved threshold: {threshold!r}. No fitting or threshold selection.', '',
                 '| Split | Probability AUC | Raw-margin AUC | Accuracy at saved cut | Logit loss |',
                 '| --- | ---: | ---: | ---: | ---: |']
        for split, result in report['splits'].items():
            operating = result['metrics_at_saved_threshold']
            lines.append(f"| {split} | {operating['roc_auc']:.6f} | {result['roc_auc_logit_margin']:.6f} | "
                         f"{operating['accuracy']:.2%} | {result['loss_from_logits']:.6f} |")
        lines += ['', report['restrictions'], '',
                  'A better raw-margin AUC explains lost ranking information; it does not fix the saved-threshold predictions. '
                  'Runtime/precision differences can change outputs; inspect reference_comparison before claiming exact reproduction.']
        (output / 'README_results.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return report
    finally:
        source.close()


def export_diagnostics(output, destination):
    output, destination = Path(output).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(output):
        raise ValueError('Choose a new ZIP path outside the diagnostic directory.')
    report = json.loads((output / 'diagnostic_results.json').read_text(encoding='utf-8'))
    files = [path for path in sorted(output.iterdir()) if path.is_file() and path.suffix in {'.json', '.csv', '.png', '.md'}]
    index = dict(schema_version=1, kind='fixed_checkpoint_diagnostic', checkpoint_sha256=report['checkpoint_sha256'],
                 manifest_sha256=report['manifest_sha256'],
                 files={path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as handle, zipfile.ZipFile(handle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
        archive.writestr('diagnostic_bundle.json', json.dumps(index, indent=2))
    verify_diagnostics(destination)
    return destination


def verify_diagnostics(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names) or sum(entry.file_size for entry in entries) > 512 * 1024**2:
            raise ValueError('Duplicate or oversized diagnostic archive.')
        for name in names:
            safe_relative(name)
        if 'diagnostic_bundle.json' not in names or archive.getinfo('diagnostic_bundle.json').file_size > 1024**2:
            raise ValueError('Missing or oversized diagnostic checksum index.')
        index = json.loads(archive.read('diagnostic_bundle.json'))
        if index.get('schema_version') != 1 or index.get('kind') != 'fixed_checkpoint_diagnostic':
            raise ValueError('Unsupported diagnostic archive.')
        if set(names) != {'diagnostic_bundle.json', *index['files']}:
            raise ValueError('Diagnostic archive differs from its checksum index.')
        for name, sha in index['files'].items():
            digest = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b''):
                    digest.update(chunk)
            if digest.hexdigest() != sha:
                raise ValueError('Diagnostic checksum mismatch: ' + name)
        report = json.loads(archive.read('diagnostic_results.json'))
        if report['checkpoint_sha256'] != index['checkpoint_sha256'] or report['manifest_sha256'] != index['manifest_sha256']:
            raise ValueError('Diagnostic index and report provenance disagree.')
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True, help='Own model ZIP, unpacked bundle, or saved suite folder')
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--include-reviewed-benchmark', action='store_true')
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    parser.add_argument('--precision', choices=['saved', 'fp32'], default='saved')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--export', type=Path)
    args = parser.parse_args(argv)
    report = inspect(args.artifact, args.data_dir, args.output, args.include_reviewed_benchmark,
                     args.batch_size, args.device, args.precision, not args.no_plots)
    print(json.dumps({split: {key: value for key, value in result.items()
                              if key in {'metrics_at_saved_threshold', 'roc_auc_logit_margin', 'reference_comparison'}}
                      for split, result in report['splits'].items()}, indent=2))
    if args.export:
        print('Diagnostic ZIP:', export_diagnostics(args.output, args.export))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
