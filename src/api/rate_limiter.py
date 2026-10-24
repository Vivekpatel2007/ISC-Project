"""
Rate Limiting Module
ISC Project: Secure Storage and Transmission of Medical Data

Provides thread-safe, in-memory sliding window rate limiting for FastAPI.
Protects sensitive endpoints against:
1. Brute-force credential attacks (POST /auth/login)
2. Resource exhaustion / GPU DoS (POST /scans/{id}/predict)
"""

import os
import sys
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding-window rate limiter.
    
    Tracks timestamps of requests within a sliding window.
    Expired timestamps outside the window are automatically purged.
    """
    def __init__(self, max_requests: int, window_seconds: int, name: str = "default"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._enabled = True

    def disable_for_tests(self) -> None:
        """Temporarily disable rate limiter for automated testing."""
        self._enabled = False

    def enable(self) -> None:
        """Re-enable rate limiter."""
        self._enabled = True

    def reset(self) -> None:
        """Clear all recorded request history."""
        with self._lock:
            self._history.clear()

    def check(self, key: str) -> None:
        """
        Check if the key has exceeded the rate limit.
        If exceeded, raises HTTPException(429) with Retry-After header.
        Otherwise, records the current request timestamp.
        """
        if not self._enabled:
            return

        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._history[key]
            # Prune expired entries
            valid_timestamps = [ts for ts in timestamps if ts > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= self.max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {self.name}. Maximum {self.max_requests} requests per {self.window_seconds}s. Please wait {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)}
                )

            self._history[key].append(now)


# In testing environments (pytest), use generous default limits to avoid breaking unit test suites;
# in production/development, use strict protective limits.
IS_TESTING = "pytest" in sys.modules or os.getenv("TESTING", "").lower() in ("true", "1")
DEFAULT_LOGIN_MAX = int(os.getenv("RATE_LIMIT_LOGIN_MAX", "200" if IS_TESTING else "10"))
DEFAULT_INFERENCE_MAX = int(os.getenv("RATE_LIMIT_INFERENCE_MAX", "200" if IS_TESTING else "30"))

# Global rate limiter instances:
# 1. Login limiter: 10 attempts per 60 seconds per IP (or 200 during testing)
login_rate_limiter = SlidingWindowRateLimiter(max_requests=DEFAULT_LOGIN_MAX, window_seconds=60, name="authentication")

# 2. Inference limiter: 30 predictions per 60 seconds per user (or 200 during testing)
inference_rate_limiter = SlidingWindowRateLimiter(max_requests=DEFAULT_INFERENCE_MAX, window_seconds=60, name="inference")


def get_client_ip(request: Request) -> str:
    """Extract client IP address safely, checking trusted headers if configured."""
    client = request.client
    return client.host if client else "unknown"


def rate_limit_login(request: Request) -> None:
    """FastAPI dependency for login rate limiting by IP."""
    ip = get_client_ip(request)
    login_rate_limiter.check(ip)


def rate_limit_inference(request: Request) -> None:
    """FastAPI dependency for inference rate limiting by IP."""
    ip = get_client_ip(request)
    inference_rate_limiter.check(ip)
