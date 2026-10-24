# Phase 2: Secure FastAPI Backend Documentation
**Project**: AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data  
**Module**: `src/api`  
**Framework**: FastAPI, Uvicorn, PyTorch, PyJWT, Cryptography, Bcrypt  

---

## 1. System Architecture & End-to-End Workflow

The Phase 2 FastAPI backend serves as the secure interface between healthcare practitioners (doctors and radiologists), the AES-256-GCM encrypted image repository (Phase 1), and the trained DenseNet121 AI inference engine.

```
                    [ Healthcare Client / Postman ]
                                  │
                                  ▼
                     [ HTTPS / TLS 1.3 Encryption ]
                                  │
                                  ▼
                     [ Security Headers Middleware ]
                     (X-Content-Type-Options, X-Frame-Options)
                                  │
                                  ▼
                   [ JWT Authentication & RBAC ]
                   (Verifies Bearer token, enforces role)
                                  │
                ┌─────────────────┴─────────────────┐
                ▼                                   ▼
        [ POST /scans ]                 [ POST /scans/{id}/predict ]
                │                                   │
                ▼                                   ▼
[ In-Memory Image Validation ]           [ In-Memory Decryption ]
(Header & PIL dimension checks)          (AES-256-GCM tag verification)
                │                                   │
                ▼                                   ▼
[ AES-256-GCM Encryption ]              [ DenseNet121 Inference ]
(PX01 format, fresh 96-bit nonce)       (Evaluated under torch.no_grad)
                │                                   │
                ▼                                   ▼
[ Atomic Write to .enc ]                [ Clinical Screening Output ]
                │                                   │
                ▼                                   ▼
[ Record Metadata in SQLite ]           [ Update Scan Status in SQLite ]
```

---

## 2. Authentication & Role-Based Access Control (RBAC)

### 2.1 Role Matrix
Access control is enforced cryptographically on every protected endpoint based on claims inside verified JWT access tokens. Untrusted request bodies or headers cannot claim a role or patient identity.

| Role | Permitted Actions | Scans Accessible |
|---|---|---|
| **`doctor`** | Upload scans (`POST /scans`), view owned scans (`GET /scans/{id}`), trigger AI screening on owned scans (`POST /scans/{id}/predict`). | Restricted strictly to scans uploaded by that specific doctor. Cross-doctor access is blocked (`403 Forbidden`). |
| **`radiologist`** | Full diagnostic review: view all institutional scans (`GET /scans`), view any scan details (`GET /scans/{id}`), execute AI predictions (`POST /scans/{id}/predict`). | All patient scan records across the facility. |
| **`admin`** | Full institutional access and user administration. | All records. |

### 2.2 Security Features
1. **Password Storage**: Passwords are never stored in plaintext. They are salted and hashed using `bcrypt` (work factor 12).
2. **Short-Lived Access Tokens**: Signed with HMAC-SHA256 (`HS256`), containing timestamps (`iat`, `nbf`, `exp`) set to expire in 30 minutes.
3. **Zero Plaintext at Rest**: Decrypted images reside strictly in volatile memory (`bytes` / `io.BytesIO`) and are immediately purged after model evaluation. Plaintext scans are never written to disk.

---

## 3. Pre-Seeded Demonstration Accounts

For local evaluation, the database automatically seeds two test accounts upon first startup:

| Role | Username | Password | Full Name |
|---|---|---|---|
| **Doctor** | `doctor1` | `DoctorPassword123!` | Dr. Sarah Chen, MD (Pediatrics) |
| **Radiologist** | `radiologist1` | `RadioPassword123!` | Dr. James Wilson, MD (Radiology) |

---

## 4. API Endpoints Specification

### 4.1 `POST /auth/login`
Authenticates a practitioner and issues a signed JWT token.

* **Request Body** (`application/json`):
  ```json
  {
    "username": "doctor1",
    "password": "DoctorPassword123!"
  }
  ```
