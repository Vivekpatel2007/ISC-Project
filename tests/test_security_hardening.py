"""
Security Hardening & Regression Test Suite
ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission

Tests verified security fixes for Phase 4:
1. Production configuration fail-fast (missing/weak secrets rejection)
2. Rate limiting on authentication and inference
3. OWASP security response headers
4. Pillow decompression bomb and image dimension protections
5. Encryption key persistence and recovery verification
6. Strict role-based access control and isolation
"""

import io
import os
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from src.api.config import validate_production_config
from src.api.main import create_app
from src.api.model_service import DenseNetInferenceEngine, InvalidImagePayloadError
from src.api.rate_limiter import login_rate_limiter, inference_rate_limiter
from src.security.encryption import encrypt_bytes, decrypt_bytes
from src.security.exceptions import AuthenticationError, InvalidKeyError
from src.security.key_manager import generate_key, key_to_base64
from src.security.secure_storage import SecureImageStorage


@pytest.fixture
def client():
    """Create test client with fresh lifespan and reset rate limiters."""
    login_rate_limiter.reset()
    inference_rate_limiter.reset()
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    login_rate_limiter.reset()
    inference_rate_limiter.reset()


def _get_auth_token(client: TestClient, username: str, password: str) -> str:
    """Helper to authenticate a practitioner."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# =====================================================================
# 1. Production Configuration Fail-Fast Tests
# =====================================================================
def test_production_fails_on_default_jwt_secret(monkeypatch):
    """Production mode must refuse to start if using the default development JWT secret."""
    monkeypatch.setattr("src.api.config.IS_PRODUCTION", True)
    monkeypatch.setattr("src.api.config.JWT_SECRET_KEY", "insecure-dev-jwt-secret-key-replace-in-production-32bytes")
    
    with pytest.raises(RuntimeError, match="FATAL SECURITY CONFIGURATION: In production mode"):
        validate_production_config()


def test_production_fails_on_short_jwt_secret(monkeypatch):
    """Production mode must refuse to start if JWT secret is shorter than 32 characters."""
    monkeypatch.setattr("src.api.config.IS_PRODUCTION", True)
    monkeypatch.setattr("src.api.config.JWT_SECRET_KEY", "short-secret-123")
    
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        validate_production_config()


def test_production_fails_on_missing_encryption_key(monkeypatch):
    """Production mode must refuse to start if IMAGE_ENCRYPTION_KEY is unset or empty."""
    monkeypatch.setattr("src.api.config.IS_PRODUCTION", True)
    monkeypatch.setattr("src.api.config.JWT_SECRET_KEY", "a" * 40)
    monkeypatch.setattr("src.api.config.IMAGE_ENCRYPTION_KEY", None)
    
    with pytest.raises(RuntimeError, match="IMAGE_ENCRYPTION_KEY must be explicitly set"):
        validate_production_config()


def test_production_succeeds_with_valid_secrets(monkeypatch):
    """Production mode starts cleanly when strong JWT secret and valid 256-bit AES key are provided."""
    valid_key = key_to_base64(generate_key())
    monkeypatch.setattr("src.api.config.IS_PRODUCTION", True)
    monkeypatch.setattr("src.api.config.JWT_SECRET_KEY", "super-strong-production-secret-key-at-least-32-chars")
    monkeypatch.setattr("src.api.config.IMAGE_ENCRYPTION_KEY", valid_key)
    
    # Should not raise any exception
    validate_production_config()


# =====================================================================
# 2. Rate Limiting Tests
# =====================================================================
def test_login_rate_limiting(client: TestClient):
    """Multiple rapid failed login attempts must trigger HTTP 429 Too Many Requests."""
    login_rate_limiter.reset()
    old_max = login_rate_limiter.max_requests
    try:
        login_rate_limiter.max_requests = 5
        # Send 5 login requests (allowed limit)
        for _ in range(5):
            resp = client.post("/auth/login", json={"username": "doctor1", "password": "WrongPassword!"})
            assert resp.status_code == 401

        # The 6th request must be rejected with 429 Too Many Requests
        blocked_resp = client.post("/auth/login", json={"username": "doctor1", "password": "WrongPassword!"})
        assert blocked_resp.status_code == 429
        assert "Retry-After" in blocked_resp.headers
        assert "Rate limit exceeded" in blocked_resp.json()["detail"]
    finally:
        login_rate_limiter.max_requests = old_max
        login_rate_limiter.reset()


# =====================================================================
# 3. Security Response Headers Tests
# =====================================================================
def test_security_headers_present_on_responses(client: TestClient):
    """All responses must include OWASP-recommended security headers."""
    resp = client.get("/health")
    assert resp.status_code == 200
    
    headers = resp.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", "")


# =====================================================================
# 4. Decompression Bomb & Image Validation Tests
# =====================================================================
def test_decompression_bomb_rejection():
    """Images exceeding the maximum pixel limit must be rejected as decompression bombs."""
    engine = DenseNetInferenceEngine()
    
    # Create an in-memory image with dimensions that exceed MAX_IMAGE_DIMENSION (4096)
    oversized_img = Image.new("RGB", (5000, 5000), color="white")
    buf = io.BytesIO()
    oversized_img.save(buf, format="PNG")
    oversized_bytes = buf.getvalue()
    
    with pytest.raises(InvalidImagePayloadError, match="(exceed maximum permitted size|decompression bomb)"):
        engine.validate_and_decode_image(oversized_bytes)


# =====================================================================
# 5. Encryption Key Persistence and Recovery Verification
# =====================================================================
def test_encryption_key_persistence_and_recovery(tmp_path):
    """
    Verify that an encrypted scan remains decryptable after storage restart with the same key,
    and fails cleanly when an incorrect key is provided.
    """
    key_a = generate_key()
    key_b = generate_key()
    
    # 1. Initialize storage with key A and store a scan
    storage_dir = tmp_path / "enc_images"
    db_path = tmp_path / "metadata.db"
    storage_a = SecureImageStorage(key=key_a, storage_dir=storage_dir, db_path=db_path)
    
    test_image_bytes = b"TEST_CHEST_XRAY_IMAGE_BYTES_PERSISTENCE_CHECK_32B"
    record = storage_a.store_image(
        image_bytes=test_image_bytes,
        patient_id="ANON-RECOVERY-01",
        uploaded_by="doctor1"
    )
    scan_id = record["scan_id"]
    
    # 2. Simulate application restart with the SAME key
    storage_restarted_same_key = SecureImageStorage(key=key_a, storage_dir=storage_dir, db_path=db_path)
    recovered_bytes, metadata = storage_restarted_same_key.retrieve_image(scan_id)
    assert recovered_bytes == test_image_bytes
    assert metadata["patient_id"] == "ANON-RECOVERY-01"
    
    # 3. Simulate application restart with a DIFFERENT key -> must fail tag verification
    storage_restarted_wrong_key = SecureImageStorage(key=key_b, storage_dir=storage_dir, db_path=db_path)
    with pytest.raises(AuthenticationError, match="(verification failed|ciphertext has been tampered)"):
        storage_restarted_wrong_key.retrieve_image(scan_id)


def test_encrypted_container_tampering_detection(tmp_path):
    """Tampering with an encrypted file on disk must be detected and rejected."""
    key = generate_key()
    storage_dir = tmp_path / "enc_images"
    db_path = tmp_path / "metadata.db"
    storage = SecureImageStorage(key=key, storage_dir=storage_dir, db_path=db_path)
    
    test_image_bytes = b"REAL_MEDICAL_DATA_PAYLOAD_INTEGRITY_CHECK_123"
    record = storage.store_image(image_bytes=test_image_bytes, patient_id="ANON-TAMPER-01")
    scan_id = record["scan_id"]
    
    # Tamper with the encrypted file directly on disk
    enc_file = storage_dir / f"{scan_id}.enc"
    assert enc_file.exists()
    content = bytearray(enc_file.read_bytes())
    # Flip a bit in the ciphertext payload
    content[-10] ^= 0xFF
    enc_file.write_bytes(bytes(content))
    
    # Retrieval must fail tag verification
    with pytest.raises(AuthenticationError):
        storage.retrieve_image(scan_id)


# =====================================================================
# 6. Access Control & Authorization Tests
# =====================================================================
def test_unauthenticated_request_rejected(client: TestClient):
    """Protected scans route must reject unauthenticated requests with 401."""
    resp = client.get("/scans")
    assert resp.status_code == 401


def test_doctor_scan_isolation(client: TestClient):
    """A doctor cannot access or predict scans uploaded by another practitioner."""
    # Authenticate as doctor1
    doctor_token = _get_auth_token(client, "doctor1", "DoctorPassword123!")
    
    # Create sample image
    img = Image.new("RGB", (100, 100), color="gray")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    # Upload scan as doctor1
    upload_resp = client.post(
        "/scans",
        headers={"Authorization": f"Bearer {doctor_token}"},
        files={"file": ("xray.png", buf.getvalue(), "image/png")},
        data={"patient_id": "ANON-DOC1-01"}
    )
    assert upload_resp.status_code == 201
    scan_id = upload_resp.json()["scan_id"]
    
    # Create doctor2 in DB
    from src.api.dependencies import get_db
    from src.api.auth import hash_password
    db = get_db()
    if not db.get_user_by_username("doctor2"):
        db.create_user("doctor2", hash_password("Doctor2Password123!"), "doctor", "Dr. Second Doctor")
    
    doctor2_token = _get_auth_token(client, "doctor2", "Doctor2Password123!")
    
    # doctor2 attempts to access doctor1's scan -> 403 Forbidden
    forbidden_resp = client.get(
        f"/scans/{scan_id}",
        headers={"Authorization": f"Bearer {doctor2_token}"}
    )
    assert forbidden_resp.status_code == 403
    assert "Forbidden" in forbidden_resp.json()["detail"]
    
    # doctor2 attempts to run prediction on doctor1's scan -> 403 Forbidden
    forbidden_pred = client.post(
        f"/scans/{scan_id}/predict",
        headers={"Authorization": f"Bearer {doctor2_token}"}
    )
    assert forbidden_pred.status_code == 403
    
    # Radiologist can access doctor1's scan
    radio_token = _get_auth_token(client, "radiologist1", "RadioPassword123!")
    radio_resp = client.get(
        f"/scans/{scan_id}",
        headers={"Authorization": f"Bearer {radio_token}"}
    )
    assert radio_resp.status_code == 200
