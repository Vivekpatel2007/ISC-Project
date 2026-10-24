"""
API Configuration & Settings Module
ISC Project: Secure Storage and Transmission of Medical Data

Security & Configuration Rules:
1. Short-Lived Access Tokens: Access tokens expire after 30 minutes (configurable).
2. Key Segregation: JWT signing keys are completely distinct from AES-GCM data encryption keys.
3. Minimal Default Exposure: Default configs are suitable for local development;
   production environments must provide persistent environment variables.
"""

import os
from pathlib import Path
from typing import List, Tuple
from dotenv import load_dotenv

load_dotenv(override=False)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Environment Mode
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
IS_PRODUCTION = APP_ENV in ("production", "prod")
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "false").lower() in ("true", "1", "yes")
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "true" if not IS_PRODUCTION else "false").lower() in ("true", "1", "yes")
SEED_DEMO_USERS = os.getenv("SEED_DEMO_USERS", "true" if not IS_PRODUCTION else "false").lower() in ("true", "1", "yes")

# Security & Tokens
INSECURE_DEV_JWT_SECRET = "insecure-dev-jwt-secret-key-replace-in-production-32bytes"
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", INSECURE_DEV_JWT_SECRET)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Cryptography & Storage Paths
IMAGE_ENCRYPTION_KEY = os.getenv("IMAGE_ENCRYPTION_KEY", None)
SECURE_STORAGE_DIR = Path(os.getenv("SECURE_STORAGE_DIR", str(PROJECT_ROOT / "secure_data" / "encrypted_images")))
METADATA_DB_PATH = Path(os.getenv("METADATA_DB_PATH", str(PROJECT_ROOT / "secure_data" / "metadata.db")))
MODEL_CHECKPOINT_PATH = Path(os.getenv("MODEL_CHECKPOINT_PATH", str(PROJECT_ROOT / "models" / "densenet121_pneumonia_best.pth")))

# Upload Limits & Format Validation
MAX_IMAGE_SIZE_BYTES = int(os.getenv("MAX_IMAGE_SIZE_BYTES", str(20 * 1024 * 1024)))  # 20 MB
ALLOWED_IMAGE_FORMATS: Tuple[str, ...] = ("JPEG", "PNG")
ALLOWED_MIME_TYPES: Tuple[str, ...] = ("image/jpeg", "image/png", "image/jpg")

# Minimum image dimensions to prevent tiny malicious or empty files
MIN_IMAGE_DIMENSION = 32
MAX_IMAGE_DIMENSION = 4096

# CORS Origins (configurable for production frontends)
CORS_ORIGINS: List[str] = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
    if origin.strip()
]


def validate_production_config() -> None:
    """
    Validate that critical secrets and storage configurations meet production security requirements.
    Fails fast with RuntimeError if any insecure defaults or missing keys are detected in production mode.
    """
    if not IS_PRODUCTION:
        return

    # 1. Enforce strong JWT secret
    if not JWT_SECRET_KEY or JWT_SECRET_KEY == INSECURE_DEV_JWT_SECRET:
        raise RuntimeError(
            "FATAL SECURITY CONFIGURATION: In production mode (APP_ENV=production), "
            "a strong, cryptographically random JWT_SECRET_KEY (min 32 bytes) must be set via environment. "
            "The default development key is strictly prohibited."
        )

    if len(JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            f"FATAL SECURITY CONFIGURATION: JWT_SECRET_KEY must be at least 32 characters in production. "
            f"Provided key has only {len(JWT_SECRET_KEY)} characters."
        )

    # 2. Enforce explicit AES encryption key
    if not IMAGE_ENCRYPTION_KEY or not IMAGE_ENCRYPTION_KEY.strip():
        raise RuntimeError(
            "FATAL SECURITY CONFIGURATION: In production mode (APP_ENV=production), "
            "IMAGE_ENCRYPTION_KEY must be explicitly set to a 256-bit Base64-encoded key. "
            "Ephemeral or hardcoded key fallbacks are strictly prohibited."
        )

    # Verify key can be decoded
    from src.security.key_manager import base64_to_key
    try:
        raw_key = base64_to_key(IMAGE_ENCRYPTION_KEY)
        if len(raw_key) != 32:
            raise RuntimeError("Key length mismatch.")
    except Exception as e:
        raise RuntimeError(
            f"FATAL SECURITY CONFIGURATION: IMAGE_ENCRYPTION_KEY failed validation: {e}"
        ) from None