* **Success Response** (`200 OK`):
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "role": "doctor",
    "username": "doctor1",
    "expires_in_minutes": 30
  }
  ```

---

### 4.2 `POST /scans`
Uploads a raw radiograph, verifies genuine image headers and dimensions, encrypts via AES-256-GCM, and saves pseudonymous metadata in SQLite.

* **Headers**: `Authorization: Bearer <access_token>`
* **Content-Type**: `multipart/form-data`
* **Form Parameters**:
  - `file`: Raw image binary (`.png` or `.jpeg`).
  - `patient_id`: Pseudonymous identifier (e.g. `ANON-00912`).
* **Success Response** (`201 Created`):
  ```json
  {
    "scan_id": "8c593258-2921-4fca-8608-8e6ad71bf64c",
    "patient_id": "ANON-00912",
    "file_size_bytes": 48291,
    "format_version": 1,
    "created_at": "2026-10-24T08:30:12.459102+00:00",
    "prediction_status": "PENDING",
    "predicted_class": null,
    "prediction_probability": null,
    "uploaded_by": "doctor1"
  }
  ```

---

### 4.3 `GET /scans/{scan_id}`
Retrieves metadata for an authorized scan.

* **Headers**: `Authorization: Bearer <access_token>`
* **Success Response** (`200 OK`): Returns `ScanMetadataResponse`.
* **Cross-User Protection**: If Doctor A attempts to view a scan uploaded by Doctor B, returns `403 Forbidden`.

---

### 4.4 `POST /scans/{scan_id}/predict`
Retrieves the encrypted container from disk, decrypts and authenticates the ciphertext in memory, and passes the raw bytes directly to the DenseNet121 model.

* **Headers**: `Authorization: Bearer <access_token>`
* **Success Response** (`200 OK`):
  ```json
  {
    "scan_id": "8c593258-2921-4fca-8608-8e6ad71bf64c",
    "patient_id": "ANON-00912",
    "prediction": "NORMAL",
    "confidence": 0.9682,
    "pneumonia_probability": 0.0318,
    "normal_probability": 0.9682,
    "threshold_applied": 0.40,
    "model_architecture": "densenet121",
    "model_epoch": 5,
    "device": "cuda",
    "disclaimer": "AI-assisted screening output for clinical decision support. Not a standalone or definitive medical diagnosis. Clinical review and correlation by a qualified radiologist or physician is required."
  }
  ```
* **Tampering Defense**: If an attacker has modified even a single byte of the `.enc` file on disk, GCM authentication fails immediately, aborting inference and returning `409 Conflict`.

---

### 4.5 `GET /health` & `GET /health/ready`
* `GET /health`: Liveness probe returning `{"status": "healthy"}`.
* `GET /health/ready`: Readiness probe verifying active database queries, encrypted storage availability, and PyTorch model loading.

---

## 5. Running the Backend & Testing (Windows PowerShell)

### Step 1: Run the Automated 33-Test Suite
```powershell
Set-Location "C:\Users\VIVEK\Desktop\ISC Project"
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

### Step 2: Start the FastAPI Server Locally
```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```
Once started, you can explore the interactive OpenAPI documentation at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc UI**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 6. HTTPS & Secure Deployment Guidelines

### Why Plain HTTP Is Inadequate
Plain HTTP transmits data over cleartext. An eavesdropper on the hospital LAN or Internet can intercept:
1. Patient radiographs (violating HIPAA and GDPR).
2. Bearer access tokens (enabling session hijacking).
3. Diagnostic AI classification outcomes.

### Production HTTPS Deployment Options
For production, the FastAPI application should sit behind a reverse proxy that terminates TLS:

1. **Option A: Nginx Reverse Proxy (Recommended for on-premise hospital servers)**:
   ```nginx
   server {
       listen 443 ssl http2;
       server_name imaging.hospital.internal;

       ssl_certificate /etc/ssl/certs/hospital_bundle.crt;
       ssl_certificate_key /etc/ssl/private/hospital.key;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers HIGH:!aNULL:!MD5;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-Proto https;
       }
   }
   ```
2. **Option B: Uvicorn Direct SSL (For local HTTPS testing)**:
   Generate a local certificate using `mkcert` or `OpenSSL`, then run:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile ./key.pem --ssl-certfile ./cert.pem
   ```

---

## 7. Educational Prototype Notice

> **Mandatory Disclaimer**: This system is developed strictly as an educational prototype for an ISC engineering project. It has not been submitted for FDA 510(k), CE mark, or HIPAA audit certification. It must not be deployed for autonomous clinical diagnosis or unmonitored patient treatment.
