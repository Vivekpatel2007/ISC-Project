"""Regression checks for inference validation and the read-only dataset audit."""

from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
from threading import Lock
import time
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
from PIL import Image
import pytest
import torch

from scripts.audit_dataset import audit_dataset, filename_group
from src.api.model_service import DenseNetInferenceEngine, InvalidImagePayloadError, ModelInferenceError


@pytest.mark.parametrize('name,label,expected', [
    ('NORMAL2-IM-0383-0001.jpeg', 'NORMAL', 'NORMAL2-IM-0383'),
    ('NORMAL2-IM-0384-0001.jpeg', 'NORMAL', 'NORMAL2-IM-0384'),
    ('IM-0115-0001-0002.jpeg', 'NORMAL', 'IM-0115'),
    ('person1000_bacteria_2931.jpeg', 'PNEUMONIA', 'PERSON1000'),
    ('unknown.jpeg', 'NORMAL', None),
])
def test_filename_groups_keep_normal_subject_numbers(name, label, expected):
    assert filename_group(name, label) == expected


def test_audit_distinguishes_pixel_duplicates_from_byte_duplicates(tmp_path):
    for index, split in enumerate(('train', 'val', 'test')):
        for label in ('NORMAL', 'PNEUMONIA'):
            (tmp_path / split / label).mkdir(parents=True)
        Image.new('L', (64, 64), 30 * (index + 1)).save(
            tmp_path / split / 'NORMAL' / f'IM-{index + 1:04d}-0001.jpeg')
        person, color = (99, 150) if split == 'val' else (12, 120)
        extension = 'png' if split == 'test' else 'jpeg'
        Image.new('L', (64, 64), color).save(
            tmp_path / split / 'PNEUMONIA' / f'person{person}_bacteria_1.{extension}')
    report = audit_dataset(tmp_path, progress=lambda _: None)
    assert report['total_images'] == 6
    assert report['decode_errors'] == []
    pair = report['overlaps']['train/test']
    assert pair['candidate_subjects']['PNEUMONIA']['count'] == 1
    assert pair['byte_duplicate_groups'] == 0
    assert pair['pixel_duplicate_groups'] == 1
    assert report['manifest_sha256'] == audit_dataset(tmp_path, progress=lambda _: None)['manifest_sha256']


def test_audit_reports_missing_classes_and_corrupt_images(tmp_path):
    folder = tmp_path / 'train' / 'NORMAL'
    folder.mkdir(parents=True)
    (folder / 'bad.jpeg').write_bytes(b'not an image')
    report = audit_dataset(tmp_path, progress=lambda _: None)
    assert len(report['missing_folders']) == 5
    assert report['decode_errors'][0]['path'] == 'train/NORMAL/bad.jpeg'
    assert report['total_images'] == 0


@pytest.mark.parametrize('metadata,message', [
    ({'architecture': 'other'}, 'architecture'),
    ({'class_names': ['PNEUMONIA', 'NORMAL']}, 'class order'),
    ({'class_to_idx': {'NORMAL': 1, 'PNEUMONIA': 0}}, 'class order'),
    ({'threshold': float('nan')}, 'threshold'),
    ({'threshold': 1.1}, 'threshold'),
    ({'normalization': {'mean': [0, 0, 0], 'std': [1, 0, 1]}}, 'normalization'),
    ({'image_size': -224}, 'image_size'),
    ({'preprocessing': {'resize_mode': 'unknown'}}, 'preprocessing'),
])
def test_invalid_checkpoint_metadata_is_rejected_before_model_construction(tmp_path, monkeypatch, metadata, message):
    from src.api import model_service
    checkpoint = tmp_path / 'invalid.pth'
    torch.save({'model_state_dict': {}, **metadata}, checkpoint)
    monkeypatch.setattr(model_service, 'select_device', lambda: torch.device('cpu'))
    with pytest.raises(ModelInferenceError, match=message):
        DenseNetInferenceEngine(checkpoint)


def test_truncated_jpeg_that_passes_header_verification_returns_validation_error():
    buffer = io.BytesIO()
    Image.new('L', (64, 64), 100).save(buffer, format='JPEG')
    truncated = buffer.getvalue()[:-2]
    with Image.open(io.BytesIO(truncated)) as image:
        image.verify()
    engine = object.__new__(DenseNetInferenceEngine)
    with pytest.raises(InvalidImagePayloadError, match='Malformed'):
        engine.validate_and_decode_image(truncated)


def stub_engine(model):
    engine = object.__new__(DenseNetInferenceEngine)
    engine.device = torch.device('cpu')
    engine.threshold, engine.best_epoch = 0.4, 5
    engine._prediction_lock = Lock()
    engine.validate_and_decode_image = lambda _: Image.new('RGB', (32, 32))
    engine.transform = lambda _: torch.zeros((3, 32, 32))
    engine.model = model
    return engine


@pytest.mark.parametrize('logits', [torch.tensor([[float('nan'), 1.0]]), torch.zeros(1, 3)])
def test_invalid_model_outputs_do_not_become_predictions(logits):
    engine = stub_engine(lambda _: logits)
    with pytest.raises(ModelInferenceError, match='class scores'):
        engine.predict(b'input')


@pytest.mark.parametrize('threshold', [float('nan'), float('inf'), -0.1, 1.1, True])
def test_invalid_threshold_override_is_rejected(threshold):
    engine = stub_engine(lambda _: torch.zeros(1, 2))
    with pytest.raises(ModelInferenceError, match='threshold'):
        engine.predict(b'input', custom_threshold=threshold)


def test_shared_model_forward_passes_do_not_overlap():
    state = {'active': 0, 'maximum': 0}
    state_lock = Lock()

    def model(_):
        with state_lock:
            state['active'] += 1
            state['maximum'] = max(state['maximum'], state['active'])
        time.sleep(0.01)
        with state_lock:
            state['active'] -= 1
        return torch.zeros(1, 2)

    engine = stub_engine(model)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(engine.predict, [b'image'] * 8))
    assert len(results) == 8
    assert state['maximum'] == 1


def test_upload_read_is_bounded_before_validation(monkeypatch):
    import asyncio
    from src.api.routers import scans
    monkeypatch.setattr(scans, 'MAX_IMAGE_SIZE_BYTES', 8)
    upload = Mock(read=AsyncMock(return_value=b'x' * 9))
    storage, engine = Mock(), Mock()
    with pytest.raises(HTTPException) as error:
        asyncio.run(scans.upload_scan(upload, 'ANON-001', {'username': 'doctor'}, storage, engine))
    assert error.value.status_code == 413
    upload.read.assert_awaited_once_with(9)
    engine.validate_and_decode_image.assert_not_called()
    storage.store_image.assert_not_called()
