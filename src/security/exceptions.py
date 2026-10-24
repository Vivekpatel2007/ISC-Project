"""
Security & Cryptography Exception Hierarchy
ISC Project: Secure Storage and Transmission of Medical Data

All security-related exceptions inherit from SecurityError and sanitize
their representations to ensure secret keys, raw ciphertext, and patient
identifiers are never leaked into logs, tracebacks, or user-facing errors.
"""


class SecurityError(Exception):
    """Base class for all security and cryptography exceptions."""
    pass


class EncryptionError(SecurityError):
    """Raised when an encryption operation fails."""
    pass


class DecryptionError(SecurityError):
    """Raised when decryption fails due to format, key, or truncation errors."""
    pass


class AuthenticationError(DecryptionError):
    """
    Raised when AES-GCM or HMAC tag verification fails.
    Indicates potential ciphertext tampering, transmission corruption, or wrong key.
    """
    pass


class InvalidKeyError(SecurityError):
    """Raised when an encryption key is missing, malformed, or of invalid length."""
    pass


class IntegrityVerificationError(SecurityError):
    """Raised when recovered data fails cryptographic hash verification."""
    pass


class ScanNotFoundError(SecurityError):
    """Raised when a requested scan ID does not exist in the secure registry."""
    pass


class InvalidIdentifierError(SecurityError):
    """Raised when a scan or patient identifier fails format validation or attempts path traversal."""
    pass


class StorageError(SecurityError):
    """Raised when disk or database storage operations fail."""
    pass


class MaxFileSizeExceededError(StorageError):
    """Raised when an uploaded file exceeds the configured maximum upload size."""
    pass
