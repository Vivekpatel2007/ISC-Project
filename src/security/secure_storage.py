"""
Secure Medical Image Storage Engine
ISC Project: Secure Storage and Transmission of Medical Data

Architecture & Flow:
1. Intake: In-memory image bytes are received with a pseudonymous patient ID (e.g. "ANON-00412").
2. Pre-flight Validation: Enforces non-empty input and configurable size boundaries (default: 20MB).
3. Identity & Provenance: Generates a cryptographically random UUID4 scan_id. Computes SHA-256 digest of plaintext bytes.
4. Cryptographic Wrapping: Encrypts bytes using AES-256-GCM (PX01 specification, 96-bit fresh nonce).
5. Atomic Persistence: Writes ciphertext to a temporary file, then performs an atomic rename/replace to prevent truncated files.
6. Consistent Metadata: Records metadata in SQLite transaction. If database insertion fails, the written encrypted file is immediately purged.
7. Retrieval & Authentication: On retrieval by scan_id, verifies file location within storage boundaries, reads ciphertext, decrypts/authenticates in-memory via GCM tag, and validates raw byte SHA-256 against registry.
8. Zero Plaintext at Rest: Decrypted bytes reside strictly in memory and are returned directly to the caller.
"""

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from src.security.database import MetadataDB, validate_patient_id, validate_scan_id
from src.security.encryption import CURRENT_VERSION, decrypt_bytes, encrypt_bytes, validate_key
from src.security.exceptions import (
    AuthenticationError,
    DecryptionError,
    IntegrityVerificationError,
    MaxFileSizeExceededError,
    ScanNotFoundError,
    StorageError,
)
from src.security.integrity import compute_sha256, verify_sha256

