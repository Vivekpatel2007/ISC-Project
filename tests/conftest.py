"""Isolate application settings before test collection imports the API modules."""

import base64
import os
from pathlib import Path
import secrets
import sys
import tempfile

import pytest

if 'src.api.config' in sys.modules:
    raise RuntimeError('Run pytest in a fresh Python process so application storage can be isolated before import.')

_workspace = tempfile.TemporaryDirectory(prefix='pulmoscan-pytest-')
_root = Path(_workspace.name).resolve()
_project = Path(__file__).resolve().parent.parent
_settings = {
    'APP_ENV': 'testing',
    'ENVIRONMENT': 'testing',
    'SECURE_STORAGE_DIR': str(_root / 'encrypted_images'),
    'METADATA_DB_PATH': str(_root / 'metadata.db'),
    'MODEL_CHECKPOINT_PATH': str(_project / 'models/densenet121_pneumonia_best.pth'),
    'IMAGE_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'),
    'JWT_SECRET_KEY': secrets.token_hex(32),
    'SEED_DEMO_USERS': 'true',
    'ENFORCE_HTTPS': 'false',
    'ENABLE_DOCS': 'true',
    'PULMOSCAN_DEVICE': 'cpu',
}
_original = {name: os.environ.get(name) for name in _settings}
os.environ.update(_settings)


@pytest.fixture(scope='session')
def isolated_test_root():
    return _root


@pytest.fixture(scope='session', autouse=True)
def bounded_test_cpu_threads():
    import torch
    original = torch.get_num_threads()
    torch.set_num_threads(min(original, 2))
    yield
    torch.set_num_threads(original)


def pytest_unconfigure(config):
    for name, original in _original.items():
        if original is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = original
    # Only this privately created temporary directory is cleaned up.
    if not _root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not _root.name.startswith('pulmoscan-pytest-'):
        raise RuntimeError('Unexpected test workspace; refusing cleanup.')
    _workspace.cleanup()
