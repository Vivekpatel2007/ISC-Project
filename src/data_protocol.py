"""Auditable, source-backed split manifests for the Kermany chest X-ray dataset."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

CLASSES = ('NORMAL', 'PNEUMONIA')
ROOT = Path(__file__).resolve().parent.parent


class DatasetIntegrityError(ValueError):
    """The original prepared dataset can no longer be read unchanged."""


def read_verified_image(root, row):
    path = source_file(root, row['path'])
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise DatasetIntegrityError(f'Source image is unreadable: {path}: {error}') from error
    actual = hashlib.sha256(payload).hexdigest()
    if actual != row['sha256']:
        raise DatasetIntegrityError(
            f"Source image changed after preparation: {path}\n"
            f"Expected SHA-256: {row['sha256']}\nActual SHA-256:   {actual}")
    return payload


def filename_group(filename, label):
    pattern = r'^(person\d+)(?:_|$)' if label == 'PNEUMONIA' else r'^(NORMAL2-IM-\d+|IM-\d+)(?:-|$)'
    match = re.match(pattern, Path(filename).stem, re.IGNORECASE)
    return match.group(1).upper() if match else None


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_file(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Dataset manifest contains a path outside its source root.')
    return path


def plan_splits(audit, train_ratio=0.85, seed=42, suspect_paths=()):
    """Reserve test components; balance train/validation candidate groups by class."""
    from sklearn.model_selection import GroupShuffleSplit
    if not 0.5 <= train_ratio < 1:
        raise ValueError('train_ratio must be at least 0.5 and below 1.')
    if audit['missing_folders'] or audit['decode_errors'] or audit['api_incompatible_images']:
        raise ValueError('Resolve the dataset audit failures before preparing an experiment.')
    rows = [dict(row) for row in audit['images']]
    if not rows or len({row['path'] for row in rows}) != len(rows):
        raise ValueError('Audit is empty or contains repeated paths.')
    parents = list(range(len(rows)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left, right):
        parents[find(right)] = find(left)

    subjects, pixels = {}, {}
    for index, row in enumerate(rows):
        subject = filename_group(Path(row['path']).name, row['label'])
        if subject is None or row['label'] not in CLASSES or row['split'] not in {'train', 'val', 'test'}:
            raise ValueError(f"Unsupported label, split, or subject filename: {row['path']}")
        row['candidate_subject'] = subject
        key = (row['label'], subject)
        if key in subjects:
            union(index, subjects[key])
        subjects[key] = index
        if row['pixel_sha256'] in pixels:
            previous = pixels[row['pixel_sha256']]
            if rows[previous]['label'] != row['label']:
                raise ValueError('Identical decoded pixels have conflicting labels.')
            union(index, previous)
        pixels[row['pixel_sha256']] = index
    components = defaultdict(list)
    for index, row in enumerate(rows):
        components[find(index)].append(row['path'])
    ids = {key: hashlib.sha256('\n'.join(sorted(paths)).encode()).hexdigest()
           for key, paths in components.items()}
    reserved = {find(index) for index, row in enumerate(rows) if row['split'] == 'test'}
    suspect_paths = set(suspect_paths)
    suspect_groups = {find(index) for index, row in enumerate(rows) if row['path'] in suspect_paths}
    result = {'train': [], 'val': [], 'test': []}
    excluded, candidates, seen_test, seen_pool = [], [], set(), set()
    for index, row in enumerate(rows):
        entry = {key: row[key] for key in ('path', 'label', 'sha256', 'pixel_sha256', 'candidate_subject')}
        entry.update(group=ids[find(index)], source_split=row['split'])
        if find(index) in suspect_groups:
            excluded.append(dict(entry, reason='component_with_changed_source'))
        elif row['split'] == 'test':
            if row['pixel_sha256'] in seen_test:
                excluded.append(dict(entry, reason='duplicate_pixels_within_test'))
            else:
                result['test'].append(entry)
                seen_test.add(row['pixel_sha256'])
        elif find(index) in reserved:
            excluded.append(dict(entry, reason='candidate_or_duplicate_component_reserved_for_test'))
        elif row['pixel_sha256'] in seen_pool:
            excluded.append(dict(entry, reason='duplicate_pixels_in_training_pool'))
        else:
            candidates.append(entry)
            seen_pool.add(row['pixel_sha256'])
    # Balance image counts using labels only, never predictions or test metrics.
    for label in CLASSES:
        subset = [row for row in candidates if row['label'] == label]
        groups = [row['group'] for row in subset]
        if len(set(groups)) < 2:
            raise ValueError(f'Need at least two eligible candidate groups for {label}.')
        splitter = GroupShuffleSplit(n_splits=64, train_size=train_ratio, random_state=seed)
        target = len(subset) * (1 - train_ratio)
        train_indices, val_indices = min(splitter.split(subset, groups=groups),
                                        key=lambda pair: abs(len(pair[1]) - target))
        result['train'].extend(subset[index] for index in train_indices)
        result['val'].extend(subset[index] for index in val_indices)
    for split in result:
        result[split].sort(key=lambda row: row['path'])
    validate_boundaries(result)
    return dict(splits=result, excluded=excluded, train_ratio=train_ratio, seed=seed,
                protocol='candidate-components-v1', raw_test_images=sum(row['split'] == 'test' for row in rows),
                counts={split: dict(Counter(row['label'] for row in items)) for split, items in result.items()},
                exclusions=dict(Counter(row['reason'] for row in excluded)),
                caveat='Filename-derived subjects are not authoritative patient identities. '
                       'Candidate groups and exact decoded pixels are disjoint by construction; near-duplicates remain unverified.')


def validate_boundaries(splits):
    for split in ('train', 'val', 'test'):
        if set(row['label'] for row in splits[split]) != set(CLASSES):
            raise ValueError(f'{split} must contain both classes.')
    for field in ('path', 'group', 'pixel_sha256', 'sha256', 'candidate_subject'):
        seen = set()
        for split in ('train', 'val', 'test'):
            values = {row[field] for row in splits[split]}
            if seen & values:
                raise ValueError(f'Cross-split {field} overlap detected.')
            seen.update(values)


def load_manifest(path, verify_files=True, progress=print):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    payload = {key: value for key, value in manifest.items() if key != 'manifest_sha256'}
    if manifest.get('schema_version') != 1 or digest_json(payload) != manifest.get('manifest_sha256'):
        raise ValueError('Split manifest version or digest is invalid.')
    validate_boundaries(manifest['splits'])
    root = Path(manifest['source_root'])
    root = root if root.is_absolute() else ROOT / root
    for index, row in enumerate(row for items in manifest['splits'].values() for row in items):
        path = source_file(root, row['path'])
        if verify_files:
            read_verified_image(root, row)
        if verify_files and (index + 1) % 1000 == 0:
            progress(f'Checked {index + 1} source image hashes ...')
    return manifest, root
