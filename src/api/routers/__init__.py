"""
API Routers Package
ISC Project: Secure Storage and Transmission of Medical Data
"""

from src.api.routers.auth import router as auth_router
from src.api.routers.health import router as health_router
from src.api.routers.scans import router as scans_router

__all__ = ["auth_router", "scans_router", "health_router"]
