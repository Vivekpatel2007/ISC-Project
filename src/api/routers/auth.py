"""
Authentication Router
ISC Project: Secure Storage and Transmission of Medical Data

Endpoints:
- POST /auth/login: Authenticate user credentials and issue signed JWT.
- GET  /auth/me: Retrieve current authenticated user profile and assigned role.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

from src.api.auth import create_access_token, verify_password, hash_password
from src.api.config import ACCESS_TOKEN_EXPIRE_MINUTES
from src.api.dependencies import get_current_user, get_db
from src.api.rate_limiter import rate_limit_login
from src.security.database import MetadataDB, validate_username
from src.security.exceptions import InvalidIdentifierError, StorageError

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32, description="Staff username")
    password: str = Field(..., min_length=6, description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in_minutes: int


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    role: str
    full_name: Optional[str] = None


class AccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    full_name: str = Field(..., min_length=1, max_length=120)
    username: str = Field(..., min_length=3, max_length=32)
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: Optional[str] = Field(None, min_length=8, max_length=72)


class AccountUpdateResponse(TokenResponse):
    user: UserProfileResponse


@router.post("/login", response_model=TokenResponse)
def login(
    credentials: LoginRequest,
    db: MetadataDB = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_login)
) -> TokenResponse:
    """
    Authenticate a healthcare practitioner (doctor/radiologist/admin) and return a signed JWT.
    """
    user = db.get_user_by_username(credentials.username)
    if not user:
        # Constant-time dummy check to mitigate user enumeration timing attacks
        verify_password("dummy", "$2b$12$e8Yn5VfU0W9X1lB0kL4ISeN4dK9J6rS6Yn5VfU0W9X1lB0kL4ISe")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "user_id": user["user_id"],
        "auth_version": user.get('auth_version', 0)
    })

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user["role"],
        username=user["username"],
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )


@router.get("/me", response_model=UserProfileResponse)
def get_profile(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> UserProfileResponse:
    """
    Return the profile and role of the currently authenticated user.
    """
    return UserProfileResponse(
        user_id=current_user["user_id"],
        username=current_user["username"],
        role=current_user["role"],
        full_name=current_user.get("full_name")
    )


@router.put('/me', response_model=AccountUpdateResponse)
def update_profile(change: AccountUpdateRequest,
                   current_user: Dict[str, Any] = Depends(get_current_user),
                   db: MetadataDB = Depends(get_db),
                   _rate_limit: None = Depends(rate_limit_login)) -> AccountUpdateResponse:
    user = db.get_user_by_id(current_user['user_id'])
    if not user or not verify_password(change.current_password, user['password_hash']):
        raise HTTPException(status_code=403, detail='Current password is incorrect.')
    name = change.full_name.strip()
    if not name or any(ord(c) < 32 for c in name):
        raise HTTPException(status_code=422, detail='Enter a valid display name.')
    try:
        username = validate_username(change.username)
    except InvalidIdentifierError:
        raise HTTPException(status_code=422, detail='Username must use 3–32 letters, numbers, dots, underscores, or hyphens.') from None
    if change.new_password and len(change.new_password.encode('utf-8')) > 72:
        raise HTTPException(status_code=422, detail='Password must be at most 72 UTF-8 bytes.')
    password_hash = hash_password(change.new_password) if change.new_password else user['password_hash']
    try:
        updated = db.update_account(user['user_id'], username, name, password_hash, user.get('auth_version', 0))
    except StorageError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    token = create_access_token(dict(sub=updated['username'], role=updated['role'], user_id=updated['user_id'],
                                     auth_version=updated['auth_version']))
    return AccountUpdateResponse(access_token=token, role=updated['role'], username=updated['username'],
                                 expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
                                 user=UserProfileResponse(**updated))
