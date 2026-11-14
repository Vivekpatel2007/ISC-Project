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
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)
from src.security.database import MetadataDB

# Login accepts JSON, so document bearer-token authorization rather than an
# OAuth2 password form that this API does not implement.
_bearer = HTTPBearer(auto_error=False, scheme_name='BearerAuth', bearerFormat='JWT')


def bearer_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail='Not authenticated.', headers={'WWW-Authenticate':'Bearer'})
    return credentials.credentials


oauth2_scheme = bearer_token  # Compatibility for the older dependency factory below.
# Valid cost-12 hash for comparable bcrypt work when the username is unknown.
DUMMY_PASSWORD_HASH = '$2b$12$l9qosfdu4OPtCslUhjD9Quq9Zu9Zb6rKcf2cwcYOeR.5HdYWB.nG.'


# =====================================================================
# Password Hashing & Verification
# =====================================================================
def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt with a secure random salt.
    """
    if not isinstance(password, str) or len(password) < 6 or len(password.encode('utf-8')) > 72:
        raise ValueError("Password must be at least 6 characters and at most 72 UTF-8 bytes.")
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
    to_encode.setdefault('auth_version', 0)
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
            algorithms=[JWT_ALGORITHM],
            options={'require': ['exp', 'iat', 'nbf', 'sub', 'user_id', 'auth_version']},
        )
        if (not isinstance(payload['user_id'], str) or not payload['user_id']
                or type(payload['auth_version']) is not int or payload['auth_version'] < 0):
            raise jwt.InvalidTokenError('Invalid identity claims.')
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
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
        if (not user or payload.get('auth_version', 0) != user.get('auth_version', 0)
                or payload.get('user_id') != user['user_id']):
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
    """Compatibility alias; always authenticate and check the database-backed role."""
    # Import when the factory is used to avoid the auth/dependencies import cycle.
    from src.api.dependencies import require_role
    return require_role(*allowed_roles)

