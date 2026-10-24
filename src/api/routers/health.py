"""
Health & Readiness Router
ISC Project: Secure Storage and Transmission of Medical Data

Endpoints:
- GET /health: Liveness probe verifying the service process is up.
- GET /health/ready: Readiness probe checking database connectivity, storage accessibility, and model loading.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.api.dependencies import get_db, get_inference_engine, get_storage
from src.api.model_service import DenseNetInferenceEngine
from src.security.database import MetadataDB
from src.security.secure_storage import SecureImageStorage

router = APIRouter(prefix="/health", tags=["Health & Readiness"])


@router.get("", status_code=status.HTTP_200_OK)
def liveness() -> Dict[str, str]:
    """
    Liveness probe indicating the backend server is running.
    """
    return {
        "status": "healthy",
        "service": "pneumonia-detection-secure-api",
        "version": "1.0.0"
    }


@router.get("/ready")
def readiness(
    db: MetadataDB = Depends(get_db),
    storage: SecureImageStorage = Depends(get_storage),
    engine: DenseNetInferenceEngine = Depends(get_inference_engine)
) -> JSONResponse:
    """
    Readiness probe verifying operational health of database, storage, and ML engine.
    """
    checks = {
        "database": False,
        "storage": False,
        "model": False
    }

    # 1. Check database
    try:
        with db._connection() as conn:
            conn.execute("SELECT 1;").fetchone()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # 2. Check storage
    try:
        checks["storage"] = storage.storage_dir.exists()
    except Exception:
        checks["storage"] = False

    # 3. Check model
    try:
        checks["model"] = engine.model is not None and engine.checkpoint_path.exists()
    except Exception:
        checks["model"] = False

    all_ready = all(checks.values())
    status_code = status.HTTP_200_OK if all_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "unready",
            "checks": checks,
            "architecture": engine.class_names,
            "threshold": engine.threshold,
            "device": str(engine.device)
        }
    )
