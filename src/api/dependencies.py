"""
FastAPI Dependency Injection Module
ISC Project: Secure Storage and Transmission of Medical Data

Provides thread-safe, lazily initialized singletons for:
- Database connection (MetadataDB)
- Secure Storage engine (SecureImageStorage)
- DenseNet121 Inference Engine (DenseNetInferenceEngine)
- User Authentication & Role enforcement dependencies
"""

import os
from threading import RLock
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, status

from src.api.auth import bearer_token, decode_access_token
from src.api.config import (
    IMAGE_ENCRYPTION_KEY,
    IS_PRODUCTION,
    MAX_IMAGE_SIZE_BYTES,
    METADATA_DB_PATH,
    MODEL_CHECKPOINT_PATH,
    SECURE_STORAGE_DIR,
)
from src.api.model_service import DenseNetInferenceEngine
from src.security.database import MetadataDB
from src.security.key_manager import base64_to_key, generate_key, load_key_from_env
from src.security.secure_storage import SecureImageStorage

# Shared lazy instances
_db_instance: Optional[MetadataDB] = None
_storage_instance: Optional[SecureImageStorage] = None
_model_instance: Optional[DenseNetInferenceEngine] = None
_initialization_lock = RLock()


def get_db() -> MetadataDB:
    """Provide singleton MetadataDB instance."""
    global _db_instance
    if _db_instance is None:
        with _initialization_lock:
            if _db_instance is None:
                _db_instance = MetadataDB(METADATA_DB_PATH)
    return _db_instance


def get_storage_key() -> bytes:
    """
    Retrieve AES-256-GCM encryption key from environment.
    In production mode, raises RuntimeError if missing or invalid.
    In development mode, falls back to a deterministic development key with warning.
    """
    try:
        return load_key_from_env()
    except Exception:
        raw_env = os.getenv("IMAGE_ENCRYPTION_KEY")
        if raw_env:
            return base64_to_key(raw_env)
        
        if IS_PRODUCTION:
            raise RuntimeError(
                "FATAL: IMAGE_ENCRYPTION_KEY must be provided via environment in production mode. "
                "Insecure fallback keys are prohibited."
            )
        # Development fallback only
        return b"12345678901234567890123456789012"  # 32 bytes


def get_storage() -> SecureImageStorage:
    """Provide singleton SecureImageStorage instance."""
    global _storage_instance
    if _storage_instance is None:
        with _initialization_lock:
            if _storage_instance is None:
                key = get_storage_key()
                _storage_instance = SecureImageStorage(
                    key=key,
                    storage_dir=SECURE_STORAGE_DIR,
                    db_path=METADATA_DB_PATH,
                    max_file_size_bytes=MAX_IMAGE_SIZE_BYTES
                )
    return _storage_instance


def get_inference_engine() -> DenseNetInferenceEngine:
    """Provide singleton DenseNet121 inference engine instance."""
    global _model_instance
    if _model_instance is None:
        with _initialization_lock:
            if _model_instance is None:
                _model_instance = DenseNetInferenceEngine(MODEL_CHECKPOINT_PATH)
    return _model_instance


def get_initialized_db() -> Optional[MetadataDB]:
    """Readiness observes published instances without initializing or blocking on them."""
    return _db_instance


def get_initialized_storage() -> Optional[SecureImageStorage]:
    return _storage_instance


def get_initialized_inference_engine() -> Optional[DenseNetInferenceEngine]:
    return _model_instance


def get_current_user(
    token: str = Depends(bearer_token),
    db: MetadataDB = Depends(get_db)
) -> Dict[str, Any]:
    """
    Validate incoming Bearer JWT and return the authenticated user record.
    Rejects any unauthenticated or expired request with 401.
    """
    payload = decode_access_token(token)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing subject identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get_user_by_username(username)
    if (not user or payload.get('auth_version', 0) != user.get('auth_version', 0)
            or payload.get('user_id') != user['user_id']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return safe user dictionary without password hash
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user.get("full_name")
    }


def require_role(*allowed_roles: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """
    Role-Based Access Control (RBAC) dependency factory.
    Enforces that current_user has one of the specified allowed_roles.
    """
    def role_dependency(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role", "")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{user_role}' is not authorized to access this medical resource. Required: {list(allowed_roles)}"
            )
        return current_user

    return role_dependency
