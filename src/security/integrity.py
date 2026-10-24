"""
Cryptographic Integrity & Hashing Module
ISC Project: Secure Storage and Transmission of Medical Data

Security Principles:
1. Unkeyed Hash (SHA-256):
   - Computes a deterministic digest of raw medical image bytes before encryption.
   - Purpose: Verifies end-to-end data integrity across storage and retrieval cycles
     (e.g., detecting bit rot or software corruption during decompression/deserialization).
   - CRITICAL SECURITY NOTE: An unkeyed hash provides integrity against accidental
     corruption, NOT adversarial tampering. An attacker with write access to both
     the file and database could replace both.

2. Authenticated Encryption (AES-GCM):
   - Cryptographic defense against adversarial tampering is provided by the
     AES-256-GCM authentication tag. Any tampering with ciphertext or headers
     causes immediate authentication failure during decryption.

3. Keyed Hash (HMAC-SHA-256):
   - When message authentication without encryption is needed (e.g., verifying
     transmission provenance across distributed hospital nodes), HMAC-SHA-256
     uses a secret key and constant-time comparison (hmac.compare_digest) to prevent
     timing side-channel attacks.
"""

import hashlib
import hmac
from typing import Union

from src.security.exceptions import IntegrityVerificationError, InvalidKeyError


def compute_sha256(data: bytes) -> str:
    """
    Compute the SHA-256 hex digest of raw bytes.

    Parameters:
        data: Raw image or file bytes.

    Returns:
        64-character lowercase hexadecimal digest string.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("Data must be bytes to compute SHA-256 digest.")
    return hashlib.sha256(data).hexdigest()


def verify_sha256(data: bytes, expected_hash: str) -> bool:
    """
    Verify that the SHA-256 digest of data matches expected_hash in constant time.

    Parameters:
        data: The bytes to verify.
        expected_hash: The 64-character hex digest to verify against.

    Returns:
        True if the hashes match, False otherwise.
    """
    if not isinstance(expected_hash, str) or len(expected_hash.strip()) != 64:
        return False
    computed = compute_sha256(data)
    # Use hmac.compare_digest for constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed.lower(), expected_hash.strip().lower())


def compute_hmac_sha256(data: bytes, key: bytes) -> str:
    """
    Compute a keyed HMAC-SHA-256 digest for data using a dedicated HMAC key.

    Parameters:
        data: Payload bytes to authenticate.
        key: Secret authentication key (recommended minimum 32 bytes).

    Returns:
        64-character hexadecimal HMAC string.
    """
    if not isinstance(key, (bytes, bytearray)) or len(key) == 0:
        raise InvalidKeyError("HMAC key must be non-empty bytes.")
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("Data must be bytes to compute HMAC.")
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def verify_hmac_sha256(data: bytes, expected_hmac: str, key: bytes) -> bool:
    """
    Verify an HMAC-SHA-256 digest in constant time.
    """
    if not isinstance(expected_hmac, str) or len(expected_hmac.strip()) != 64:
        return False
    computed = compute_hmac_sha256(data, key)
    return hmac.compare_digest(computed.lower(), expected_hmac.strip().lower())