DEFAULT_STORAGE_DIR = Path("secure_data/encrypted_images")
DEFAULT_DB_PATH = Path("secure_data/metadata.db")
DEFAULT_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class SecureImageStorage:
    def __init__(
        self,
        key: bytes,
        storage_dir: Union[str, Path] = DEFAULT_STORAGE_DIR,
        db_path: Union[str, Path] = DEFAULT_DB_PATH,
        max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE
    ):
        validate_key(key)
        self.key = key
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.db = MetadataDB(db_path)
        self.max_file_size_bytes = max_file_size_bytes

    def _get_encrypted_file_path(self, scan_id: str) -> Path:
        """
        Derive the filesystem path for an encrypted scan and verify it cannot escape storage_dir.
        """
        safe_id = validate_scan_id(scan_id)
        filename = f"{safe_id}.enc"
        target_path = (self.storage_dir / filename).resolve()

        # Strict directory containment check to prevent path traversal
        try:
            target_path.relative_to(self.storage_dir)
        except ValueError:
            raise StorageError("Path traversal attempt detected.") from None

        return target_path

    def store_image(
        self,
        image_bytes: bytes,
        patient_id: str,
        associated_data: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Encrypt and securely store a medical chest X-ray image.

        Parameters:
            image_bytes: The raw image bytes (e.g. JPEG/PNG/DICOM).
            patient_id: Pseudonymous identifier (e.g. 'ANON-10492').
            associated_data: Optional authenticated metadata for AEAD.

        Returns:
            Dictionary containing stored scan metadata (scan_id, patient_id, sha256, etc.).

        Raises:
            MaxFileSizeExceededError: If image size exceeds max_file_size_bytes.
            StorageError: If storage or encryption fails.
        """
        if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) == 0:
            raise StorageError("Image payload is empty or invalid.")

        if len(image_bytes) > self.max_file_size_bytes:
            raise MaxFileSizeExceededError(
                f"Image size ({len(image_bytes)} bytes) exceeds maximum allowed limit ({self.max_file_size_bytes} bytes)."
            )

        safe_patient_id = validate_patient_id(patient_id)
        scan_id = str(uuid.uuid4())
        original_sha256 = compute_sha256(image_bytes)

        # 1. Encrypt image in memory using AES-256-GCM
        encrypted_container = encrypt_bytes(
            image_bytes,
            self.key,
            associated_data=associated_data
        )

        final_path = self._get_encrypted_file_path(scan_id)
        temp_path = self.storage_dir / f"{scan_id}.tmp"

        # 2. Atomic file write
        try:
            temp_path.write_bytes(encrypted_container)
            os.replace(temp_path, final_path)
        except Exception as e:
            if temp_path.exists():
                try: temp_path.unlink()
                except Exception: pass
            raise StorageError(f"Failed to write encrypted image to disk: {type(e).__name__}") from None

        # 3. Database transaction
        try:
            record = self.db.insert_scan(
                scan_id=scan_id,
                patient_id=safe_patient_id,
                encrypted_filename=final_path.name,
                original_sha256=original_sha256,
                file_size_bytes=len(encrypted_container),
                format_version=CURRENT_VERSION
            )
            return record
        except Exception as e:
            # Atomic rollback: If DB insertion fails, remove encrypted file to prevent orphans
            if final_path.exists():
                try: final_path.unlink()
                except Exception: pass
            raise StorageError(f"Failed to record scan in database: {e}") from None

    def retrieve_image(
        self,
        scan_id: str,
        associated_data: Optional[bytes] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """
        Retrieve and decrypt a medical image in memory with full cryptographic verification.

        Parameters:
            scan_id: Unique scan identifier.
            associated_data: Optional authenticated metadata expected by AEAD.

        Returns:
            Tuple of (decrypted_image_bytes, metadata_dict).

        Raises:
            ScanNotFoundError: If the scan ID is not in the database.
            StorageError: If the encrypted file is missing from disk.
            AuthenticationError: If ciphertext has been tampered with or tag verification fails.
            IntegrityVerificationError: If recovered bytes do not match the expected SHA-256 digest.
        """
        # 1. Query metadata registry
        record = self.db.get_scan(scan_id)

        # 2. Locate encrypted file
        file_path = self._get_encrypted_file_path(scan_id)
        if not file_path.exists():
            raise StorageError(f"Encrypted image file missing on disk for scan '{scan_id}'.")

        # 3. Read encrypted bytes
        try:
            encrypted_container = file_path.read_bytes()
        except Exception as e:
            raise StorageError(f"Failed to read encrypted file: {type(e).__name__}") from None

        # 4. Decrypt and authenticate using AES-256-GCM
        decrypted_bytes = decrypt_bytes(
            encrypted_container,
            self.key,
            associated_data=associated_data
        )

        # 5. Verify integrity against registered SHA-256 hash
        expected_sha256 = record["original_sha256"]
        if not verify_sha256(decrypted_bytes, expected_sha256):
            raise IntegrityVerificationError(
                f"Integrity check failed for scan '{scan_id}': recovered bytes digest does not match registry."
            )

        return decrypted_bytes, record

    def verify_scan_integrity(
        self,
        scan_id: str,
        associated_data: Optional[bytes] = None
    ) -> Dict[str, Any]:
        """
        Perform complete cryptographic verification of an encrypted scan without writing any plaintext to disk.
        """
        try:
            decrypted_bytes, record = self.retrieve_image(scan_id, associated_data=associated_data)
            return {
                "scan_id": scan_id,
                "status": "VALID",
                "authentication": "VERIFIED (AES-256-GCM)",
                "integrity": "VERIFIED (SHA-256 matches)",
                "original_sha256": record["original_sha256"],
                "file_size_bytes": record["file_size_bytes"],
                "created_at": record["created_at"]
            }
        except (AuthenticationError, DecryptionError, IntegrityVerificationError, StorageError) as e:
            return {
                "scan_id": scan_id,
                "status": "CORRUPTED_OR_TAMPERED",
                "error": str(e)
            }
        except ScanNotFoundError:
            return {
                "scan_id": scan_id,
                "status": "NOT_FOUND",
                "error": "Scan record does not exist."
            }

    def delete_scan(self, scan_id: str) -> None:
        """
        Delete both the encrypted file and database record for a scan.
        """
        file_path = self._get_encrypted_file_path(scan_id)
        if file_path.exists():
            try: file_path.unlink()
            except Exception: pass
        self.db.delete_scan(scan_id)
