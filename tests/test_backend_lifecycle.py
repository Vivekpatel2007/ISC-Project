"""Concurrent initialization, read-only probes, artifact identity, and test isolation."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
from threading import Barrier, Lock
import time
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import torch

from src.api import config, dependencies, model_service
from src.api.routers.health import router
from src.security.database import MetadataDB


@pytest.mark.parametrize('getter,slot,constructor', [
    ('get_db', '_db_instance', 'MetadataDB'),
    ('get_storage', '_storage_instance', 'SecureImageStorage'),
    ('get_inference_engine', '_model_instance', 'DenseNetInferenceEngine'),
])
def test_concurrent_first_requests_publish_only_one_instance(monkeypatch, getter, slot, constructor):
    monkeypatch.setattr(dependencies, slot, None)
    monkeypatch.setattr(dependencies, 'get_storage_key', lambda: b'x' * 32)
    barrier, lock, calls = Barrier(8), Lock(), []
    result = object()

    def create(*_, **__):
        with lock:
            calls.append(1)
        time.sleep(.03)  # Allow competing threads to encounter the not-yet-published instance.
        return result

    monkeypatch.setattr(dependencies, constructor, create)

    def request(_):
        barrier.wait(timeout=5)
        return getattr(dependencies, getter)()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, range(8)))
    assert all(value is result for value in results) and len(calls) == 1


def test_failed_initialization_is_not_cached_and_can_be_retried(monkeypatch):
    monkeypatch.setattr(dependencies, '_model_instance', None)
    result = object()
    factory = Mock(side_effect=[RuntimeError('initialization failure'), result])
    monkeypatch.setattr(dependencies, 'DenseNetInferenceEngine', factory)
    with pytest.raises(RuntimeError):
        dependencies.get_inference_engine()
    assert dependencies.get_initialized_inference_engine() is None
    assert dependencies.get_inference_engine() is result and factory.call_count == 2


def test_readiness_before_initialization_returns_503_without_creating_anything(monkeypatch):
    for slot in ('_db_instance', '_storage_instance', '_model_instance'):
        monkeypatch.setattr(dependencies, slot, None)
    factories = []
    for name in ('MetadataDB', 'SecureImageStorage', 'DenseNetInferenceEngine'):
        factory = Mock(side_effect=AssertionError('Readiness must not initialize services'))
        monkeypatch.setattr(dependencies, name, factory)
        factories.append(factory)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get('/health/ready')
    assert response.status_code == 503
    assert response.json()['checks'] == dict(database=False, storage=False, model=False)
    assert response.json()['components']['model'] == 'not_initialized'
    for factory in factories:
        factory.assert_not_called()


def ready_client(tmp_path):
    db = MetadataDB(tmp_path / 'metadata.db')
    storage_dir = tmp_path / 'encrypted'
    storage_dir.mkdir()
    checkpoint = tmp_path / 'model.pth'
    checkpoint.write_bytes(b'placeholder for probe; never deserialized')
    info = dict(architecture='densenet121', class_names=['NORMAL', 'PNEUMONIA'], threshold=.4, device='cpu',
                checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(), probabilities_calibrated=False)
    engine = SimpleNamespace(model=object(), checkpoint_path=checkpoint, model_information=lambda: info)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependencies.get_initialized_db] = lambda: db
    app.dependency_overrides[dependencies.get_initialized_storage] = lambda: SimpleNamespace(storage_dir=storage_dir)
    app.dependency_overrides[dependencies.get_initialized_inference_engine] = lambda: engine
    return TestClient(app), db, engine, storage_dir


def test_readiness_identifies_loaded_model_without_paths_or_validation_claims(tmp_path):
    client, _, _, _ = ready_client(tmp_path)
    response = client.get('/health/ready')
    assert response.status_code == 200
    data = response.json()
    assert data['architecture'] == 'densenet121'
    assert data['class_names'] == ['NORMAL', 'PNEUMONIA']
    assert data['readiness_scope'] == 'operational_only'
    assert len(data['model']['checkpoint_sha256']) == 64
    assert str(tmp_path) not in response.text
    assert client.get('/health').json()['version'] == config.API_VERSION


def test_probe_does_not_recreate_deleted_database(tmp_path):
    client, db, _, _ = ready_client(tmp_path)
    db.db_path.unlink()
    response = client.get('/health/ready')
    assert response.status_code == 503 and not response.json()['checks']['database']
    assert not db.db_path.exists()


def test_probe_rejects_an_empty_database_without_creating_schema(tmp_path):
    client, db, _, _ = ready_client(tmp_path)
    db.db_path.write_bytes(b'')
    response = client.get('/health/ready')
    assert response.status_code == 503 and not response.json()['checks']['database']
    assert db.db_path.stat().st_size == 0


def test_probe_handles_unavailable_model_and_does_not_leak_errors(tmp_path):
    client, _, engine, _ = ready_client(tmp_path)
    engine.model_information = Mock(side_effect=RuntimeError('sensitive-local-path-or-credential'))
    response = client.get('/health/ready')
    assert response.status_code == 503 and response.json()['model'] is None
    assert 'sensitive-local-path-or-credential' not in response.text
    engine.model_information = lambda: {}
    assert client.get('/health/ready').status_code == 503


class TinyCheckpointModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.classifier = torch.nn.Linear(3, 2)


@pytest.mark.parametrize('metadata,message', [
    ({'manifest_sha256': 'a' * 64}, 'finalized'),
    ({'manifest_sha256': 'a' * 64, 'finalized': False}, 'finalized'),
    ({'manifest_sha256': 'invalid'}, 'manifest SHA-256'),
    ({'best_epoch': True}, 'best_epoch'),
])
def test_resume_and_provisional_artifacts_are_not_accepted_as_inference_models(tmp_path, monkeypatch, metadata, message):
    path = tmp_path / 'candidate.pt'
    torch.save(dict(model_state_dict=TinyCheckpointModel().state_dict(), **metadata), path)
    monkeypatch.setattr(model_service, 'select_device', lambda: torch.device('cpu'))
    constructor = Mock(side_effect=AssertionError('Reject metadata before building a network'))
    monkeypatch.setattr(model_service.models, 'densenet121', constructor)
    with pytest.raises(model_service.ModelInferenceError, match=message):
        model_service.DenseNetInferenceEngine(path)
    constructor.assert_not_called()


def test_model_identity_is_hash_of_the_exact_bytes_loaded(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.pt'
    torch.save(dict(model_state_dict=TinyCheckpointModel().state_dict()), path)
    original = path.read_bytes()
    load = torch.load
    inputs = []

    def capture(payload, **kwargs):
        inputs.append(payload)
        return load(payload, **kwargs)

    monkeypatch.setattr(model_service, 'select_device', lambda: torch.device('cpu'))
    monkeypatch.setattr(model_service.models, 'densenet121', lambda **_: TinyCheckpointModel())
    monkeypatch.setattr(model_service.torch, 'load', capture)
    engine = model_service.DenseNetInferenceEngine(path)
    assert len(inputs) == 1 and isinstance(inputs[0], io.BytesIO)
    assert engine.model_information()['checkpoint_sha256'] == hashlib.sha256(original).hexdigest()
    path.write_bytes(b'changed-on-disk-after-load')
    assert engine.model_information()['checkpoint_sha256'] == hashlib.sha256(original).hexdigest()


def test_application_test_settings_use_only_temporary_storage(isolated_test_root):
    assert config.METADATA_DB_PATH.is_relative_to(isolated_test_root)
    assert config.SECURE_STORAGE_DIR.is_relative_to(isolated_test_root)
    assert config.APP_ENV == 'testing'
    assert config.METADATA_DB_PATH.resolve() != (config.PROJECT_ROOT / 'secure_data/metadata.db').resolve()
