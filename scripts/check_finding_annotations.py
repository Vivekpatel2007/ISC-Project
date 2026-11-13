"""Inspect finding annotation CSVs without reading images or training a model.

This is an intake check, not a complete dataset audit. No image identifiers or
example rows are exported. Test annotations are deliberately not discovered.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path


COORDINATES = ('x_min', 'y_min', 'x_max', 'y_max')
MISSING = {'', 'nan', 'none', 'null'}


def read_csv(path, required):
    payload = Path(path).read_bytes()
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig'), newline=''))
    columns = reader.fieldnames or []
    if len(set(columns)) != len(columns) or any(not name.strip() for name in columns):
        raise ValueError('CSV has empty or duplicate column names.')
    if not set(required).issubset(columns):
        raise ValueError('Unsupported CSV schema. Required columns: ' + ', '.join(required)
                         + '. Found: ' + ', '.join(columns))
    rows = list(reader)
    if not rows:
        raise ValueError('CSV contains no data rows.')
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('CSV contains rows with missing or extra fields.')
    return rows, {'sha256': hashlib.sha256(payload).hexdigest(), 'columns': columns, 'rows': len(rows)}


def audit_annotations(annotations, image_labels):
    boxes, box_source = read_csv(annotations, ('image_id', 'class_name', *COORDINATES))
    labels, label_source = read_csv(image_labels, ('image_id',))
    errors, warnings = Counter(), Counter()
    label_ids = {row['image_id'].strip() for row in labels}
    errors['empty_image_label_id'] = sum(not row['image_id'].strip() for row in labels)
    label_ids.discard('')
    warnings['additional_image_label_rows'] = len(labels) - len(label_ids)
    if 'rad_id' not in box_source['columns']:
        warnings['reviewer_column_absent'] = 1
    classes, class_images, class_ids = Counter(), defaultdict(set), defaultdict(set)
    class_names_by_id = defaultdict(set)
    positive_ids, background_ids, annotated_ids, seen = set(), set(), set(), set()
    for row in boxes:
        image_id, name = row['image_id'].strip(), row['class_name'].strip()
        if not image_id or not name:
            errors['empty_annotation_id_or_class'] += 1
            continue
        annotated_ids.add(image_id)
        if image_id not in label_ids:
            errors['annotation_image_missing_from_image_labels'] += 1
        values = [row[key].strip() for key in COORDINATES]
        if name.casefold() == 'no finding':
            background_ids.add(image_id)
            # Releases may encode the background sentinel as empty/NaN or zeros.
            present = [value for value in values if value.casefold() not in MISSING]
            try:
                if any(not math.isfinite(float(value)) or float(value) != 0 for value in present):
                    errors['background_row_has_coordinates'] += 1
            except ValueError:
                errors['background_row_has_coordinates'] += 1
            continue
        positive_ids.add(image_id)
        try:
            coordinates = tuple(float(value) for value in values)
        except ValueError:
            errors['invalid_box_coordinates'] += 1
            continue
        x_min, y_min, x_max, y_max = coordinates
        if (not all(math.isfinite(value) for value in coordinates)
                or min(coordinates) < 0 or x_max <= x_min or y_max <= y_min):
            errors['invalid_box_coordinates'] += 1
            continue
        reviewer = row.get('rad_id', '').strip()
        class_id = row.get('class_id', '').strip()
        if class_id:
            class_ids[name].add(class_id)
            class_names_by_id[class_id].add(name)
        key = (image_id, name, reviewer, coordinates)
        if key in seen:
            warnings['duplicate_box_rows'] += 1
            continue
        seen.add(key)
        classes[name] += 1
        class_images[name].add(image_id)
    errors['background_and_positive_same_image'] = len(background_ids & positive_ids)
    errors['class_name_has_multiple_ids'] = sum(len(values) > 1 for values in class_ids.values())
    errors['class_id_has_multiple_names'] = sum(len(values) > 1 for values in class_names_by_id.values())
    if not classes:
        errors['no_valid_finding_boxes'] = 1
    errors = {key: count for key, count in sorted(errors.items()) if count}
    warnings = {key: count for key, count in sorted(warnings.items()) if count}
    return {
        'schema_version': 1, 'stage': 'annotation_intake_only',
        'status': 'blocked' if errors else 'needs_review', 'training_ready': False,
        'inputs': {'annotations': box_source, 'image_labels': label_source},
        'counts': {
            'image_label_images': len(label_ids), 'annotated_images': len(annotated_ids),
            'images_with_finding_rows': len(positive_ids), 'explicit_no_finding_images': len(background_ids),
            'images_without_annotation_rows': len(label_ids - annotated_ids),
            'unique_valid_boxes': sum(classes.values()),
        },
        'candidate_classes': [
            {'name': name, 'boxes': classes[name], 'images': len(class_images[name]),
             'source_class_ids': sorted(class_ids[name])}
            for name in sorted(classes)
        ],
        'errors': errors, 'warnings': warnings,
        'limitations': [
            'Only CSV structure, class counts and box geometry were checked.',
            'Image-level label values and clinical meanings have not been validated.',
            'Missing box rows do not establish a normal or fully annotated image.',
            'No DICOM decoding, dimensions, orientation, pixel hashes or duplicate-image audit was performed.',
            'Box coordinates must still be verified against source image dimensions and previews.',
            'No train/validation/calibration split or cross-split patient/duplicate check was performed.',
            'No test-set metrics, training, model promotion or clinical validation was performed.',
        ],
    }


def discover_training_root(search_root):
    candidates = sorted({path.parent.resolve() for path in Path(search_root).rglob('annotations_train.csv')
                         if (path.parent / 'image_labels_train.csv').is_file()})
    if len(candidates) != 1:
        raise ValueError('Expected one dataset with annotations_train.csv and image_labels_train.csv; '
                         f'found {len(candidates)}. Set DATA_ROOT explicitly. The binary dataset is insufficient.')
    return candidates[0]


def save_report(report, destination):
    # Never overwrite an earlier audit or an accidentally selected input file.
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations', type=Path, required=True, help='Training bounding-box CSV')
    parser.add_argument('--image-labels', type=Path, required=True, help='Training image-level CSV')
    parser.add_argument('--output', type=Path, required=True, help='New report path; never overwritten')
    args = parser.parse_args()
    try:
        report = audit_annotations(args.annotations, args.image_labels)
        save_report(report, args.output)
    except (ValueError, OSError, UnicodeError, csv.Error) as exc:
        parser.exit(2, f'Annotation check failed: {exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    raise SystemExit(2 if report['errors'] else 0)


if __name__ == '__main__':
    main()
