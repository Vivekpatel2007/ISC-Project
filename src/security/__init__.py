"""
Security & Cryptography Package
ISC Project: Secure Storage and Transmission of Medical Data
"""

from src.security.database import MetadataDB
from src.security.encryption import (
    CURRENT_VERSION,
    MAGIC_HEADER,
    decrypt_bytes,
    encrypt_bytes,
    validate_key,
)
from src.security.exceptions import (
    AuthenticationError,
    DecryptionError,
    EncryptionError,
    IntegrityVerificationError,
    InvalidIdentifierError,
    InvalidKeyError,
    MaxFileSizeExceededError,
    ScanNotFoundError,
    SecurityError,
    StorageError,
)
from src.security.integrity import (
    compute_hmac_sha256,
    compute_sha256,
    verify_hmac_sha256,
    verify_sha256,
)
from src.security.key_manager import (
    base64_to_key,
    generate_key,
    key_to_base64,
    load_key_from_env,
    load_key_from_file,
    save_key_to_file,
)
from src.security.secure_storage import SecureImageStorage

__all__ = [
    # Encryption
    "encrypt_bytes",
    "decrypt_bytes",
    "validate_key",
    "MAGIC_HEADER",
    "CURRENT_VERSION",
    # Key Management
    "generate_key",
    "key_to_base64",
    "base64_to_key",
    "load_key_from_env",
    "load_key_from_file",
    "save_key_to_file",
    # Integrity
    "compute_sha256",
    "verify_sha256",
    "compute_hmac_sha256",
    "verify_hmac_sha256",
    # Storage & DB
    "SecureImageStorage",
    "MetadataDB",
    # Exceptions
    "SecurityError",
    "EncryptionError",
    "DecryptionError",
    "AuthenticationError",
    "InvalidKeyError",
    "IntegrityVerificationError",
    "ScanNotFoundError",
    "InvalidIdentifierError",
    "StorageError",
    "MaxFileSizeExceededError",
]
