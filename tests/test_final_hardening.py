"""Final regression checks for token validation, private responses and worker execution."""

import asyncio
from datetime import datetime, timedelta, timezone
import io
from types import SimpleNamespace

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import jwt
from PIL import Image
import pytest

from src.api.auth import DUMMY_PASSWORD_HASH, decode_access_token, hash_password, require_roles
from src.api.config import JWT_SECRET_KEY
from src.api.dependencies import get_db, get_storage, get_inference_engine
from src.api.main import create_app
from src.api.rate_limiter import SlidingWindowRateLimiter, login_rate_limiter
from src.api.request_limits import RequestBodyLimitMiddleware
from src.security.database import MetadataDB
from src.security.exceptions import StorageError
from src.security.secure_storage import SecureImageStorage


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    db = MetadataDB(tmp_path / 'metadata.db')
    password = bcrypt.hashpw(b'TestPassword123!', bcrypt.gensalt(rounds=4)).decode()
    for name, role in [('doctor_a', 'doctor'), ('radio_a', 'radiologist')]:
        db.create_user(name, password, role, name)
    storage = SecureImageStorage(b'x' * 32, tmp_path / 'images', db.db_path)
    observations = []
    def validate(raw):
        try:
            asyncio.get_running_loop()
            observations.append('event-loop')
        except RuntimeError:
            observations.append('worker')
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_inference_engine] = lambda: SimpleNamespace(validate_and_decode_image=validate)
    monkeypatch.setattr(login_rate_limiter, '_enabled', False)
    @app.get('/restricted-test')
    def restricted(user=Depends(require_roles('radiologist'))):
        return {'role': user['role']}
    client = TestClient(app)
    def login(name='doctor_a'):
        response = client.post('/auth/login', json={'username':name, 'password':'TestPassword123!'})
        assert response.status_code == 200
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    image = io.BytesIO()
    Image.new('L', (64, 64), 120).save(image, format='PNG')
    yield client, db, storage, login, image.getvalue(), observations
    client.close()


def claims():
    now = datetime.now(timezone.utc)
    return dict(sub='doctor_a', user_id='test-id', auth_version=0, iat=now, nbf=now, exp=now + timedelta(minutes=5))


@pytest.mark.parametrize('missing', ['exp', 'iat', 'nbf', 'sub', 'user_id', 'auth_version'])
def test_tokens_require_expiry_and_complete_identity(missing):
    payload = claims()
    del payload[missing]
    with pytest.raises(HTTPException) as result:
        decode_access_token(jwt.encode(payload, JWT_SECRET_KEY, algorithm='HS256'))
    assert result.value.status_code == 401


@pytest.mark.parametrize('change', [{'auth_version':True}, {'auth_version':-1}, {'auth_version':'0'}, {'user_id':42}, {'exp':None}])
def test_malformed_signed_claims_return_401_instead_of_server_errors(change):
    with pytest.raises(HTTPException) as result:
        decode_access_token(jwt.encode({**claims(), **change}, JWT_SECRET_KEY, algorithm='HS256'))
    assert result.value.status_code == 401


def test_legacy_role_helper_authenticates_and_fails_closed(workspace):
    client, _, _, login, _, _ = workspace
    assert client.get('/restricted-test').status_code == 401
    assert client.get('/restricted-test', headers=login()).status_code == 403
    assert client.get('/restricted-test', headers=login('radio_a')).status_code == 200


def test_openapi_describes_the_actual_json_login_and_bearer_token_auth(workspace):
    client, _, _, _, _, _ = workspace
    schema = client.app.openapi()
    assert schema['components']['securitySchemes']['BearerAuth']['type'] == 'http'
    assert schema['components']['securitySchemes']['BearerAuth']['scheme'] == 'bearer'
    assert 'application/json' in schema['paths']['/auth/login']['post']['requestBody']['content']
    response = client.get('/auth/me', headers={'Authorization':'Basic invalid'})
    assert response.status_code == 401


def test_auth_and_medical_metadata_are_not_cacheable(workspace):
    client, _, _, login, _, _ = workspace
    headers = login()
    for response in [client.get('/auth/me', headers=headers), client.get('/scans', headers=headers),
                     client.get('/auth/me'), client.post('/auth/login', json={'username':'doctor_a', 'password':'TestPassword123!'})]:
        assert response.headers['Cache-Control'] == 'no-store, private'


def test_validation_errors_do_not_echo_passwords_or_other_rejected_inputs(workspace):
    client, _, _, _, _, _ = workspace
    response = client.post('/auth/login', json={'username':'x', 'password':'k7Q!b'})
    assert response.status_code == 422
    assert 'k7Q!b' not in response.text
    assert all(set(error) == {'loc', 'msg', 'type'} for error in response.json()['detail'])


def test_unknown_user_dummy_hash_is_valid_cost_12_and_password_bytes_are_bounded():
    assert DUMMY_PASSWORD_HASH.startswith('$2b$12$')
    assert bcrypt.checkpw(b'dummy-not-a-real-account', DUMMY_PASSWORD_HASH.encode())
    with pytest.raises(ValueError, match='72 UTF-8 bytes'):
        hash_password('é' * 37)


def test_upload_decoding_and_storage_run_outside_the_event_loop(workspace):
    client, db, _, login, image, observations = workspace
    response = client.post('/scans', headers=login(), data={'patient_id':'PAT-001'}, files={'file':('scan.png', image, 'image/png')})
    assert response.status_code == 201
    assert observations == ['worker']
    assert len(db.list_all_scans()) == 1


def test_storage_failures_are_sanitized_and_do_not_add_records(workspace, monkeypatch):
    client, db, storage, login, image, _ = workspace
    def fail(**kwargs):
        raise StorageError('Private path C:/private/patient-encryption-key')
    monkeypatch.setattr(storage, 'store_image', fail)
    response = client.post('/scans', headers=login(), data={'patient_id':'PAT-001'}, files={'file':('scan.png', image, 'image/png')})
    assert response.status_code == 503 and 'Private path' not in response.text
    assert db.list_all_scans() == []


def test_rate_limiter_bounds_keys_prunes_idle_clients_and_rounds_retry_up(monkeypatch):
    now = [0.]
    monkeypatch.setattr('src.api.rate_limiter.time.monotonic', lambda: now[0])
    limiter = SlidingWindowRateLimiter(1, 60, max_keys=2)
    limiter.check('a')
    limiter.check('b')
    with pytest.raises(HTTPException):
        limiter.check('c')
    assert set(limiter._history) == {'a', 'b'}
    now[0] = .2
    with pytest.raises(HTTPException) as result:
        limiter.check('a')
    assert result.value.headers['Retry-After'] == '60'
    now[0] = 61
    limiter.check('c')
    assert set(limiter._history) == {'c'}


@pytest.mark.parametrize('streamed', [False, True])
def test_request_limit_rejects_declared_and_chunked_oversized_bodies(streamed):
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=10)
    completed = []
    @app.post('/')
    async def read_body(request: Request):
        data = await request.body()
        completed.append(True)
        return {'bytes': len(data)}
    with TestClient(app) as client:
        response = client.post('/', content=iter([b'12345', b'678901']) if streamed else b'12345678901')
        assert response.status_code == 413
        assert not completed
        assert client.post('/', content=b'1234567890').json() == {'bytes':10}
