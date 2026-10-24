# Deployment Preparation & Operations Guide

**Project Title:** AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data  
**Scope:** Phase 4 Deployment Preparation  
**Architecture:** FastAPI (Backend) + PyTorch DenseNet121 + AES-256-GCM Storage + Next.js App Router (Frontend)

---

## 1. Important Regulatory & Clinical Disclaimers

> [!CAUTION]
> **Educational & Research Prototype Only:** This system is an educational clinical decision-support demonstration. It has **NOT** been certified by the FDA, CE, or any healthcare regulatory body. It must **NEVER** be used as a standalone or definitive diagnostic system. Clinical correlation by a licensed radiologist or physician is legally and clinically required.
> 
> **No Real Patient PII:** Do not deploy real un-anonymized patient health records without institutional IRB approval and full compliance with regional privacy laws (HIPAA, GDPR, HITECH).

---

## 2. Environment Configuration

### Backend Environment Variables (`.env`)

Configure the backend via a dedicated `.env` file or orchestrator secrets (Kubernetes Secrets, Docker Secrets, Systemd Environment):

```env
# =====================================================================
# Production Backend Environment Configuration
# =====================================================================

# 1. Environment Mode (Enforces secret validation on boot)
APP_ENV=production

# 2. Cryptography & Key Management (MANDATORY: MUST BE 32 RAW BYTES / 256-BIT BASE64)
# Generate with: python -c "from src.security.key_manager import generate_key, key_to_base64; print(key_to_base64(generate_key()))"
IMAGE_ENCRYPTION_KEY=<REPLACE_WITH_GENERATED_BASE64_256BIT_KEY>

# 3. JWT Authentication Secret (MANDATORY: MINIMUM 32 CHARACTERS)
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=<REPLACE_WITH_CRYPTOGRAPHICALLY_RANDOM_SECRET_KEY>

# Token Expiration (Default: 30 minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=30

# 4. Storage & Database Paths
SECURE_STORAGE_DIR=/var/data/secure_images
METADATA_DB_PATH=/var/data/metadata.db
MODEL_CHECKPOINT_PATH=models/densenet121_pneumonia_best.pth

# 5. File Upload Restrictions
MAX_IMAGE_SIZE_BYTES=20971520

# 6. Production Hardening Flags
ENFORCE_HTTPS=true
ENABLE_DOCS=false
SEED_DEMO_USERS=false

# 7. Allowed CORS Origins (Exact production domain only; no wildcards)
CORS_ORIGINS=https://pulmoscan.hospital.local,https://app.pulmoscan.org
```

### Frontend Environment Variables (`frontend/.env.production`)

```env
# PulmoScan Production Frontend
# Points to the public HTTPS domain of the FastAPI backend or reverse proxy
NEXT_PUBLIC_API_BASE_URL=https://api.pulmoscan.hospital.local
```

---

## 3. Secret Management & Key Generation

Never commit secret keys or environment files to version control.

### Generating Keys
Run the following PowerShell commands in the activated virtual environment:

1. **AES-256-GCM Image Encryption Key (256 bits, Base64 URL-safe):**
   ```powershell
   .\.venv\Scripts\python.exe -c "from src.security.key_manager import generate_key, key_to_base64; print(key_to_base64(generate_key()))"
   ```

2. **JWT Signing Secret (256-bit cryptographically secure hex):**
   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
   ```

### Fail-Safe Behavior
When `APP_ENV=production` is set, the backend runs `validate_production_config()` on startup:
- If `JWT_SECRET_KEY` equals the dev default or is shorter than 32 characters, startup is **aborted immediately**.
- If `IMAGE_ENCRYPTION_KEY` is missing or fails 32-byte length validation, startup is **aborted immediately**.
- Hardcoded fallback keys are permanently disabled in production mode.

---

## 4. HTTPS, Reverse Proxy & CORS Requirements

In production, the FastAPI application should listen on a private loopback port (`127.0.0.1:8000` or UNIX socket) behind a hardened reverse proxy (e.g., Nginx, Caddy, or an AWS Application Load Balancer) that handles TLS termination.

### Recommended Nginx Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name api.pulmoscan.hospital.local;

    # TLS Certificates
    ssl_certificate /etc/ssl/certs/pulmoscan_cert.pem;
    ssl_certificate_key /etc/ssl/private/pulmoscan_key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Request Size Limits (Must align with backend MAX_IMAGE_SIZE_BYTES)
    client_max_body_size 25M;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Content-Security-Policy "default-src 'self';" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }
}
```

---

## 5. Encryption Key Backup, Persistence & Recovery

### Cryptographic Reality & Warning
> [!WARNING]
> AES-256-GCM is an authenticated symmetric cipher. There is **no master key**, **no backdoor**, and **no recovery mechanism**. If the `IMAGE_ENCRYPTION_KEY` is lost, all encrypted medical images stored under that key become permanently unrecoverable.

### Key Lifecycle Guidelines
1. **Key Backup:** Store an offline, encrypted copy of the Base64 key string in an enterprise password vault (e.g. 1Password, Bitwarden) or Cloud Key Management Service (AWS KMS, Azure Key Vault).
2. **Key Persistence:** Ensure the key variable is persistent across host reboots and container restarts.
3. **Key Rotation Plan:** Do not change `IMAGE_ENCRYPTION_KEY` on an existing database without executing a migration script that:
   - Retrieves each scan with old key $K_1$
   - Decrypts in memory and validates tag
   - Re-encrypts with new key $K_2$ with fresh nonce
   - Atomically updates disk container and SQLite checksum.

---

## 6. Backup Consistency & Disaster Recovery

Medical imaging systems require atomic consistency between the encrypted image containers and the metadata database.

### 1. SQLite Metadata Backup
Never copy `metadata.db` while active writes may occur. Use the SQLite online backup utility:
```powershell
.\.venv\Scripts\python.exe -c "
import sqlite3
src = sqlite3.connect('secure_data/metadata.db')
dst = sqlite3.connect('backups/metadata_backup.db')
src.backup(dst)
dst.close()
src.close()
print('Consistent SQLite snapshot created.')
"
```

### 2. File Synchronization
Back up the `secure_data/encrypted_images/` directory concurrently with the SQLite snapshot to ensure all referenced `.enc` files exist.

---

## 7. Startup Verification & Readiness Probes

Before routing practitioner traffic to a freshly booted instance:

1. **Liveness Check:**
   ```bash
   curl -f http://127.0.0.1:8000/health
   # Expected: {"status":"healthy","service":"pneumonia-detection-secure-api","version":"1.0.0"}
   ```

2. **Readiness Probe:**
   ```bash
   curl -f http://127.0.0.1:8000/health/ready
   # Expected HTTP 200: {"status":"ready","checks":{"database":true,"storage":true,"model":true},"threshold":0.40,"device":"cuda"}
   ```
   If any component is unready (e.g. storage directory not mounted or model checkpoint missing), the endpoint returns `HTTP 503 Service Unavailable`.
