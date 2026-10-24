"""
Secure Key Management Module
ISC Project: Secure Storage and Transmission of Medical Data

Key Management Policies & Guarantees:
1. Generation: Keys are generated using secrets.token_bytes(32) (CSPRNG).
2. Separation of Concerns: The encryption key is NEVER stored inside the
   encrypted image container, alongside encrypted files, or in the SQLite database.
3. Zero-Leakage: Keys are masked in any string representations or exceptions.
   Keys are never written to application logs or console streams.
4. Deterministic Persistence: Keys are NOT generated dynamically on each run;
   the application loads a persistent key from environment variables or a key file.
5. Catastrophic Loss Warning: AES-256-GCM is an information-theoretically secure
   symmetric cipher. If the encryption key is lost, encrypted medical records
   CANNOT be recovered by any means.
6. Production Recommendation: For production deployments, local environment
   variables should be replaced by a dedicated Hardware Security Module (HSM),
   OS secret store (e.g. Windows DPAPI), or Cloud KMS (AWS KMS / Azure Key Vault).
"""

import base64
import os
import secrets
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv

from src.security.exceptions import InvalidKeyError

# Key constants
EXPECTED_KEY_BYTES = 32  # 256 bits
DEFAULT_ENV_VAR = "IMAGE_ENCRYPTION_KEY"


def generate_key() -> bytes:
    """
    Generate a fresh, cryptographically secure 256-bit (32-byte) random symmetric key.
    Uses the system CSPRNG (os.urandom / secrets module).
    """
    return secrets.token_bytes(EXPECTED_KEY_BYTES)


def key_to_base64(key: bytes) -> str:
    """
    Encode a raw 32-byte key into a URL-safe Base64 string for environment variable storage.
    """
    if len(key) != EXPECTED_KEY_BYTES:
        raise InvalidKeyError(
            f"Cannot encode key: expected {EXPECTED_KEY_BYTES} bytes, got {len(key)} bytes."
        )
    return base64.urlsafe_b64encode(key).decode("ascii")


def base64_to_key(encoded_key: str) -> bytes:
    """
    Decode a Base64 string into raw 32-byte key bytes and validate its length.
    """
    if not isinstance(encoded_key, str) or not encoded_key.strip():
        raise InvalidKeyError("Encryption key string is empty or invalid.")

    try:
        raw_key = base64.urlsafe_b64decode(encoded_key.strip().encode("ascii"))
    except Exception as e:
        raise InvalidKeyError("Failed to decode Base64 encryption key.") from None

    if len(raw_key) != EXPECTED_KEY_BYTES:
        raise InvalidKeyError(
            f"Decoded key length mismatch: expected {EXPECTED_KEY_BYTES} bytes (256 bits), got {len(raw_key)} bytes."
        )

    return raw_key


def load_key_from_env(
    var_name: str = DEFAULT_ENV_VAR,
    dotenv_path: Optional[Union[str, Path]] = None
) -> bytes:
    """
    Load and decode a 256-bit encryption key from the environment or a .env file.

    Parameters:
        var_name: Name of the environment variable (default: IMAGE_ENCRYPTION_KEY).
        dotenv_path: Optional explicit path to a .env file.

    Returns:
        32-byte raw key.

    Raises:
        InvalidKeyError: If the variable is not set, empty, or fails length validation.
    """
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)
    else:
        load_dotenv(override=False)

    encoded = os.getenv(var_name)
    if not encoded:
        raise InvalidKeyError(
            f"Missing required encryption key in environment variable '{var_name}'. "
            "Please configure your key in your .env file or environment."
        )

    return base64_to_key(encoded)


def load_key_from_file(file_path: Union[str, Path]) -> bytes:
    """
    Load a raw binary (32 bytes) or Base64 string key from a restricted local file.

    Parameters:
        file_path: Path to the key file.

    Returns:
        32-byte raw key.
    """
    p = Path(file_path)
    if not p.exists():
        raise InvalidKeyError(f"Encryption key file not found: {p.name}")

    content = p.read_bytes()
    if len(content) == EXPECTED_KEY_BYTES:
        return content  # Direct raw binary key

    # Attempt to parse as text/base64
    try:
        text = content.decode("ascii").strip()
        return base64_to_key(text)
    except Exception:
        raise InvalidKeyError("Key file does not contain a valid 32-byte binary or Base64 key.") from None


def save_key_to_file(key: bytes, file_path: Union[str, Path], as_base64: bool = True) -> None:
    """
    Save an encryption key to a local file with safe permissions.
    Intended for initialization/setup scripts only.
    """
    if len(key) != EXPECTED_KEY_BYTES:
        raise InvalidKeyError(f"Cannot save key: expected {EXPECTED_KEY_BYTES} bytes, got {len(key)} bytes.")

    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if as_base64:
        p.write_text(key_to_base64(key), encoding="ascii")
    else:
        p.write_bytes(key)

    # Restrict permissions on Unix if available
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass  # On Windows, NTFS ACLs apply
