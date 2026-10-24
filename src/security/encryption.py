"""
AES-256-GCM Authenticated Encryption & Decryption Module
ISC Project: Secure Storage and Transmission of Medical Data

Binary Container Format (PX01 Specification):
+---------------+---------------+-------------------+-----------------------------------+
| Field         | Length (bytes)| Format            | Description                       |
+---------------+---------------+-------------------+-----------------------------------+
| MAGIC_HEADER  | 4             | ASCII b"PX01"     | Format identifier                 |
| VERSION       | 1             | uint8 (0x01)      | Container format version          |
| NONCE         | 12            | Binary (96-bit)   | Cryptographically random IV/nonce |
| CIPHERTEXT    | N             | Binary            | AES-256-GCM encrypted payload     |
| AUTH_TAG      | 16            | Binary (128-bit)  | AEAD authentication tag           |
+---------------+---------------+-------------------+-----------------------------------+
Minimum valid container size = 4 + 1 + 12 + 0 + 16 = 33 bytes.

Security Guarantees:
- Confidentiality: AES with 256-bit key length.
- Integrity & Authenticity: Galois/Counter Mode (GCM) produces a 128-bit MAC tag.
- Nonce Uniqueness: Fresh 96-bit nonce generated via os.urandom(12) for every call.
  (Nonce reuse under GCM destroys catastrophic authenticity guarantees).
- Tag Verification: cryptography.hazmat.primitives.ciphers.aead.AESGCM verifies
  the 16-byte tag before decrypting any plaintext.
"""

import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.security.exceptions import (
    AuthenticationError,
    DecryptionError,
    EncryptionError,
    InvalidKeyError,
)

# Binary format constants
MAGIC_HEADER = b"PX01"
CURRENT_VERSION = 0x01
KEY_SIZE_BYTES = 32     # 256 bits
NONCE_SIZE_BYTES = 12   # 96 bits (NIST SP 800-38D recommended for GCM)
TAG_SIZE_BYTES = 16     # 128 bits
HEADER_SIZE_BYTES = len(MAGIC_HEADER) + 1 + NONCE_SIZE_BYTES  # 4 + 1 + 12 = 17 bytes
MIN_CONTAINER_SIZE = HEADER_SIZE_BYTES + TAG_SIZE_BYTES       # 33 bytes


def validate_key(key: bytes) -> None:
    """Validate that the encryption key is exactly 256 bits (32 bytes)."""
    if not isinstance(key, (bytes, bytearray)):
        raise InvalidKeyError("Encryption key must be raw bytes.")
    if len(key) != KEY_SIZE_BYTES:
        raise InvalidKeyError(
            f"Invalid key length: expected {KEY_SIZE_BYTES} bytes (256 bits), got {len(key)} bytes."
        )


def encrypt_bytes(
    plaintext: bytes,
    key: bytes,
    associated_data: Optional[bytes] = None
) -> bytes:
    """
    Encrypt arbitrary bytes (such as medical images) using AES-256-GCM.

    Parameters:
        plaintext: The raw unencrypted data.
        key: A 32-byte (256-bit) cryptographically secure key.
        associated_data: Optional unencrypted metadata bound to the authentication tag (AEAD).

    Returns:
        Packaged binary container bytes conforming to the PX01 specification.

    Raises:
        InvalidKeyError: If key length or type is invalid.
        EncryptionError: If the encryption operation fails.
    """
    validate_key(key)

    if not isinstance(plaintext, (bytes, bytearray)):
        raise EncryptionError("Plaintext data must be bytes.")

    try:
        # Generate fresh, cryptographically secure 96-bit nonce
        nonce = os.urandom(NONCE_SIZE_BYTES)
        aesgcm = AESGCM(key)

        # AESGCM.encrypt returns ciphertext with 16-byte tag appended
        ciphertext_with_tag = aesgcm.encrypt(nonce, bytes(plaintext), associated_data)

        # Assemble container: MAGIC (4B) + VERSION (1B) + NONCE (12B) + CIPHERTEXT+TAG
        version_byte = bytes([CURRENT_VERSION])
        container = MAGIC_HEADER + version_byte + nonce + ciphertext_with_tag
        return container

    except InvalidKeyError:
        raise
    except Exception as e:
        raise EncryptionError(f"Encryption failed: {type(e).__name__}") from None


def decrypt_bytes(
    container: bytes,
    key: bytes,
    associated_data: Optional[bytes] = None
) -> bytes:
    """
    Decrypt and authenticate a PX01 binary container using AES-256-GCM.

    Parameters:
        container: The packaged binary bytes.
        key: The 32-byte (256-bit) key used during encryption.
        associated_data: Optional authenticated data that must match what was passed during encryption.

    Returns:
        Decrypted plaintext bytes.

    Raises:
        InvalidKeyError: If key length or type is invalid.
        DecryptionError: If the container is truncated, malformed, or has an unknown version.
        AuthenticationError: If tag verification fails (indicating tampering or wrong key).
    """
    validate_key(key)

    if not isinstance(container, (bytes, bytearray)):
        raise DecryptionError("Encrypted container must be bytes.")

    if len(container) < MIN_CONTAINER_SIZE:
        raise DecryptionError(
            f"Encrypted container is truncated ({len(container)} bytes; minimum expected is {MIN_CONTAINER_SIZE} bytes)."
        )

    # 1. Verify Magic Header
    header = container[:len(MAGIC_HEADER)]
    if header != MAGIC_HEADER:
        raise DecryptionError("Invalid container format: magic header mismatch.")

    # 2. Check Version
    version = container[len(MAGIC_HEADER)]
    if version != CURRENT_VERSION:
        raise DecryptionError(f"Unsupported container version: {version}. Expected: {CURRENT_VERSION}.")

    # 3. Extract Nonce and Payload
    nonce_start = len(MAGIC_HEADER) + 1
    nonce_end = nonce_start + NONCE_SIZE_BYTES
    nonce = container[nonce_start:nonce_end]
    ciphertext_with_tag = container[nonce_end:]

    # 4. Decrypt and Authenticate
    try:
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data)
        return plaintext
    except InvalidTag:
        # Crucial security requirement: Never leak key or content in authentication failure
        raise AuthenticationError(
            "Authentication verification failed: ciphertext has been tampered with or key is incorrect."
        ) from None
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {type(e).__name__}") from None
