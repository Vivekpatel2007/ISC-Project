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

# Security & Tokens
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "insecure-dev-jwt-secret-key-replace-in-production-32bytes")
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
