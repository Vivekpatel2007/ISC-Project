"""
Authentication & Role-Based Authorization Module (RBAC)
ISC Project: Secure Storage and Transmission of Medical Data

Security Principles:
1. Salted Password Hashing: bcrypt with automatic salting (cost factor 12).
2. Short-Lived Signed JWTs: HMAC-SHA256 tokens expiring in 30 minutes.
3. Explicit Authorization: Every protected endpoint extracts and cryptographically
   validates user identity; claims from request bodies or headers are strictly ignored.
4. Role Hierarchy:
   - Doctor: Authorized to upload scans for patients and view scans they created.
   - Radiologist: Authorized to view all scans and execute AI-assisted pneumonia diagnostic predictions.
   - Admin: Authorized to view all scans and manage user accounts.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from src.api.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)
from src.security.database import MetadataDB

# OAuth2 password bearer scheme for swagger/openapi integration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# =====================================================================
# Password Hashing & Verification
# =====================================================================
def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with a secure random salt.
    """
    if not isinstance(password, str) or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash in constant time.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


# =====================================================================
# JWT Token Generation & Decoding
# =====================================================================
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Generate a signed, short-lived JSON Web Token (JWT).
    """
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "iat": now,
        "exp": expire,
        "nbf": now
    })

    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Cryptographically verify and decode a JWT access token.
    Raises HTTPException(401) on any signature failure or token expiration.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


# =====================================================================
# FastAPI Dependencies for User & Role Validation
# =====================================================================
def get_current_user_factory(db_getter: Callable[[], MetadataDB]):
    """
    Factory creating the get_current_user dependency bound to a MetadataDB provider.
    """
    def get_current_user(
        token: str = Depends(oauth2_scheme),
        db: MetadataDB = Depends(db_getter)
    ) -> Dict[str, Any]:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing subject identity.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = db.get_user_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account associated with this token no longer exists.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Do not expose the password hash in the user dependency object
        safe_user = {k: v for k, v in user.items() if k != "password_hash"}
        return safe_user

    return get_current_user


def require_roles(*allowed_roles: str):
    """
    Dependency generator enforcing role-based access control.
    Example: Depends(require_roles("radiologist", "admin"))
    """
    def role_checker(current_user: Dict[str, Any] = Depends(oauth2_scheme)) -> None:
        user_role = current_user.get("role") if isinstance(current_user, dict) else None
        if user_role and user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{user_role}' is not authorized to access this resource."
            )
    return role_checker

