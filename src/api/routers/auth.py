"""
Authentication Router
ISC Project: Secure Storage and Transmission of Medical Data

Endpoints:
- POST /auth/login: Authenticate user credentials and issue signed JWT.
- GET  /auth/me: Retrieve current authenticated user profile and assigned role.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth import create_access_token, verify_password
from src.api.config import ACCESS_TOKEN_EXPIRE_MINUTES
from src.api.dependencies import get_current_user, get_db
from src.api.rate_limiter import rate_limit_login
from src.security.database import MetadataDB

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
        "user_id": user["user_id"]
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
