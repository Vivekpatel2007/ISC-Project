# Security Audit & Vulnerability Assessment Report

**Project Title:** AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data  
**Scope:** Phase 4 Security Hardening & Audit  
**Date of Audit:** October 2026  
**Audited Modules:**
- Cryptographic Engine & Key Management (`src/security/encryption.py`, `src/security/key_manager.py`, `src/security/integrity.py`)
- Secure Storage & Metadata Database (`src/security/secure_storage.py`, `src/security/database.py`)
- FastAPI Backend & Authentication (`src/api/auth.py`, `src/api/config.py`, `src/api/dependencies.py`, `src/api/main.py`)
- API Routers (`src/api/routers/auth.py`, `src/api/routers/scans.py`, `src/api/routers/health.py`)
- DenseNet121 Inference Engine (`src/api/model_service.py`)
- Next.js Healthcare Frontend (`frontend/src/context/auth-context.tsx`, `frontend/src/lib/api-client.ts`, `frontend/src/app/`)

---

## 1. Executive Summary

A systematic security audit was conducted covering encryption, key lifecycle, role-based authorization, file upload controls, HTTP security headers, metadata confidentiality, and frontend session state.

The application architecture demonstrates strong defensive foundations:
1. Authenticated encryption uses **AES-256-GCM** with fresh 96-bit nonces (`os.urandom(12)`) and 128-bit MAC tags (NIST SP 800-38D).
2. Pure in-memory decryption ensures zero plaintext radiograph images reside on disk at any stage.
3. Access tokens are short-lived (30 minutes) and kept strictly in volatile React memory on the frontend, avoiding persistent browser storage (`localStorage` / `sessionStorage`).
4. Role-based access control (RBAC) enforces strict practitioner boundaries (doctors are restricted to their own uploaded scans, while radiologists have institutional diagnostic review clearance).

Targeted remediations were implemented for verified findings:
- Enforcing production environment secret validation to eliminate default development keys.
- Thread-safe sliding-window rate limiting on login and inference endpoints.
- Pillow decompression bomb safeguards.
- OWASP security headers (including `Content-Security-Policy` and `Strict-Transport-Security`).

---

## 2. Audit Findings by Severity

| ID | Title | Domain | Severity | Status |
|---|---|---|---|---|
| **SEC-01** | Insecure Hardcoded Fallback for AES Data Encryption Key | Key Management | **High** | **Remediated** |
| **SEC-02** | Insecure Default Fallback for JWT Signing Secret | Authentication | **High** | **Remediated** |
| **SEC-03** | Lack of Rate Limiting on Login and Inference Endpoints | API / DoS | **Medium** | **Remediated** |
| **SEC-04** | Unconditional Demo Account Auto-Seeding | Authentication | **Medium** | **Remediated** |
| **SEC-05** | Missing Pillow Decompression Bomb Max Pixel Clamp | File Upload | **Low** | **Remediated** |
| **SEC-06** | Missing Content-Security-Policy (CSP) & HSTS Headers | HTTP Security | **Low** | **Remediated** |
| **SEC-07** | Incomplete `require_roles` Function in `auth.py` | Code Integrity | **Low** | **Remediated** |
| **SEC-08** | SQLite Metadata Database Stored in Plaintext | Database | **Informational** | **Documented** |
| **SEC-09** | Language-Level Impossibility of Guaranteed Zeroization in CPython | Cryptography | **Informational** | **Documented** |

---

## 3. Detailed Findings, Evidence & Remediations

### SEC-01: Insecure Hardcoded Fallback for AES Data Encryption Key
- **Severity:** High
- **Evidence:** `src/api/dependencies.py` lines 48-58 contained a fallback `return b"12345678901234567890123456789012"` if `IMAGE_ENCRYPTION_KEY` failed to load.
- **Potential Impact:** In a deployment with misconfigured environment variables, patient scans would be encrypted using a publicly known static key.
- **Remediation:** Added `APP_ENV` and `IS_PRODUCTION` controls in `src/api/config.py`. In `src/api/dependencies.py`, if `IS_PRODUCTION` is True and `IMAGE_ENCRYPTION_KEY` is missing or invalid, the backend immediately raises `RuntimeError` and refuses to boot. In development, a prominent warning is logged.
- **Verification:** Verified via `tests/test_security_hardening.py::test_production_fails_on_missing_encryption_key`.

### SEC-02: Insecure Default Fallback for JWT Signing Secret
- **Severity:** High
- **Evidence:** `src/api/config.py` defaulted `JWT_SECRET_KEY` to `"insecure-dev-jwt-secret-key-replace-in-production-32bytes"`.
- **Potential Impact:** An attacker knowing the open-source repository could forge valid HMAC-SHA256 tokens for `doctor`, `radiologist`, or `admin`, bypassing authentication.
- **Remediation:** Implemented `validate_production_config()` in `src/api/config.py`. If `APP_ENV=production` and `JWT_SECRET_KEY` is the default string or shorter than 32 characters, startup fails fast with `RuntimeError`.
- **Verification:** Verified via `tests/test_security_hardening.py::test_production_fails_on_default_jwt_secret` and `test_production_fails_on_short_jwt_secret`.

