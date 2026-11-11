"""Locate saved artifacts and identical source data for inference-only inspection."""

import json
from pathlib import Path
import zipfile

from scripts.inspect_checkpoint import ArtifactReader


def discover_artifact(input_root, suite_name, explicit=None):
    if explicit:
        return Path(explicit).resolve()
    candidates = set()
    for path in Path(input_root).rglob('comparison.json'):
        if path.parent.name == suite_name:
            candidates.add(path.parent.resolve())
    for path in Path(input_root).rglob('bundle.json'):
        if path.stat().st_size <= 1024**2:
            try:
                index = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if index.get('suite_name') == suite_name and (path.parent / 'suite/comparison.json').is_file():
                candidates.add(path.parent.resolve())
    for path in Path(input_root).rglob('*.zip'):
        try:
            with zipfile.ZipFile(path) as archive:
                if 'bundle.json' not in archive.namelist() or archive.getinfo('bundle.json').file_size > 1024**2:
                    continue
                index = json.loads(archive.read('bundle.json'))
        except (ValueError, OSError, zipfile.BadZipFile):
            continue
        if index.get('suite_name') == suite_name:
            candidates.add(path.resolve())
    if not candidates:
        raise ValueError('Attach the saved v2 notebook output or upload the model ZIP as a private input. '
                         'Set ARTIFACT_PATH if automatic discovery cannot find the requested SUITE_NAME.')
    identities = set()
    for path in candidates:
        reader = ArtifactReader(path)
        try:
            comparison = reader.json('comparison.json')
            row = comparison['candidates'][0]
            identities.add((reader.suite_name, row['checkpoint_sha256'], row['manifest_sha256']))
        finally:
            reader.close()
    if len(identities) != 1:
        raise ValueError('Multiple distinct artifacts match. Set ARTIFACT_PATH explicitly; no model is selected from benchmark scores.')
    chosen = sorted(candidates, key=lambda path: (path.is_file(), str(path)))[0]
    print('Saved artifact:', chosen, flush=True)
    return chosen


def discover_dataset(input_root, explicit=None):
    def valid(root):
        return all((root / split / label).is_dir() for split in ('train', 'val', 'test')
                   for label in ('NORMAL', 'PNEUMONIA'))
    if explicit:
        root = Path(explicit).resolve()
        if not valid(root):
            raise ValueError('DATA_ROOT must directly contain train/, val/, test/ with both class folders.')
        return root
    roots = sorted({path.parent.resolve() for path in Path(input_root).rglob('train') if valid(path.parent)},
                   key=lambda path: (len(path.parts), str(path)))
    if not roots:
        raise ValueError('Attach the original chest-xray-pneumonia dataset.')
    shallowest = [root for root in roots if len(root.parts) == len(roots[0].parts)]
    if len(shallowest) != 1:
        raise ValueError('Multiple source datasets match. Set DATA_ROOT explicitly.')
    return shallowest[0]
