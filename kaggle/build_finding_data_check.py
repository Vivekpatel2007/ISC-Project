"""Build a standalone, CPU-only finding-annotation intake notebook."""

import argparse
import hashlib
import json
from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'scripts/check_finding_annotations.py'
OUTPUT = ROOT / 'kaggle/PulmoScan_Finding_Data_Check.ipynb'


def build_notebook():
    cells = []

    def cell(kind, source):
        item = dict(cell_type=kind, id=f'finding-{len(cells):02d}', metadata={},
                    source=textwrap.dedent(source).strip().splitlines(keepends=True))
        if kind == 'code':
            item.update(execution_count=None, outputs=[])
        cells.append(item)

    cell('markdown', '''
        # PulmoScan: finding annotation intake (not training)

        Checks the **training CSVs only** for a finding/localization dataset.
        The existing NORMAL/PNEUMONIA folder dataset cannot supply finding boxes.

        Read `docs/FINDING_MODEL_NEXT_STEPS.md` in the project first.
        Obtain your own authorized access to [VinDr-PCXR/PediCXR](https://physionet.org/content/vindr-pcxr/1.0.0/).
        Use Kaggle only if your data agreement permits that processing and storage arrangement;
        private visibility alone does not establish permission. Do not publish restricted inputs or outputs.
        If permission is unclear, run the local annotation checker instead.

        In a permitted private notebook, attach the authorized training CSVs via **Add Input**.
        CPU is enough; Internet and package installation are unnecessary. No image files are read,
        no test annotations are inspected, and no model is trained or replaced.
        A successful check still needs image/label/split review before training.
    ''')
    source = SOURCE.read_text(encoding='utf-8')
    digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
    cell('code', f'''
        import hashlib
        import types
        SOURCE = {source!r}
        if hashlib.sha256(SOURCE.encode('utf-8')).hexdigest() != {digest!r}:
            raise ValueError('Notebook source checksum failed. Re-import an intact notebook.')
        checker = types.ModuleType('pulmoscan_finding_intake')
        exec(compile(SOURCE, '<embedded annotation checker>', 'exec'), checker.__dict__)
        print('Loaded annotation checker; no training or installations.')
    ''')
    cell('code', '''
        from pathlib import Path

        # Directory directly containing BOTH training CSVs. Leave None if only one matches.
        DATA_ROOT = None
        # Example: DATA_ROOT = '/kaggle/input/your-authorized-input/dataset'

        root = (Path(DATA_ROOT) if DATA_ROOT is not None
                else checker.discover_training_root(Path('/kaggle/input')))
        report = checker.audit_annotations(root / 'annotations_train.csv', root / 'image_labels_train.csv')
    ''')
    cell('code', '''
        from datetime import datetime, timezone
        import json
        from uuid import uuid4

        output = Path('/kaggle/working') / (
            'pulmoscan_finding_intake_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            + '_' + uuid4().hex[:8] + '.json')
        checker.save_report(report, output)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print('Report:', output.name)
        if report['errors']:
            raise ValueError('Annotation errors found. Review the saved report; do not start training.')
        print('Intake completed. Image, label and split review still required. Training is not ready.')
    ''')
    return dict(nbformat=4, nbformat_minor=5, cells=cells, metadata=dict(
        kernelspec=dict(display_name='Python 3', language='python', name='python3'),
        language_info=dict(name='python', version='3.11'),
        pulmoscan=dict(purpose='finding_annotation_intake_only', source_sha256=digest)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    generated = json.dumps(build_notebook(), indent=1, ensure_ascii=False) + '\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != generated:
            raise SystemExit('Notebook is stale; run python kaggle/build_finding_data_check.py.')
        print('PASS: finding intake notebook matches current sources.')
    else:
        OUTPUT.write_text(generated, encoding='utf-8')
        print('Built:', OUTPUT)


if __name__ == '__main__':
    main()
