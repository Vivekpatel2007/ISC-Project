"""Generate a standalone inference-only notebook; embeds no training entry points."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import textwrap
import zlib

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'kaggle/PulmoScan_Logit_Diagnostics.ipynb'
SOURCES = ('src/compute.py', 'src/data_protocol.py', 'src/modeling.py', 'src/scoring.py',
           'scripts/experiment_bundle.py', 'scripts/inspect_checkpoint.py', 'kaggle/diagnostic_runtime.py')


def build_notebook():
    files = {name: (ROOT / name).read_bytes() for name in SOURCES}
    files.update({'src/__init__.py': b'', 'scripts/__init__.py': b''})
    index = {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()}
    packed = zlib.compress(json.dumps({name: base64.b64encode(payload).decode() for name, payload in files.items()},
                                      sort_keys=True, separators=(',', ':')).encode(), 9)
    cells = []

    def cell(kind, source):
        value = dict(cell_type=kind, id=f'cell-{len(cells):02d}', metadata={},
                     source=textwrap.dedent(source).strip().splitlines(keepends=True))
        if kind == 'code':
            value.update(execution_count=None, outputs=[])
        cells.append(value)

    cell('markdown', '''
        # PulmoScan: inspect saved v2 logits — no training

        This notebook inspects the **already selected DenseNet121 checkpoint**. It never fits a model,
        chooses another model, searches thresholds, or changes original artifacts. It does not download pretrained weights.

        Attach **two inputs**:
        1. The original **paultimothymooney/chest-xray-pneumonia** dataset.
        2. Your saved v2 notebook output containing suite **kaggle-v2-20261110T094413Z**. Alternatively,
           upload **pulmoscan_models (3).zip** as a private Kaggle dataset and attach it. ZIP and unpacked inputs are supported.

        Select an available GPU for inference. Internet is not needed if Kaggle's usual libraries are present.
        Import this notebook into a **new notebook/session**, not into the original training notebook.
        Use **Run All** here: there is no training cell. Keep your original training outputs unchanged.

        The existing benchmark is already reviewed. These diagnostics cannot establish new unbiased final accuracy.
        Download **pulmoscan_diagnostics.zip** when complete and save the notebook version including outputs.
    ''')
    bootstrap = '''
        import base64, hashlib, importlib.util, json, sys, zlib
        from pathlib import Path, PurePosixPath
        WORKSPACE = Path('/kaggle/working/pulmoscan_diagnostics')
        SOURCE_INDEX = __INDEX__
        SOURCE_PAYLOAD = '__PAYLOAD__'
        packed = base64.b64decode(SOURCE_PAYLOAD)
        if hashlib.sha256(packed).hexdigest() != '__HASH__':
            raise ValueError('Embedded diagnostic source checksum failed.')
        files = json.loads(zlib.decompress(packed))
        if set(files) != set(SOURCE_INDEX):
            raise ValueError('Embedded source index differs.')
        for name, encoded in files.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\\\' in name or ':' in name:
                raise ValueError('Unsafe embedded path.')
            content = base64.b64decode(encoded)
            if hashlib.sha256(content).hexdigest() != SOURCE_INDEX[name]:
                raise ValueError('Embedded source checksum differs: ' + name)
            target = WORKSPACE.joinpath(*relative.parts)
            if not target.resolve().is_relative_to(WORKSPACE.resolve()):
                raise ValueError('Source escaped the diagnostic workspace.')
            if target.exists() and target.read_bytes() != content:
                raise ValueError('Existing diagnostic workspace uses different code. Choose a new WORKSPACE.')
        for name, encoded in files.items():
            target = WORKSPACE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(base64.b64decode(encoded))
        index_path = WORKSPACE / 'source_index.json'
        index_path.write_text(json.dumps(SOURCE_INDEX, sort_keys=True, indent=2))
        sys.path.insert(0, str(WORKSPACE))
        print('Verified inference-only source files:', len(files))
    '''
    cell('code', bootstrap.replace('__INDEX__', repr(index)).replace('__PAYLOAD__', base64.b64encode(packed).decode())
         .replace('__HASH__', hashlib.sha256(packed).hexdigest()))
    cell('markdown', '''
        ## Settings and input detection

        The default suite is the reviewed v2 export. Auto-detection accepts duplicate representations of the same
        checkpoint, but refuses distinct matching models. Set paths explicitly if needed.
        `INCLUDE_REVIEWED_BENCHMARK=True` is deliberate: it investigates the already observed errors.
        Set False for validation/calibration only. The original saved threshold remains unchanged.
        `PRECISION='saved'` follows the checkpoint's AMP preference on CUDA; device/library changes may affect reproduction.
    ''')
    cell('code', '''
        from datetime import datetime, timezone
        SUITE_NAME = 'kaggle-v2-20261110T094413Z'
        ARTIFACT_PATH = None  # ZIP, unpacked bundle root, or saved suite folder containing comparison.json.
        DATA_ROOT = None  # Directory directly containing train/, val/, test/.
        REQUIRE_GPU = True  # Set False deliberately for automatic GPU/CPU selection.
        INCLUDE_REVIEWED_BENCHMARK = True
        PRECISION = 'saved'
        BATCH_SIZE = 16
        DIAGNOSTIC_NAME = 'inspection-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')

        for module in ('torch', 'torchvision', 'numpy', 'sklearn', 'PIL'):
            if importlib.util.find_spec(module) is None:
                raise RuntimeError('Missing runtime library: ' + module + '. Use a complete Kaggle Python GPU runtime.')
        import torch, torchvision
        from src.compute import select_device
        device = select_device('cuda' if REQUIRE_GPU else 'auto')
        print('torch', torch.__version__, '| torchvision', torchvision.__version__, '| device', device)
        spec = importlib.util.spec_from_file_location('pulmoscan_diagnostic_runtime', WORKSPACE / 'kaggle/diagnostic_runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        artifact = runtime.discover_artifact('/kaggle/input', SUITE_NAME, ARTIFACT_PATH)
        data_root = runtime.discover_dataset('/kaggle/input', DATA_ROOT)
        print('Source dataset:', data_root)
    ''')
    cell('markdown', '''
        ## Fixed-checkpoint inference

        Verify the checkpoint checksum, original manifest, split boundaries, and all original source image hashes.
        A different mount path is allowed only when the original bytes still match; the manifest is not rewritten.
        Then record both logits, their difference, historical float32 softmax scores, stable log probabilities,
        and per-image log loss. No optimizer or gradient updates occur.

        AUC from the logit difference can retain ordering lost when probabilities round to exactly 1.0.
        This does **not** repair wrong predictions at the saved threshold or calibrate model probabilities.
        Reference comparisons report any changed decisions instead of claiming exact reproduction across runtimes.
    ''')
    cell('code', '''
        from scripts.inspect_checkpoint import inspect, export_diagnostics
        output = WORKSPACE / 'results' / DIAGNOSTIC_NAME
        report = inspect(artifact, data_root, output,
                         include_reviewed_benchmark=INCLUDE_REVIEWED_BENCHMARK,
                         batch_size=BATCH_SIZE,
                         device_preference='cuda' if REQUIRE_GPU else 'auto',
                         precision=PRECISION, plots=True)
        for split, result in report['splits'].items():
            original = result['metrics_at_saved_threshold']
            print(f"{split}: probability AUC={original['roc_auc']:.6f} | margin AUC={result['roc_auc_logit_margin']:.6f} | "
                  f"accuracy at SAVED cut={original['accuracy']:.2%} | loss={result['loss_from_logits']:.6f}")
            print('Saturation:', json.dumps(result['score_saturation']))
            print('Reference agreement:', json.dumps(result.get('reference_comparison', {})))
    ''')
    cell('markdown', '''
        ## Inspect images and download

        The gallery shows normal images incorrectly flagged at the unchanged threshold, ordered by raw margin.
        These are model errors on public benchmark images, not clinical diagnoses. Raw-margin AUC and stable
        log loss are diagnostics; do not use this reviewed benchmark to choose another model or threshold.

        The ZIP contains the report, per-image CSVs, plots, source checksums, and a checksum index.
        It does not contain another trained model. Download it and send it back for review.
    ''')
    cell('code', '''
        from IPython.display import Image as DisplayImage, FileLink, display
        for filename in ('logit_distributions.png', 'false_positive_examples.png'):
            if (output / filename).exists():
                display(DisplayImage(filename=str(output / filename), width=1100))
        (output / 'diagnostic_source_index.json').write_text(json.dumps(SOURCE_INDEX, sort_keys=True, indent=2))
        download = Path('/kaggle/working/pulmoscan_diagnostics.zip')
        if download.exists():
            download = download.with_name('pulmoscan_diagnostics_' + DIAGNOSTIC_NAME + '.zip')
        export_diagnostics(output, download)
        print('Download:', download)
        display(FileLink(str(download)))
        print('Also available in Kaggle output files. Save Version including outputs before ending the session.')
    ''')
    return dict(nbformat=4, nbformat_minor=5, cells=cells, metadata=dict(
        kernelspec=dict(display_name='Python 3', language='python', name='python3'),
        language_info=dict(name='python', version='3.11'),
        pulmoscan=dict(mode='fixed_checkpoint_diagnostic', source_files_sha256=index)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    content = json.dumps(build_notebook(), indent=1, ensure_ascii=False) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != content:
            raise SystemExit('Diagnostic notebook is stale; run python kaggle/build_diagnostics_notebook.py.')
        print('PASS: inference-only notebook matches current diagnostic sources.')
    else:
        OUTPUT.write_text(content, encoding='utf-8')
        print('Built:', OUTPUT, '| bytes:', OUTPUT.stat().st_size)


if __name__ == '__main__':
    main()
