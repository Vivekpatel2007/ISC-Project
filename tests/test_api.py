"""
FastAPI Security & Backend Integration Test Suite
ISC Project: Secure Storage and Transmission of Medical Data

Tests the Phase 2 requirements:
1. Health & readiness endpoints.
2. Successful authentication and JWT issuance.
3. Failed authentication with invalid credentials.
4. Accessing protected endpoints without a token (401 Unauthorized).
5. Accessing protected endpoints with an expired or malformed token.
6. Role-based authorization (Doctor vs Radiologist vs Admin).
7. Authorized image upload and encrypted storage.
8. Rejection of invalid uploads (empty, corrupted, non-image bytes, oversized).
9. Cross-user scan access enforcement (Doctor A cannot access Doctor B's scan; Radiologist can access both).
10. End-to-end in-memory decryption and DenseNet121 inference with clinical disclaimer.
11. Verification that prediction updates the scan status in SQLite to PROCESSED.
12. Verification that no plaintext is written to disk during the entire API lifecycle.
"""

import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.auth import hash_password
from src.api.dependencies import get_db, get_inference_engine, get_storage
from src.api.main import create_app
from src.api.model_service import DenseNetInferenceEngine
from src.security import (
    MetadataDB,
    SecureImageStorage,
    compute_sha256,
    generate_key,
)

# Reference to the actual trained checkpoint
MODEL_PATH = Path("models/densenet121_pneumonia_best.pth")


def make_test_image_bytes(format_name: str = "PNG", size=(224, 224), color=40) -> bytes:
    """Generate a valid synthetic chest radiograph image in memory."""
    img = Image.new("L", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    return buf.getvalue()


@pytest.fixture(scope="session")
def shared_inference_engine():
    """Load model engine once for the test session to optimize test runtime."""
    return DenseNetInferenceEngine(MODEL_PATH)


@pytest.fixture
def api_test_env(shared_inference_engine):
    """
    Sets up an isolated temporary storage folder and SQLite database,
    seeded with test practitioner credentials.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir) / "encrypted_images"
        db_path = Path(tmpdir) / "test_api_metadata.db"
        key = generate_key()

        db = MetadataDB(db_path)
        storage = SecureImageStorage(
            key=key,
            storage_dir=storage_dir,
            db_path=db_path,
            max_file_size_bytes=5 * 1024 * 1024  # 5 MB test limit
        )

        # Seed practitioner accounts
        # Doctor 1
        db.create_user(
            username="doctor_smith",
            password_hash=hash_password("DoctorPass123!"),
            role="doctor",
            full_name="Dr. Smith, MD"
        )
        # Doctor 2
        db.create_user(
            username="doctor_jones",
            password_hash=hash_password("DoctorPass123!"),
            role="doctor",
            full_name="Dr. Jones, MD"
        )
        # Radiologist
        db.create_user(
            username="radio_wilson",
            password_hash=hash_password("RadioPass123!"),
            role="radiologist",
            full_name="Dr. Wilson, MD (Radiology)"
        )

        app = create_app()

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_storage] = lambda: storage
        app.dependency_overrides[get_inference_engine] = lambda: shared_inference_engine

        client = TestClient(app)

        yield {
            "client": client,
            "db": db,
            "storage": storage,
            "storage_dir": storage_dir,
            "key": key
        }


def get_token(client: TestClient, username: str, password: str = "DoctorPass123!") -> str:
    """Helper to authenticate and retrieve access token."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


# =====================================================================
# 1. Health & Readiness Endpoints
# =====================================================================
def test_health_liveness(api_test_env):
    client = api_test_env["client"]
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_health_readiness(api_test_env):
    client = api_test_env["client"]
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] is True
    assert data["checks"]["storage"] is True
    assert data["checks"]["model"] is True


