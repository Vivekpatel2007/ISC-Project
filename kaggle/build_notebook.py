"""Build a standalone notebook embedding only the current shared training sources."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import textwrap
import zlib

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'kaggle/PulmoScan_Training.ipynb'
OUTPUT_V2 = ROOT / 'kaggle/PulmoScan_Training_v2.ipynb'
SOURCES = (
    'src/compute.py', 'src/data_protocol.py', 'src/modeling.py', 'src/scoring.py', 'src/training.py', 'src/prepare_dataset.py',
    'scripts/train_models.py', 'scripts/audit_dataset.py', 'scripts/evaluate_experiment.py',
    'scripts/check_training_data.py', 'scripts/experiment_bundle.py', 'scripts/diagnose_experiment.py',
    'kaggle/runtime.py', 'kaggle/train_config.json', 'kaggle/train_config_v2.json', 'kaggle/requirements.txt',
)


def build_notebook(profile='v1'):
    if profile not in {'v1', 'v2'}:
        raise ValueError('Unknown notebook profile.')
    files = {name: (ROOT / name).read_bytes() for name in SOURCES}
    # Give the extracted src/scripts priority over unrelated installed namespace packages.
    files.update({'src/__init__.py': b'', 'scripts/__init__.py': b''})
    index = {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()}
    encoded = json.dumps({name: base64.b64encode(payload).decode('ascii') for name, payload in files.items()},
                         sort_keys=True, separators=(',', ':')).encode()
    compressed = zlib.compress(encoded, level=9)
    payload = base64.b64encode(compressed).decode('ascii')
    cells = []

    def markdown(source):
        cells.append(dict(cell_type='markdown', id=f'cell-{len(cells):02d}', metadata={},
                          source=textwrap.dedent(source).strip().splitlines(keepends=True)))

    def code(source):
        cells.append(dict(cell_type='code', id=f'cell-{len(cells):02d}', metadata={}, execution_count=None,
                          outputs=[], source=textwrap.dedent(source).strip().splitlines(keepends=True)))

    markdown('''
        # PulmoScan: Kaggle training

        Train **DenseNet121 + EfficientNet-B0** with the same audited split/preprocessing/training code as the local project.
        This notebook embeds the necessary source files. **No project ZIP, private repository, API token, `.env`, or local dataset upload is required.**

        Before running:
        1. In Kaggle, import this `.ipynb` using **Import Notebook**.
        2. **Add Input**: [paultimothymooney/chest-xray-pneumonia](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia).
        3. In session settings choose an available **GPU** and enable **Internet** for official ImageNet weights.
        4. Run cells in order. GPU availability/account requirements depend on Kaggle. Only one GPU is used.

        The input dataset stays read-only. Models/logs are written to `/kaggle/working/pulmoscan_training/`.
        Download `pulmoscan_models.zip` when complete, and **Save Version** with outputs before ending the session.
        No app server starts, no live model is replaced, and test evaluation is disabled by default.
        [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).
    ''')
    bootstrap = '''
        import base64, hashlib, json, os, sys, zlib
        from pathlib import Path, PurePosixPath

        WORKSPACE = Path('/kaggle/working/pulmoscan_training')
        SOURCE_INDEX = __INDEX__
        SOURCE_PAYLOAD = '__PAYLOAD__'
        packed = base64.b64decode(SOURCE_PAYLOAD)
        if hashlib.sha256(packed).hexdigest() != '__PACKED_HASH__':
            raise ValueError('Embedded source checksum failed. Re-import an intact notebook.')
        files = json.loads(zlib.decompress(packed))
        if set(files) != set(SOURCE_INDEX):
            raise ValueError('Embedded source index differs.')
        for name, encoded in files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\\\' in name or ':' in name:
                raise ValueError('Unsafe embedded source path.')
            content = base64.b64decode(encoded)
            if hashlib.sha256(content).hexdigest() != SOURCE_INDEX[name]:
                raise ValueError('Embedded source checksum failed: ' + name)
            target = WORKSPACE.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(WORKSPACE.resolve()):
                raise ValueError('Embedded source escaped workspace.')
            if target.exists() and target.read_bytes() != content:
                raise ValueError('Existing workspace uses different code. Preserve it and choose a new WORKSPACE.')
        WORKSPACE.mkdir(parents=True, exist_ok=True)
        for name, encoded in files.items():
            target = WORKSPACE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(base64.b64decode(encoded))
        index_path = WORKSPACE / 'source_index.json'
        index_text = json.dumps(SOURCE_INDEX, sort_keys=True, indent=2)
        if index_path.exists() and index_path.read_text() != index_text:
            raise ValueError('Existing source index differs; keep the original notebook for a resumed run.')
        index_path.write_text(index_text)
        sys.path.insert(0, str(WORKSPACE))
        os.chdir(WORKSPACE)
        print('Verified training sources:', len(files), '| workspace:', WORKSPACE)
    '''
    code(bootstrap.replace('__INDEX__', repr(index)).replace('__PAYLOAD__', payload)
         .replace('__PACKED_HASH__', hashlib.sha256(compressed).hexdigest()))
    markdown('''
        ## Settings

        Defaults use physical batch **16**, accumulation **1** (effective batch 16), 224px, up to 25 epochs per model.
        If GPU memory is insufficient, use batch 8/accumulation 2 **in a new workspace/run**, preserving the effective batch.
        Keep `num_workers=0` for reproducible epoch-boundary resume. Do not change settings when resuming.
        `RUN_NAME` stays unchanged when rerunning this cell in the current session.

        For a later session: attach your saved notebook output, set `RESUME_SOURCE` to its `pulmoscan_training` directory,
        set `RUN_NAME` to the original suite folder, and use the original notebook/code/settings.
        Prior Kaggle input mount paths must still exist. Resume uses the last completed epoch, not the middle of an epoch.
    ''')
    code('''
        from datetime import datetime, timezone
        DATA_ROOT = None  # Auto-detect, or paste the directory directly containing train/, val/, test/.
        PROFILE = 'v1'
        REQUIRE_GPU = True  # Set False deliberately to allow CPU; local training remains GPU-or-CPU automatic.
        BATCH_SIZE = 16
        ACCUMULATION_STEPS = 1
        EPOCHS = 25
        RUN_NAME = globals().get('RUN_NAME', 'kaggle-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        RESUME_SOURCE = None  # Example: '/kaggle/input/my-saved-training/pulmoscan_training'
        RUN_FINAL_TEST = False  # Leave False until both validation summaries have been reviewed.
        INCLUDE_RESUME_IN_ZIP = False  # True adds larger last.pt optimizer/RNG checkpoints to the download.
        print('Suite:', RUN_NAME)
    ''')
    markdown('''
        ## Runtime check

        Kaggle supplies torch and its matching GPU torchvision build. This cell keeps that pair installed,
        imports the training libraries, and installs only missing small extras. It never installs the local API dependencies.
        If torch/torchvision fail to import together, use a compatible Kaggle GPU runtime; do not install Windows CUDA wheels.
        Internet must be enabled for first-time official weight downloads and any missing extras.
    ''')
    code('''
        import importlib.util, subprocess
        extras = {'numpy': 'numpy>=1.24,<3', 'sklearn': 'scikit-learn>=1.3,<2',
                  'PIL': 'pillow>=10.4,<14', 'dotenv': 'python-dotenv>=1,<2'}
        missing = [requirement for module, requirement in extras.items() if importlib.util.find_spec(module) is None]
        if missing:
            subprocess.run([sys.executable, '-m', 'pip', 'install', *missing], check=True)
        # Load by file location to avoid a name collision with the installed Kaggle SDK.
        spec = importlib.util.spec_from_file_location('pulmoscan_notebook_runtime', WORKSPACE / 'kaggle/runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        os.environ['PULMOSCAN_DEVICE'] = 'cuda' if REQUIRE_GPU else 'auto'
        device = runtime.check_environment(REQUIRE_GPU)
        if RESUME_SOURCE and not (WORKSPACE / 'data').exists():
            runtime.restore_previous(RESUME_SOURCE, WORKSPACE)
        dataset_root = runtime.discover_dataset('/kaggle/input', DATA_ROOT)
        print('Read-only source dataset:', dataset_root)
    ''')
    markdown('''
        ## Audit and prepare

        Fully decode images; record byte/pixel hashes; reserve test-connected filename/duplicate groups;
        deduplicate exact pixels; split the remaining pool by candidate groups, stratified by class.
        Training-only augmentation is mild; validation/test use deterministic full-field letterboxing.
        No source images are copied, modified, or silently skipped. Every read during training checks the saved byte hash.

        This is a fresh audit of Kaggle's input, **not the damaged local source tree**. Local-only suspect exclusions
        are not carried across, so counts and manifest identity can differ from the laptop experiment.
        Filename IDs are heuristic, near-duplicates are not fully verified, and this pediatric benchmark does not establish
        clinical validity or external generalization. Never tune on the reserved test set.
    ''')
    code('''
        config_path, manifest_path = runtime.prepare(
            WORKSPACE, dataset_root, BATCH_SIZE, ACCUMULATION_STEPS, EPOCHS, profile=PROFILE)
        from scripts.check_training_data import main as check_data
        if check_data(['--manifest', str(manifest_path), '--passes', '2']):
            raise RuntimeError('Dataset integrity checks failed. Inspect the report; do not bypass hashes.')
    ''')
    markdown('''
        ## Preflight (no training)

        Check source hashes, official pretrained weight hashes, and finite forward outputs on the selected GPU.
        This does not establish training peak memory or accuracy.
    ''')
    code('''
        from scripts.train_models import cli as training_cli
        if training_cli(['--config', str(config_path), '--check']):
            raise RuntimeError('Preflight failed. Inspect the output before training.')
    ''')
    markdown('''
        ## Train both candidates

        This cell performs real training with live batch/epoch logs. DenseNet121 runs first, then EfficientNet-B0.
        New profiles select checkpoints using validation ROC-AUC from raw logit margins
        (validation loss breaks exact ties), with early stopping. Legacy saved profiles retain probability AUC.
        Class weights, warm-up, frozen BatchNorm statistics, mixed precision, gradient clipping, and accumulation are shared
        with the local workflow. Initial AMP scale reductions may occur; finite-loss checks remain enabled.
        A finalized threshold uses validation only, targeting at least 95% validation sensitivity while maximizing balanced accuracy.
        That target is an experiment policy, not guaranteed test sensitivity or clinical validation.

        Rerunning this cell skips completed candidates and resumes an incomplete candidate's `last.pt` when available.
        Stop/interruption before the first full epoch needs a new `RUN_NAME`. Save outputs before ending a Kaggle session.
    ''')
    code('''
        suite = runtime.run_or_resume(WORKSPACE, config_path, RUN_NAME)
        print('Training/validation complete:', suite)
    ''')
    markdown('''
        ## Review validation results

        Compare validation results before enabling final test evaluation. Larger GPU resources do not guarantee higher accuracy.
        Graphs use the recorded history only; no additional model inference is performed here.
    ''')
    code('''
        comparison = json.loads((suite / 'comparison.json').read_text())
        for row in comparison['candidates']:
            result = row['validation_at_selected_threshold']
            print(f"{row['architecture']}: best epoch={row['best_epoch']} | AUC={row['selection_metric_value']:.5f} | "
                  f"accuracy={result['accuracy']:.3%} | sensitivity={result['sensitivity']:.3%} | "
                  f"specificity={result['specificity']:.3%} | threshold={result['threshold']:.6f}")
            if 'calibration_at_selected_threshold' in row:
                print('Separate threshold-calibration holdout:', json.dumps(row['calibration_at_selected_threshold']))
        print('Validation-selected checkpoint:', comparison['recommended_checkpoint'])
        print('Pending candidates:', comparison['pending_candidates'])
        if importlib.util.find_spec('matplotlib'):
            import matplotlib.pyplot as plt
            fig, axes = plt.subplots(1, 2, figsize=(12, 4))
            for row in comparison['candidates']:
                history = json.loads((suite / row['architecture'] / 'history.json').read_text())
                epochs = [item['epoch'] for item in history]
                auc_field = 'roc_auc_logit_margin' if row.get('selection_metric') == 'val_logit_margin_auc' else 'roc_auc'
                axes[0].plot(epochs, [item['validation'][auc_field] for item in history], label=row['architecture'])
                axes[1].plot(epochs, [item['validation']['loss'] for item in history], label=row['architecture'])
            for axis, title in zip(axes, ('Validation ROC-AUC', 'Validation loss')):
                axis.set(xlabel='Epoch', title=title)
                axis.legend()
                axis.grid(alpha=.2)
            plt.tight_layout()
            plt.show()
    ''')
    markdown('''
        ## Optional final test — disabled by default

        After reviewing the completed validation comparison, set `RUN_FINAL_TEST=True` in the settings cell
        and run **only the settings cell and this cell**. Do not rerun training to optimize a test result.
        The validation-selected model and threshold are fixed. Existing final results are displayed, not recomputed.
        If you skip this step, the ZIP contains validation results only and says test evaluation is pending.
    ''')
    code('''
        final_path = suite / 'final_test_results.json'
        if RUN_FINAL_TEST and not final_path.exists():
            command = [sys.executable, '-u', 'scripts/evaluate_experiment.py', '--suite', str(suite)]
            if PROFILE == 'v2':
                command.append('--allow-reviewed-benchmark')
            subprocess.run(command, cwd=WORKSPACE, check=True)
        if final_path.exists():
            print(json.dumps(json.loads(final_path.read_text())['metrics'], indent=2))
        else:
            print('Test not evaluated. Review validation first, then explicitly enable this step.')
    ''')
    markdown('''
        ## Download models and evidence

        The ZIP contains both `best.pt` models, their preprocessing/threshold metadata, split manifests,
        histories, logs, validation comparison/predictions, optional final test results, exact source files,
        and SHA-256 checksums. `last.pt` is optional; it is always present in the saved workspace after a completed epoch.
        Save a notebook version including outputs before stopping the session; a download link alone does not persist a session.

        Download `pulmoscan_models.zip` from the link or Kaggle's output file browser.
        On your laptop: `python scripts/experiment_bundle.py import --archive "PATH_TO/pulmoscan_models.zip"`.
        This verifies and stores the experiment, without replacing the app's current model or starting a server.
        EfficientNet serving integration still needs review if EfficientNet wins; the current API supports DenseNet121.
    ''')
    code('''
        from scripts.experiment_bundle import export_suite, verify_bundle
        download = Path('/kaggle/working/pulmoscan_models.zip')
        if download.exists():
            # Explicitly choose a new filename if you exported before adding final test results.
            download = download.with_name('pulmoscan_models_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.zip')
        export_suite(suite, download, include_resume=INCLUDE_RESUME_IN_ZIP)
        receipt = verify_bundle(download)
        print('Verified download:', download, '| final test included:', receipt['test_evaluated'])
        from IPython.display import FileLink, display
        display(FileLink(str(download)))
        print('Also available in the Kaggle output browser. Save Version with outputs before ending this session.')
    ''')
    if profile == 'v2':
        for cell in cells:
            source = ''.join(cell['source'])
            source = source.replace('pulmoscan_training', 'pulmoscan_training_v2')
            source = source.replace("PROFILE = 'v1'", "PROFILE = 'v2'")
            source = source.replace("'kaggle-' + datetime", "'kaggle-v2-' + datetime")
            source = source.replace('A finalized threshold uses validation only, targeting',
                                    'A finalized threshold uses a separate calibration holdout after model selection, targeting')
            if source.startswith('## Optional final test'):
                source = textwrap.dedent('''
                    ## Optional repeat of the reviewed benchmark — disabled by default

                    The original 618-image test benchmark has already been inspected. It cannot become a fresh,
                    unbiased final holdout again. To record a diagnostic repeat, explicitly set `RUN_FINAL_TEST=True`
                    in the settings cell, run that cell, then run this cell. The output records
                    `evaluation_role=previously_reviewed_benchmark`. Do not choose a model or threshold using this score.
                    Independent holdout data is still required for final performance claims.
                ''').strip()
            cell['source'] = source.splitlines(keepends=True)
        warning = textwrap.dedent('''
            ## v2 experiment: test the compression-shortcut hypothesis

            The reviewed v1 run achieved 99.72% validation accuracy but 81.39% on the reserved benchmark,
            with 115 false-positive normal images. Metadata alone nearly separated development labels;
            normal test images had a markedly different bytes-per-pixel distribution.
            This suggests a dataset shortcut/shift, **not proof of its cause**.

            This v2 notebook starts a separate experiment: approximately **70% training / 15% model-selection
            validation / 15% threshold calibration** within eligible development data. Candidate groups and exact
            duplicates stay disjoint across all four splits, including the reviewed benchmark.
            Training-only JPEG variation (75% probability, quality 40–95 after resizing) tests compression robustness.
            Deterministic inference preprocessing stays the same. Neither change guarantees improved generalization.

            Use a new Kaggle notebook/session with this notebook. Keep v1 outputs unchanged. Review both validation
            and separate threshold-calibration results first. Do not enable repeated benchmark evaluation by default.
        ''').strip()
        cells.insert(1, dict(cell_type='markdown', id='v2-experiment-notes', metadata={}, source=warning.splitlines(keepends=True)))
    return dict(nbformat=4, nbformat_minor=5, metadata=dict(
        kernelspec=dict(display_name='Python 3', language='python', name='python3'),
        language_info=dict(name='python', version='3.11'),
        pulmoscan=dict(profile=profile, source_files_sha256=index, training_source='shared repository sources; generated by kaggle/build_notebook.py')),
        cells=cells)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Fail if the generated notebook differs from current sources')
    parser.add_argument('--profile', choices=['all', 'v1', 'v2'], default='all')
    args = parser.parse_args()
    for profile, output in [('v1', OUTPUT), ('v2', OUTPUT_V2)]:
        if args.profile not in {'all', profile}:
            continue
        generated = json.dumps(build_notebook(profile), indent=1, ensure_ascii=False) + '\n'
        if args.check:
            if not output.exists() or output.read_text(encoding='utf-8') != generated:
                raise SystemExit('Notebook is stale; run python kaggle/build_notebook.py.')
            print('PASS: standalone notebook matches current shared sources:', profile)
        else:
            output.write_text(generated, encoding='utf-8')
            print('Built:', output, '| bytes:', output.stat().st_size)


if __name__ == '__main__':
    main()
