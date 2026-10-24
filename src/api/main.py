"""
Main FastAPI Application
ISC Project: AI-Based Pneumonia Detection with Secure Storage & Transmission

Features:
1. Security Headers Middleware (OWASP recommended defense-in-depth).
2. Strict CORS Configuration.
3. Clean Sanitized Exception Handlers (no stack traces or keys leaked).
4. Startup Seeding: Initializes database and seeds default demonstration accounts.
5. Lifespan Engine: Pre-loads the DenseNet121 model and cryptographic storage engine.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.auth import hash_password
from src.api.config import (
    CORS_ORIGINS,
    ENABLE_DOCS,
    ENFORCE_HTTPS,
    IS_PRODUCTION,
    SEED_DEMO_USERS,
    validate_production_config,
)
from src.api.dependencies import get_db, get_inference_engine, get_storage
from src.api.model_service import ModelInferenceError
from src.api.routers import auth_router, health_router, scans_router
from src.security.exceptions import (
    AuthenticationError,
    DecryptionError,
    IntegrityVerificationError,
    InvalidIdentifierError,
    ScanNotFoundError,
    SecurityError,
    StorageError,
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Appends OWASP recommended security headers to all HTTP responses.
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; "
            "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "frame-ancestors 'none';"
        )
        if ENFORCE_HTTPS or IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager: validates production secrets, pre-warms database,
    optionally seeds demo credentials in development, and loads the DenseNet121 inference model.
    """
    # 1. Fail fast if production security requirements are not satisfied
    validate_production_config()

    # 2. Warm up database
    db = get_db()

    # 3. Seed demonstration accounts only if explicitly permitted (development/testing)
    if SEED_DEMO_USERS:
        if db.get_user_by_username("doctor1") is None:
            db.create_user(
                username="doctor1",
                password_hash=hash_password("DoctorPassword123!"),
                role="doctor",
                full_name="Dr. Sarah Chen, MD (Pediatrics)"
            )

        if db.get_user_by_username("radiologist1") is None:
            db.create_user(
                username="radiologist1",
                password_hash=hash_password("RadioPassword123!"),
                role="radiologist",
                full_name="Dr. James Wilson, MD (Radiology)"
            )

    # 4. Pre-warm secure storage engine and ML model
    get_storage()
    get_inference_engine()

    yield

    # Clean shutdown tasks if any
    pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="AI-Based Pneumonia Detection & Secure Medical Data API",
        description=(
            "Secure, HIPAA-conscious REST API providing AES-256-GCM encrypted medical "
            "radiograph storage, SHA-256 integrity verification, role-based access control, "
            "and in-memory DenseNet121 AI-assisted pneumonia screening."
        ),
        version="2.0.0",
        docs_url="/docs" if ENABLE_DOCS else None,
        redoc_url="/redoc" if ENABLE_DOCS else None,
        openapi_url="/openapi.json" if ENABLE_DOCS else None,
        lifespan=lifespan
    )

    # 1. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # 3. Exception Handlers (Sanitized for zero leakage)
    @app.exception_handler(ScanNotFoundError)
    async def scan_not_found_handler(request: Request, exc: ScanNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Medical scan record not found."}
        )

    @app.exception_handler(InvalidIdentifierError)
    async def invalid_id_handler(request: Request, exc: InvalidIdentifierError):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Invalid identifier format or prohibited path characters."}
        )

    @app.exception_handler(AuthenticationError)
    async def auth_tamper_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Cryptographic authentication failed: ciphertext is corrupt or tampered with."}
        )

    @app.exception_handler(IntegrityVerificationError)
    async def integrity_handler(request: Request, exc: IntegrityVerificationError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Data integrity check failed: payload does not match expected SHA-256 hash."}
        )

    @app.exception_handler(ModelInferenceError)
    async def inference_error_handler(request: Request, exc: ModelInferenceError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": f"Model inference error: {str(exc)}"}
        )

    @app.exception_handler(SecurityError)
    async def security_error_handler(request: Request, exc: SecurityError):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "A security or storage operation failed."}
        )

    # 4. Include Routers
    app.include_router(auth_router)
    app.include_router(scans_router)
    app.include_router(health_router)

    return app


app = create_app()
