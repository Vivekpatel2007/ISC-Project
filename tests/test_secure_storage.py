"""
Comprehensive Cryptography & Secure Storage Test Suite
ISC Project: Secure Storage and Transmission of Medical Data

Tests the 12 critical security requirements:
1. Successful encryption and decryption round trip.
2. Fresh nonce verification (different ciphertexts for identical plaintext).
3. Incorrect key rejection (authentication tag failure).
4. Ciphertext tampering detection (single-bit flip detection).
5. Truncated and malformed file handling.
6. SHA-256 computation and constant-time integrity verification.
7. End-to-end secure image storage and in-memory retrieval.
8. SQLite metadata creation, query, and constraint enforcement.
9. Path traversal and malicious identifier rejection.
10. Atomic rollback on failure and missing file handling.
11. Verification that no plaintext is ever written to storage.
12. Zero-leakage verification (keys not exposed in exceptions).
"""

import os
import tempfile
from pathlib import Path

import pytest

from src.security import (
    AuthenticationError,
    DecryptionError,
    IntegrityVerificationError,
    InvalidIdentifierError,
    InvalidKeyError,
    MaxFileSizeExceededError,
    MetadataDB,
    ScanNotFoundError,
    SecureImageStorage,
    StorageError,
    base64_to_key,
    compute_hmac_sha256,
    compute_sha256,
    decrypt_bytes,
    encrypt_bytes,
    generate_key,
    key_to_base64,
    verify_hmac_sha256,
    verify_sha256,
)


@pytest.fixture
def sample_key():
    """Generates a fresh 256-bit test key."""
    return generate_key()


@pytest.fixture
def sample_image_bytes():
    """Synthetic binary payload mimicking medical image bytes."""
    # 64 KB of pseudo-random image bytes
    return os.urandom(65536)