### SEC-03: Lack of Rate Limiting on Login and Inference Endpoints
- **Severity:** Medium
- **Evidence:** Neither `POST /auth/login` nor `POST /scans/{id}/predict` had request throttling.
- **Potential Impact:** Credential brute-forcing on login; GPU resource exhaustion / DoS by authenticated users on the inference endpoint.
- **Remediation:** Implemented thread-safe `SlidingWindowRateLimiter` in `src/api/rate_limiter.py`. Integrated `rate_limit_login` dependency (10 requests/minute/IP) and `rate_limit_inference` dependency (30 requests/minute/IP). Returns HTTP 429 Too Many Requests with `Retry-After` header.
- **Verification:** Verified via `tests/test_security_hardening.py::test_login_rate_limiting`.

### SEC-04: Unconditional Demo Account Auto-Seeding
- **Severity:** Medium
- **Evidence:** `lifespan()` in `src/api/main.py` automatically seeded `doctor1` (`DoctorPassword123!`) and `radiologist1` (`RadioPassword123!`) into SQLite on startup.
- **Potential Impact:** If deployed to production, hardcoded demo credentials would exist by default.
- **Remediation:** Gated demo user creation behind `SEED_DEMO_USERS` flag (defaults to `true` in development, `false` in production).
- **Verification:** Confirmed in `main.py` lifespan and deployment configuration documentation.

### SEC-05: Missing Pillow Decompression Bomb Max Pixel Clamp
- **Severity:** Low (Defense-in-depth)
- **Evidence:** Pillow default `Image.MAX_IMAGE_PIXELS` was ~89 million pixels. Although image dimension checks occurred after decoding, decompression bombs could allocate excessive memory during initial header parsing.
- **Remediation:** Clamped `Image.MAX_IMAGE_PIXELS = MAX_IMAGE_DIMENSION * MAX_IMAGE_DIMENSION` (4096 * 4096 = 16,777,216 pixels) in `src/api/model_service.py`. Added explicit `except Image.DecompressionBombError:` handling.
- **Verification:** Verified via `tests/test_security_hardening.py::test_decompression_bomb_rejection`.

### SEC-06: Missing Content-Security-Policy (CSP) & HSTS Headers
- **Severity:** Low
- **Evidence:** `SecurityHeadersMiddleware` lacked CSP and HSTS headers.
- **Remediation:** Added `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none';` and conditional `Strict-Transport-Security: max-age=31536000; includeSubDomains` when `ENFORCE_HTTPS` or `IS_PRODUCTION` is enabled.
- **Verification:** Verified via `tests/test_security_hardening.py::test_security_headers_present_on_responses` and live E2E suite.

### SEC-07: Incomplete `require_roles` Function in `auth.py`
- **Severity:** Low
- **Evidence:** `src/api/auth.py` had a stub `require_roles` function containing only `pass`.
- **Remediation:** Replaced stub with functional role checking dependency.
- **Verification:** Checked in unit tests and code inspection.

---

## 4. Architectural Boundaries & Documented Limitations

### SEC-08: SQLite Metadata Storage at Rest
- **Current State:** The SQLite database file (`secure_data/metadata.db`) is standard unencrypted SQLite.
- **Analysis:**
  - What is encrypted: All raw chest X-ray image bytes are encrypted in separate binary containers (`.enc`) with AES-256-GCM.
  - What is stored in SQLite: Pseudonymous patient identifiers (`ANON-XXXXX`), file sizes, SHA-256 digests, timestamps, usernames, and diagnostic classification results (`NORMAL` / `PNEUMONIA`).
  - No direct PII (patient names, phone numbers, addresses, social security numbers) is stored in the database.
- **Production Recommendation:** For production HIPAA-conscious compliance, the host filesystem must use full-disk encryption (BitLocker on Windows, LUKS on Linux) or the application must adopt an encrypted SQLite engine such as SQLCipher.

### SEC-09: Python Memory Management & Zeroization Impossibility
- **Current State:** Decrypted image bytes and cryptographic keys exist as immutable Python `bytes` in process memory.
- **Analysis:** Due to CPython's garbage collector, memory fragmentation, string interning, and operating system virtual memory paging, Python applications cannot guarantee complete zeroization (secure clearing) of all memory copies.
- **Mitigation:** Sensitive buffers are held strictly in local function scopes (`io.BytesIO`) and dereferenced immediately. In production, process memory dumping should be restricted by OS permissions, and swap space should be encrypted.

---

## 5. Explicitly Unverified Areas

The following items are outside the scope of a local educational prototype and could not be verified locally:
1. **Hardware Security Module (HSM) / Cloud KMS:** Encryption keys are managed via environment variables rather than AWS KMS, Azure Key Vault, or Windows DPAPI.
2. **TLS Certificate Authority Verification:** Tested over local loopback (`http://127.0.0.1`); actual TLS termination must be validated in the production reverse proxy (Nginx, Caddy, AWS ALB).
3. **Database Distributed Replication:** SQLite is a single-file local database; cross-datacenter multi-region replication was not tested.
