"""Finding intake rejects unusable annotations and never turns a CSV check into training approval."""

import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_finding_annotations import (
    COORDINATES, audit_annotations, discover_training_root, save_report,
)


ROOT = Path(__file__).resolve().parent.parent


def write_csv(path, columns, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def dataset(root, box_rows=None):
    root.mkdir(parents=True, exist_ok=True)
    boxes = write_csv(root / 'annotations_train.csv', ['image_id', 'class_name', *COORDINATES, 'rad_id', 'class_id'],
                      box_rows if box_rows is not None else [
                          ['private-positive-id', 'Opacity', 10, 20, 40, 60, 'reader1', '3'],
                          ['private-background-id', 'No finding', '', 'NaN', '', '', 'reader1', '0'],
                      ])
    labels = write_csv(root / 'image_labels_train.csv', ['image_id', 'labels'], [
        ['private-positive-id', '[1, 0]'], ['private-background-id', '[0, 1]'], ['unboxed-id', '[0, 0]'],
    ])
    return boxes, labels


def test_counts_are_grounded_in_unique_boxes_and_no_identifiers_are_exported(tmp_path):
    boxes, labels = dataset(tmp_path)
    report = audit_annotations(boxes, labels)
    assert report['status'] == 'needs_review' and report['training_ready'] is False
    assert report['errors'] == {}
    assert report['candidate_classes'] == [{'name': 'Opacity', 'boxes': 1, 'images': 1, 'source_class_ids': ['3']}]
    assert report['counts']['images_without_annotation_rows'] == 1
    assert report['counts']['explicit_no_finding_images'] == 1
    encoded = json.dumps(report)
    assert 'private-positive-id' not in encoded and 'unboxed-id' not in encoded
    assert len(report['inputs']['annotations']['sha256']) == 64
    # There are no images in this fixture. A successful intake must not imply image validation.
    assert 'No DICOM decoding' in ' '.join(report['limitations'])


@pytest.mark.parametrize('coordinates', [
    [-1, 2, 3, 4], [2, 2, 2, 4], [1, 5, 4, 2], ['NaN', 2, 3, 4], [1, 2, 'inf', 4], ['', 2, 3, 4],
])
def test_invalid_boxes_block_progress(tmp_path, coordinates):
    boxes, labels = dataset(tmp_path, [['private-positive-id', 'Opacity', *coordinates, 'reader1', '3']])
    report = audit_annotations(boxes, labels)
    assert report['status'] == 'blocked'
    assert report['errors']['invalid_box_coordinates'] == 1
    assert report['counts']['unique_valid_boxes'] == 0


def test_conflicting_background_unknown_images_and_class_ids_are_reported(tmp_path):
    boxes, labels = dataset(tmp_path, [
        ['private-positive-id', 'Opacity', 1, 2, 3, 4, 'reader1', '3'],
        ['private-positive-id', 'No finding', 0, 0, 0, 0, 'reader1', '0'],
        ['unknown-id', 'Effusion', 1, 2, 3, 4, 'reader1', '3'],
        ['private-positive-id', 'Opacity', 1, 2, 3, 4, 'reader1', '4'],
    ])
    report = audit_annotations(boxes, labels)
    assert report['errors']['background_and_positive_same_image'] == 1
    assert report['errors']['annotation_image_missing_from_image_labels'] == 1
    assert report['errors']['class_id_has_multiple_names'] == 1
    assert report['errors']['class_name_has_multiple_ids'] == 1
    assert report['warnings']['duplicate_box_rows'] == 1


def test_wrong_schema_and_malformed_rows_are_not_silently_accepted(tmp_path):
    boxes, labels = dataset(tmp_path)
    boxes.write_text('image_id,class_name,x_min,y_min,x_max,y_max\nimage,Opacity,1,2,3,4,extra\n')
    with pytest.raises(ValueError, match='missing or extra'):
        audit_annotations(boxes, labels)
    boxes.write_text('patientId,x,y,width,height\nimage,1,2,3,4\n')
    with pytest.raises(ValueError, match='Unsupported CSV schema'):
        audit_annotations(boxes, labels)


def test_discovery_is_unambiguous_and_ignores_test_csvs(tmp_path):
    dataset(tmp_path / 'one')
    (tmp_path / 'annotations_test.csv').write_text('not read')
    assert discover_training_root(tmp_path) == (tmp_path / 'one').resolve()
    dataset(tmp_path / 'two')
    with pytest.raises(ValueError, match='found 2'):
        discover_training_root(tmp_path)


def test_report_cannot_overwrite_input_or_an_earlier_result(tmp_path):
    boxes, labels = dataset(tmp_path)
    original = boxes.read_bytes()
    report = audit_annotations(boxes, labels)
    with pytest.raises(FileExistsError):
        save_report(report, boxes)
    assert boxes.read_bytes() == original
    output = tmp_path / 'report.json'
    save_report(report, output)
    with pytest.raises(FileExistsError):
        save_report(report, output)


def test_cli_saves_a_blocked_report_and_returns_failure(tmp_path):
    boxes, labels = dataset(tmp_path, [['unknown', 'Opacity', 1, 2, 3, 4, 'reader1', '3']])
    output = tmp_path / 'report.json'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/check_finding_annotations.py'),
                             '--annotations', str(boxes), '--image-labels', str(labels), '--output', str(output)],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert json.loads(output.read_text())['status'] == 'blocked'


def test_standalone_notebook_runs_on_synthetic_csvs_without_images_or_installs(tmp_path):
    spec = importlib.util.spec_from_file_location('finding_notebook_builder', ROOT / 'kaggle/build_finding_data_check.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    notebook = builder.build_notebook()
    assert json.loads(builder.OUTPUT.read_text(encoding='utf-8')) == notebook
    input_root, output_root = tmp_path / 'input', tmp_path / 'output'
    dataset(input_root / 'pediatric')
    (input_root / 'pediatric' / 'annotations_test.csv').write_text('must not be parsed')
    namespace = {}
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source']).replace("Path('/kaggle/input')", f'Path({str(input_root)!r})')
            source = source.replace("Path('/kaggle/working')", f'Path({str(output_root)!r})')
            assert cell['outputs'] == [] and cell['execution_count'] is None
            exec(compile(source, '<finding notebook cell>', 'exec'), namespace)
    assert namespace['report']['training_ready'] is False
    assert len(list(output_root.glob('pulmoscan_finding_intake_*.json'))) == 1