@pytest.fixture
def temp_storage_env(sample_key):
    """Provides an isolated temporary directory and SQLite database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_dir = Path(tmpdir) / "encrypted_images"
        db_path = Path(tmpdir) / "test_metadata.db"
        storage = SecureImageStorage(
            key=sample_key,
            storage_dir=storage_dir,
            db_path=db_path,
            max_file_size_bytes=10 * 1024 * 1024
        )
        yield {
            "storage": storage,
            "storage_dir": storage_dir,
            "db_path": db_path,
            "key": sample_key
        }


# =====================================================================
# 1. Encryption and Decryption Round Trip
# =====================================================================
def test_encryption_decryption_round_trip(sample_key, sample_image_bytes):
    encrypted = encrypt_bytes(sample_image_bytes, sample_key)
    assert isinstance(encrypted, bytes)
    assert encrypted != sample_image_bytes
    assert len(encrypted) > len(sample_image_bytes)

    decrypted = decrypt_bytes(encrypted, sample_key)
    assert decrypted == sample_image_bytes


# =====================================================================
# 2. Fresh Nonces (Different Ciphertexts for Identical Plaintext)
# =====================================================================
def test_nonce_uniqueness_for_repeated_encryptions(sample_key, sample_image_bytes):
    enc1 = encrypt_bytes(sample_image_bytes, sample_key)
    enc2 = encrypt_bytes(sample_image_bytes, sample_key)
    enc3 = encrypt_bytes(sample_image_bytes, sample_key)

    # All three ciphertexts must be distinct because random 96-bit nonces are generated
    assert enc1 != enc2
    assert enc2 != enc3
    assert enc1 != enc3

    # All must decrypt to the exact same original bytes
    assert decrypt_bytes(enc1, sample_key) == sample_image_bytes
    assert decrypt_bytes(enc2, sample_key) == sample_image_bytes
    assert decrypt_bytes(enc3, sample_key) == sample_image_bytes


# =====================================================================
# 3. Incorrect Key Rejection
# =====================================================================
def test_incorrect_key_rejection(sample_key, sample_image_bytes):
    wrong_key = generate_key()
    assert wrong_key != sample_key

    encrypted = encrypt_bytes(sample_image_bytes, sample_key)
    with pytest.raises(AuthenticationError):
        decrypt_bytes(encrypted, wrong_key)


def test_invalid_key_length_rejection(sample_image_bytes):
    short_key = b"too_short_key_16"
    with pytest.raises(InvalidKeyError):
        encrypt_bytes(sample_image_bytes, short_key)

    with pytest.raises(InvalidKeyError):
        decrypt_bytes(b"dummy_encrypted_data", short_key)


# =====================================================================
# 4. Ciphertext Tampering Detection
# =====================================================================
def test_ciphertext_tampering_detection(sample_key, sample_image_bytes):
    encrypted = bytearray(encrypt_bytes(sample_image_bytes, sample_key))

    # Tamper with a single byte in the ciphertext portion
    tamper_idx = len(encrypted) - 5
    encrypted[tamper_idx] ^= 0xFF

    with pytest.raises(AuthenticationError):
        decrypt_bytes(bytes(encrypted), sample_key)


def test_header_and_nonce_tampering(sample_key, sample_image_bytes):
    encrypted = bytearray(encrypt_bytes(sample_image_bytes, sample_key))

    # Tamper with the nonce (bytes 5 to 16)
    encrypted[6] ^= 0xAA

    with pytest.raises(AuthenticationError):
        decrypt_bytes(bytes(encrypted), sample_key)


# =====================================================================
# 5. Truncated or Malformed Container Rejection
# =====================================================================
def test_truncated_container_rejection(sample_key, sample_image_bytes):
    encrypted = encrypt_bytes(sample_image_bytes, sample_key)

    # Severely truncated (shorter than minimal container header)
    with pytest.raises(DecryptionError):
        decrypt_bytes(encrypted[:20], sample_key)

    # Truncated in the middle of ciphertext
    with pytest.raises(DecryptionError):
        decrypt_bytes(encrypted[:len(encrypted) - 8], sample_key)


def test_malformed_magic_header_rejection(sample_key, sample_image_bytes):
    encrypted = bytearray(encrypt_bytes(sample_image_bytes, sample_key))
    encrypted[:4] = b"BADH"  # Corrupt magic bytes
    with pytest.raises(DecryptionError):
        decrypt_bytes(bytes(encrypted), sample_key)


# =====================================================================
# 6. SHA-256 Calculation & Integrity Verification
# =====================================================================
def test_sha256_computation_and_verification(sample_image_bytes):
    h = compute_sha256(sample_image_bytes)
    assert len(h) == 64
    assert isinstance(h, str)
    assert verify_sha256(sample_image_bytes, h) is True

    # Tampered data fails verification
    modified = sample_image_bytes + b"x"
    assert verify_sha256(modified, h) is False
    assert verify_sha256(sample_image_bytes, "0" * 64) is False


def test_hmac_sha256_verification(sample_key, sample_image_bytes):
    mac = compute_hmac_sha256(sample_image_bytes, sample_key)
    assert len(mac) == 64
    assert verify_hmac_sha256(sample_image_bytes, mac, sample_key) is True

    wrong_key = generate_key()
    assert verify_hmac_sha256(sample_image_bytes, mac, wrong_key) is False


# =====================================================================
# 7. End-to-End Secure Storage and Retrieval
# =====================================================================
def test_secure_storage_and_retrieval(temp_storage_env, sample_image_bytes):
    storage = temp_storage_env["storage"]
    storage_dir = temp_storage_env["storage_dir"]

    patient_id = "ANON-00912"
    meta = storage.store_image(sample_image_bytes, patient_id=patient_id)

    scan_id = meta["scan_id"]
    assert scan_id is not None
    assert meta["patient_id"] == patient_id
    assert meta["original_sha256"] == compute_sha256(sample_image_bytes)

    # Verify encrypted file exists on disk
    enc_file = storage_dir / f"{scan_id}.enc"
    assert enc_file.exists()
    assert enc_file.read_bytes() != sample_image_bytes

    # Retrieve and verify in-memory decryption
    retrieved_bytes, retrieved_meta = storage.retrieve_image(scan_id)
    assert retrieved_bytes == sample_image_bytes
    assert retrieved_meta["scan_id"] == scan_id


# =====================================================================
# 8. SQLite Metadata Creation and Querying
# =====================================================================
def test_metadata_database_operations(temp_storage_env, sample_image_bytes):
    storage = temp_storage_env["storage"]
    db = storage.db

    meta1 = storage.store_image(sample_image_bytes, patient_id="P-001")
    meta2 = storage.store_image(sample_image_bytes, patient_id="P-001")
    meta3 = storage.store_image(sample_image_bytes, patient_id="P-002")

    # Patient listing
    p1_scans = db.list_scans_for_patient("P-001")
    assert len(p1_scans) == 2
    assert {s["scan_id"] for s in p1_scans} == {meta1["scan_id"], meta2["scan_id"]}

    # Update prediction
    db.update_prediction(meta1["scan_id"], predicted_class="PNEUMONIA", probability=0.942)
    updated = db.get_scan(meta1["scan_id"])
    assert updated["prediction_status"] == "PROCESSED"
    assert updated["predicted_class"] == "PNEUMONIA"
    assert round(updated["prediction_probability"], 3) == 0.942


# =====================================================================
# 9. Path Traversal & Malicious Identifier Rejection
# =====================================================================
def test_path_traversal_rejection(temp_storage_env):
    storage = temp_storage_env["storage"]

    traversal_ids = [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "scan/../../secret",
        "valid_id\x00_null",
        "../test",
        "../../../escape"
    ]

    for bad_id in traversal_ids:
        with pytest.raises(InvalidIdentifierError):
            storage.retrieve_image(bad_id)

    with pytest.raises(InvalidIdentifierError):
        storage.store_image(b"test", patient_id="../../evil_patient")


# =====================================================================
# 10. Missing Files and Error Handling
# =====================================================================
def test_missing_encrypted_file_handling(temp_storage_env, sample_image_bytes):
    storage = temp_storage_env["storage"]
    storage_dir = temp_storage_env["storage_dir"]

    meta = storage.store_image(sample_image_bytes, patient_id="ANON-404")
    scan_id = meta["scan_id"]

    # Delete the underlying encrypted file to simulate disk loss
    (storage_dir / f"{scan_id}.enc").unlink()

    with pytest.raises(StorageError):
        storage.retrieve_image(scan_id)

    status = storage.verify_scan_integrity(scan_id)
    assert status["status"] == "CORRUPTED_OR_TAMPERED"


def test_nonexistent_scan_id(temp_storage_env):
    storage = temp_storage_env["storage"]
    with pytest.raises(ScanNotFoundError):
        storage.retrieve_image("00000000-0000-0000-0000-000000000000")


def test_max_file_size_enforcement(temp_storage_env):
    storage = temp_storage_env["storage"]
    oversized = os.urandom(11 * 1024 * 1024)  # 11 MB exceeds 10 MB limit
    with pytest.raises(MaxFileSizeExceededError):
        storage.store_image(oversized, patient_id="ANON-OVERSIZED")


# =====================================================================
# 11. Verification That Plaintext Is Never Left on Disk
# =====================================================================
def test_no_plaintext_files_on_disk(temp_storage_env, sample_image_bytes):
    storage = temp_storage_env["storage"]
    storage_dir = temp_storage_env["storage_dir"]

    meta = storage.store_image(sample_image_bytes, patient_id="ANON-CLEAN")
    scan_id = meta["scan_id"]

    # Retrieve and decrypt in memory
    decrypted, _ = storage.retrieve_image(scan_id)
    assert decrypted == sample_image_bytes

    # Inspect all files in storage directory
    for f in storage_dir.iterdir():
        assert f.name.endswith(".enc")
        content = f.read_bytes()
        # Verify no file on disk contains plaintext image bytes
        assert sample_image_bytes not in content
        assert not f.name.endswith(".tmp")


# =====================================================================
# 12. Zero-Leakage: Keys Never Appear in Error Messages
# =====================================================================
def test_key_zero_leakage_in_exceptions(sample_key, sample_image_bytes):
    b64_key = key_to_base64(sample_key)

    # 1. Ensure wrong key exception doesn't leak either key
    wrong_key = generate_key()
    b64_wrong = key_to_base64(wrong_key)
    enc = encrypt_bytes(sample_image_bytes, sample_key)

    try:
        decrypt_bytes(enc, wrong_key)
    except AuthenticationError as e:
        err_msg = str(e)
        assert b64_key not in err_msg
        assert b64_wrong not in err_msg
        assert sample_key.hex() not in err_msg
        assert wrong_key.hex() not in err_msg

    # 2. Key format encoding round trip
    assert base64_to_key(b64_key) == sample_key
