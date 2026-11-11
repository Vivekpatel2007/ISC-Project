"""Patient follow-up permissions, protected image retrieval, and account changes."""
import io
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from src.api.auth import hash_password
from src.api.dependencies import get_db, get_storage, get_inference_engine
from src.api.main import create_app
from src.api.rate_limiter import login_rate_limiter
from src.security.database import MetadataDB
from src.security.secure_storage import SecureImageStorage
from src.security.exceptions import StorageError


@pytest.fixture
def workspace(tmp_path):
    db = MetadataDB(tmp_path / 'metadata.db')
    storage = SecureImageStorage(key=b'x' * 32, storage_dir=tmp_path / 'images', db_path=db.db_path)
    password = hash_password('OriginalPassword123!')
    for username, role in [('doctor_a', 'doctor'), ('doctor_b', 'doctor'), ('radio_a', 'radiologist')]:
        db.create_user(username, password, role, username)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_inference_engine] = lambda: SimpleNamespace(validate_and_decode_image=lambda raw: Image.open(io.BytesIO(raw)).load())
    login_rate_limiter.reset()
    client = TestClient(app)
    def login(username='doctor_a', password='OriginalPassword123!'):
        response = client.post('/auth/login', json=dict(username=username, password=password))
        assert response.status_code == 200, response.text
        return {'Authorization': 'Bearer ' + response.json()['access_token']}
    image = io.BytesIO()
    Image.new('L', (100, 100), 100).save(image, format='PNG')
    yield client, db, storage, login, image.getvalue()
    client.close()
    login_rate_limiter.reset()


def test_image_endpoint_authorizes_before_decrypting_and_never_caches(workspace, monkeypatch):
    client, db, storage, login, image = workspace
    scan = storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    route = f"/scans/{scan['scan_id']}/image"
    retrieve = Mock(wraps=storage.retrieve_image)
    monkeypatch.setattr(storage, 'retrieve_image', retrieve)
    assert client.get(route).status_code == 401
    assert client.get(route, headers=login('doctor_b')).status_code == 403
    retrieve.assert_not_called()
    response = client.get(route, headers=login())
    assert response.status_code == 200 and response.content == image
    assert response.headers['content-type'] == 'image/png'
    assert 'no-store' in response.headers['cache-control']
    assert 'bearer' not in str(response.headers).lower()
    assert client.get(route, headers=login('radio_a')).status_code == 200


def test_tampered_image_is_not_returned(workspace):
    client, _, storage, login, image = workspace
    scan = storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    file = storage._get_encrypted_file_path(scan['scan_id'])
    raw = bytearray(file.read_bytes()); raw[-1] ^= 1; file.write_bytes(raw)
    response = client.get(f"/scans/{scan['scan_id']}/image", headers=login())
    assert response.status_code == 409 and response.content != image


def test_account_rename_password_change_preserves_ownership_and_revokes_old_tokens(workspace):
    client, db, storage, login, image = workspace
    scan = storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    old = login()
    change = dict(username='doctor_new', full_name='Updated Name', current_password='OriginalPassword123!', new_password='NewPassword123!')
    response = client.put('/auth/me', headers=old, json=change)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['user']['full_name'] == 'Updated Name' and data['user']['role'] == 'doctor'
    assert not {'password_hash', 'auth_version'} & data['user'].keys()
    assert client.get('/auth/me', headers=old).status_code == 401
    assert db.get_scan(scan['scan_id'])['uploaded_by'] == 'doctor_new'
    assert client.post('/auth/login', json=dict(username='doctor_new', password='OriginalPassword123!')).status_code == 401
    updated = login('doctor_new', 'NewPassword123!')
    assert client.get(f"/scans/{scan['scan_id']}/image", headers=updated).content == image
    # A name-only update still revokes other existing sessions for the same username.
    change.update(current_password='NewPassword123!', new_password=None)
    assert client.put('/auth/me', headers=updated, json=change).status_code == 200
    assert client.get('/auth/me', headers=updated).status_code == 401


@pytest.mark.parametrize('extra,status', [
    ({'current_password': 'WrongPassword123!'}, 403),
    ({'username': 'doctor_b'}, 409),
    ({'role': 'admin'}, 422),
    ({'full_name': '   '}, 422),
    ({'new_password': 'é' * 40}, 422),
])
def test_account_changes_reject_wrong_password_conflicts_and_role_escalation(workspace, extra, status):
    client, db, _, login, _ = workspace
    old = login()
    change = dict(username='doctor_a', full_name='New Name', current_password='OriginalPassword123!', **{})
    change.update(extra)
    assert client.put('/auth/me', headers=old, json=change).status_code == status
    assert client.get('/auth/me', headers=old).status_code == 200
    assert db.get_user_by_username('doctor_a')['full_name'] == 'doctor_a'


def test_patient_rename_and_delete_are_scoped_to_ownership(workspace):
    client, db, storage, login, image = workspace
    own = [storage.store_image(image, 'PAT-001', uploaded_by='doctor_a') for _ in range(2)]
    other = storage.store_image(image, 'PAT-001', uploaded_by='doctor_b')
    token = login()
    assert client.put('/patients/PAT-001', headers=token, json={'patient_id': 'PAT-NEW'}).status_code == 200
    assert all(db.get_scan(scan['scan_id'])['patient_id'] == 'PAT-NEW' for scan in own)
    assert db.get_scan(other['scan_id'])['patient_id'] == 'PAT-001'
    assert client.delete('/patients/PAT-001', headers=token).status_code == 404
    response = client.delete('/patients/PAT-NEW', headers=token)
    assert response.status_code == 200 and response.json()['deleted_scans'] == 2
    assert all(not storage._get_encrypted_file_path(scan['scan_id']).exists() for scan in own)
    assert storage._get_encrypted_file_path(other['scan_id']).exists()
    assert len(db.list_users()) == 3


def test_follow_up_is_a_new_pending_scan_and_preserves_history(workspace):
    client, db, storage, login, image = workspace
    old = storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    db.update_prediction(old['scan_id'], 'PNEUMONIA', .9)
    response = client.post('/scans', headers=login(), data={'patient_id': 'PAT-001'}, files={'file': ('follow-up.png', image, 'image/png')})
    assert response.status_code == 201 and response.json()['prediction_status'] == 'PENDING'
    assert response.json()['predicted_class'] is None
    assert response.json()['scan_id'] != old['scan_id']
    # A later result updates the follow-up, not the historical scan.
    db.update_prediction(response.json()['scan_id'], 'NORMAL', .1)
    assert db.get_scan(old['scan_id'])['predicted_class'] == 'PNEUMONIA'
    assert db.list_scans_for_patient('PAT-001')[0]['predicted_class'] == 'NORMAL'


def test_patient_id_collision_does_not_merge_histories(workspace):
    client, db, storage, login, image = workspace
    storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    storage.store_image(image, 'PAT-002', uploaded_by='doctor_a')
    assert client.put('/patients/PAT-001', headers=login(), json={'patient_id': 'PAT-002'}).status_code == 409
    assert len(db.list_scans_for_patient('PAT-001')) == 1


def test_failed_file_delete_does_not_silently_remove_metadata(workspace, monkeypatch):
    _, db, storage, _, image = workspace
    scan = storage.store_image(image, 'PAT-001', uploaded_by='doctor_a')
    from pathlib import Path
    monkeypatch.setattr(Path, 'unlink', Mock(side_effect=PermissionError('locked file')))
    with pytest.raises(StorageError, match='retained'):
        storage.delete_scan(scan['scan_id'])
    assert db.get_scan(scan['scan_id'])