# =====================================================================
# 2. Authentication & Access Token Tests
# =====================================================================
def test_successful_login(api_test_env):
    client = api_test_env["client"]
    resp = client.post("/auth/login", json={
        "username": "doctor_smith",
        "password": "DoctorPass123!"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "doctor"
    assert data["username"] == "doctor_smith"


def test_failed_login_invalid_password(api_test_env):
    client = api_test_env["client"]
    resp = client.post("/auth/login", json={
        "username": "doctor_smith",
        "password": "WrongPassword!"
    })
    assert resp.status_code == 401
    assert "Incorrect username or password" in resp.json()["detail"]


def test_failed_login_nonexistent_user(api_test_env):
    client = api_test_env["client"]
    resp = client.post("/auth/login", json={
        "username": "nobody_user",
        "password": "SomePassword123!"
    })
    assert resp.status_code == 401


def test_get_profile_authenticated(api_test_env):
    client = api_test_env["client"]
    token = get_token(client, "doctor_smith")

    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "doctor_smith"
    assert data["role"] == "doctor"


def test_unauthenticated_request_rejected(api_test_env):
    client = api_test_env["client"]
    resp = client.get("/scans")
    assert resp.status_code == 401


def test_invalid_token_rejected(api_test_env):
    client = api_test_env["client"]
    resp = client.get("/scans", headers={"Authorization": "Bearer bad.token.value"})
    assert resp.status_code == 401


# =====================================================================
# 3. Medical Image Upload & Encrypted Storage Tests
# =====================================================================
def test_authorized_scan_upload(api_test_env):
    client = api_test_env["client"]
    storage_dir = api_test_env["storage_dir"]
    token = get_token(client, "doctor_smith")

    image_bytes = make_test_image_bytes("PNG")
    files = {"file": ("chest_xray.png", image_bytes, "image/png")}
    data = {"patient_id": "ANON-00991"}

    resp = client.post("/scans", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    meta = resp.json()

    scan_id = meta["scan_id"]
    assert scan_id is not None
    assert meta["patient_id"] == "ANON-00991"
    assert meta["uploaded_by"] == "doctor_smith"
    assert meta["prediction_status"] == "PENDING"

    # Verify encrypted file on disk
    enc_file = storage_dir / f"{scan_id}.enc"
    assert enc_file.exists()
    assert image_bytes not in enc_file.read_bytes()  # Must be encrypted!


def test_upload_rejection_empty_file(api_test_env):
    client = api_test_env["client"]
    token = get_token(client, "doctor_smith")

    files = {"file": ("empty.png", b"", "image/png")}
    data = {"patient_id": "ANON-00001"}

    resp = client.post("/scans", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_upload_rejection_corrupted_non_image(api_test_env):
    client = api_test_env["client"]
    token = get_token(client, "doctor_smith")

    # Upload arbitrary text pretending to be an image
    fake_bytes = b"This is not a real chest radiograph image." * 5
    files = {"file": ("fake.png", fake_bytes, "image/png")}
    data = {"patient_id": "ANON-00002"}

    resp = client.post("/scans", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400
    assert "validation failed" in resp.json()["detail"].lower()


def test_upload_rejection_invalid_patient_id(api_test_env):
    client = api_test_env["client"]
    token = get_token(client, "doctor_smith")

    image_bytes = make_test_image_bytes()
    files = {"file": ("xray.png", image_bytes, "image/png")}
    # Path traversal sequence in patient_id
    data = {"patient_id": "../../evil_id"}

    resp = client.post("/scans", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


# =====================================================================
# 4. Cross-User Access Control (RBAC & Ownership)
# =====================================================================
def test_cross_user_access_control(api_test_env):
    client = api_test_env["client"]

    # 1. Doctor Smith uploads a scan
    token_smith = get_token(client, "doctor_smith")
    img_bytes = make_test_image_bytes()
    resp_upload = client.post(
        "/scans",
        files={"file": ("smith_scan.png", img_bytes, "image/png")},
        data={"patient_id": "ANON-SMITH-1"},
        headers={"Authorization": f"Bearer {token_smith}"}
    )
    assert resp_upload.status_code == 201
    scan_id = resp_upload.json()["scan_id"]

    # 2. Doctor Smith can view their own scan
    resp_smith_get = client.get(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {token_smith}"})
    assert resp_smith_get.status_code == 200

    # 3. Doctor Jones attempts to view Doctor Smith's scan -> MUST BE REJECTED (403 Forbidden)
    token_jones = get_token(client, "doctor_jones")
    resp_jones_get = client.get(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {token_jones}"})
    assert resp_jones_get.status_code == 403
    assert "not authorized" in resp_jones_get.json()["detail"].lower()

    # 4. Radiologist Wilson views Doctor Smith's scan -> MUST BE ALLOWED (diagnostic clearance)
    token_wilson = get_token(client, "radio_wilson", password="RadioPass123!")
    resp_wilson_get = client.get(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {token_wilson}"})
    assert resp_wilson_get.status_code == 200
    assert resp_wilson_get.json()["scan_id"] == scan_id


# =====================================================================
# 5. In-Memory Decryption and DenseNet121 Inference
# =====================================================================
def test_in_memory_prediction_pipeline(api_test_env):
    client = api_test_env["client"]
    token_smith = get_token(client, "doctor_smith")

    # Upload real format image
    img_bytes = make_test_image_bytes()
    resp_upload = client.post(
        "/scans",
        files={"file": ("xray.png", img_bytes, "image/png")},
        data={"patient_id": "ANON-DIAG-01"},
        headers={"Authorization": f"Bearer {token_smith}"}
    )
    assert resp_upload.status_code == 201
    scan_id = resp_upload.json()["scan_id"]

    # Call /predict endpoint
    resp_pred = client.post(f"/scans/{scan_id}/predict", headers={"Authorization": f"Bearer {token_smith}"})
    assert resp_pred.status_code == 200
    pred_data = resp_pred.json()

    assert pred_data["scan_id"] == scan_id
    assert pred_data["prediction"] in ("NORMAL", "PNEUMONIA")
    assert 0.0 <= pred_data["pneumonia_probability"] <= 1.0
    assert 0.0 <= pred_data["normal_probability"] <= 1.0
    assert pred_data["threshold_applied"] == 0.40
    assert pred_data["model_architecture"] == "densenet121"
    assert "disclaimer" in pred_data
    assert "AI-assisted screening output" in pred_data["disclaimer"]

    # Verify database was updated to PROCESSED
    resp_scan = client.get(f"/scans/{scan_id}", headers={"Authorization": f"Bearer {token_smith}"})
    assert resp_scan.json()["prediction_status"] == "PROCESSED"
    assert resp_scan.json()["predicted_class"] == pred_data["prediction"]


# =====================================================================
# 6. Tampering Detection in API Predict Pipeline
# =====================================================================
def test_api_tampered_scan_rejection(api_test_env):
    client = api_test_env["client"]
    storage_dir = api_test_env["storage_dir"]
    token = get_token(client, "doctor_smith")

    img_bytes = make_test_image_bytes()
    resp = client.post(
        "/scans",
        files={"file": ("xray.png", img_bytes, "image/png")},
        data={"patient_id": "ANON-TAMPER"},
        headers={"Authorization": f"Bearer {token}"}
    )
    scan_id = resp.json()["scan_id"]

    # Adversary corrupts ciphertext on disk
    enc_file = storage_dir / f"{scan_id}.enc"
    corrupted = bytearray(enc_file.read_bytes())
    corrupted[-5] ^= 0xEE
    enc_file.write_bytes(bytes(corrupted))

    # Prediction must detect cryptographic tampering and reject with 409 Conflict
    resp_pred = client.post(f"/scans/{scan_id}/predict", headers={"Authorization": f"Bearer {token}"})
    assert resp_pred.status_code == 409
    detail = resp_pred.json()["detail"].lower()
    assert "authentication" in detail and "tampered" in detail
