# Phase 1: Secure Medical Image Storage & Cryptography Documentation
**Project**: AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data  
**Module**: `src/security`  
**Standard**: NIST SP 800-38D (AES-GCM), FIPS 180-4 (SHA-256), HIPAA Technical Safeguards (45 CFR § 164.312)  

---

## 1. System Architecture & Data Flow

The Secure Medical Image Storage module guarantees confidentiality, authenticity, and integrity for patient chest radiographs at rest and during retrieval:

```
[ Incoming Chest X-Ray Image ]
           │
           ▼
[ In-Memory Pre-flight Validation ]
           │ (Enforces size limit, checks non-empty)
           ▼
[ Compute SHA-256 Original Digest ] ─────────────────────────┐
           │                                                 │
           ▼                                                 │
[ Generate Fresh 96-bit Nonce ]                              │
           │                                                 │
           ▼                                                 │
[ AES-256-GCM Encrypt & Authenticate ]                       │
           │                                                 │
           ▼                                                 │
[ Package PX01 Binary Container ]                            │
  (Magic Header + Version + Nonce + Ciphertext + Tag)        │
           │                                                 │
           ▼                                                 │
[ Atomic File Write (.tmp ➔ .enc) ]                          │
           │                                                 │
           ▼                                                 │
[ Record Metadata in SQLite ] <──────────────────────────────┘
  (scan_id, patient_id, filename, sha256, timestamp)
```

### Retrieval & Verification Data Flow:
```
[ Request scan_id ] ──> [ Query SQLite Metadata ]
                                 │
                                 ▼
                     [ Locate Encrypted File ]
                                 │
                                 ▼
                     [ In-Memory Decryption ]
                     (Verifies AES-256-GCM 128-bit tag)
                                 │
                                 ▼ (If tag fails: AuthenticationError)
                     [ In-Memory SHA-256 Check ]
                     (Verifies plaintext against registry)
                                 │
                                 ▼ (If mismatch: IntegrityVerificationError)
                     [ Return Plaintext Bytes in Memory ]
                     (Zero plaintext written to disk!)
```

---

## 2. Cryptographic Specifications & Container Format

### 2.1 The PX01 Binary Container Format
Encrypted images are stored on disk in the custom binary container format **`PX01`**:

| Byte Offset | Length | Field Name | Description |
|---|---|---|---|
| `0x00 - 0x03` | 4 bytes | `MAGIC_HEADER` | ASCII string `b"PX01"` identifying valid encrypted containers. |
| `0x04` | 1 byte | `VERSION` | Container format version byte (`0x01`). |
| `0x05 - 0x10` | 12 bytes | `NONCE` | Cryptographically random 96-bit initialization vector generated per encryption. |
| `0x11 - End-16`| Variable | `CIPHERTEXT` | AES-256-GCM encrypted image payload. |
| `End-16 - End` | 16 bytes | `AUTH_TAG` | 128-bit Galois/Counter Mode authentication tag. |

* **Minimum valid container length**: $4 + 1 + 12 + 0 + 16 = 33$ bytes.

### 2.2 Roles of Cryptographic Primitives
1. **AES-256-GCM (Authenticated Encryption)**:
   - Provides **confidentiality** (rendering medical scans unintelligible to unauthorized parties).
   - Provides **integrity & authenticity** (the 128-bit tag detects any byte manipulation, truncated files, or wrong keys).
   - **Nonce Uniqueness**: A fresh 96-bit nonce is generated using `os.urandom(12)` for *every single encryption*. Nonces are never reused.
2. **SHA-256 (Pre-Encryption Digest)**:
   - Records the cryptographic digest of the raw image before encryption.
   - Used upon retrieval to verify that in-memory deserialization, decryption, and image decoding suffered no corruption or bit rot.
   - *Security Note*: Unkeyed SHA-256 alone cannot defend against an attacker who has write access to both storage and database. True defense against tampering is provided by the **AES-GCM authentication tag**.

---

## 3. Key Management Policies

1. **Separation of Keys and Data**:
   - The encryption key is **NEVER** stored inside the encrypted container, alongside `.enc` files, or in the SQLite database.
2. **Zero Plaintext Key Exposure**:
   - Keys are never printed to console streams, logged, or included in error tracebacks.
   - `.gitignore` is configured to prevent accidental commits of `.env`, `*.key`, or `secrets/`.
3. **Key Recovery Limitations**:
   - AES-256 is an information-theoretically secure symmetric cipher with no backdoor.
   - **CRITICAL**: If the encryption key is lost, encrypted medical images **cannot be recovered**. Regular, encrypted offline backups of the master key are essential.
4. **Production Recommendation**:
   - In production healthcare environments, environment variables should be replaced with a dedicated **Hardware Security Module (HSM)**, OS-level credential vault (e.g., Windows DPAPI / Credential Manager), or managed Cloud KMS (AWS KMS, Azure Key Vault, HashiCorp Vault).

---

## 4. Environment Setup (Windows PowerShell)

### Step 1: Activate Virtual Environment
```powershell
Set-Location "C:\Users\VIVEK\Desktop\ISC Project"
.\.venv\Scripts\Activate.ps1
```

### Step 2: Generate an Encryption Key
Run the Python key generator helper:
```powershell
.\.venv\Scripts\python.exe -c "from src.security.key_manager import generate_key, key_to_base64; print(key_to_base64(generate_key()))"
```

### Step 3: Configure `.env`
Copy `.env.example` to `.env` and paste your generated key:
```powershell
Copy-Item .env.example .env
```
Inside `.env`:
```ini
IMAGE_ENCRYPTION_KEY=<your_generated_base64_key_here>
SECURE_STORAGE_DIR=secure_data/encrypted_images
METADATA_DB_PATH=secure_data/metadata.db
MAX_IMAGE_SIZE_BYTES=20971520
```

---

## 5. Usage Examples

### Encrypting and Storing a Medical Image:
```python
from pathlib import Path
from src.security import SecureImageStorage, load_key_from_env

# 1. Load key from .env
key = load_key_from_env()

# 2. Initialize storage engine
storage = SecureImageStorage(
    key=key,
    storage_dir="secure_data/encrypted_images",
    db_path="secure_data/metadata.db"
)

# 3. Read image bytes
raw_bytes = Path("data/model_data/test/NORMAL/IM-0001-0001.jpeg").read_bytes()

# 4. Store image with pseudonymous patient ID
metadata = storage.store_image(raw_bytes, patient_id="ANON-10842")

print("Stored Scan ID:", metadata["scan_id"])
print("Encrypted File:", metadata["encrypted_filename"])
print("Original SHA-256:", metadata["original_sha256"])
```

### Retrieving and Decrypting in Memory:
```python
# Retrieve decrypted bytes in memory (never written to disk)
recovered_bytes, record = storage.retrieve_image(metadata["scan_id"])

# Verify exact match
assert len(recovered_bytes) == len(raw_bytes)
print("Decryption and tag verification successful!")
```

### Verifying Scan Integrity:
```python
# Check ciphertext authentication and hash integrity
report = storage.verify_scan_integrity(metadata["scan_id"])
print(report)
# Output: {'scan_id': '...', 'status': 'VALID', 'authentication': 'VERIFIED (AES-256-GCM)', ...}
```

---

## 6. Running Automated Tests & Demonstration

### Run the 18 Security Unit Tests:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_secure_storage.py -v
```

### Run the Interactive Live Demonstration:
```powershell
.\.venv\Scripts\python.exe demo_secure_storage.py
```

---

## 7. Integration with DenseNet121 Inference Pipeline

In Phase 2 / Phase 3, the web application will connect the secure storage module directly with our retrained DenseNet121 model ([models/densenet121_pneumonia_best.pth](file:///C:/Users/VIVEK/Desktop/ISC%20Project/models/densenet121_pneumonia_best.pth)):

```python
import io
import torch
from PIL import Image
from torchvision import models, transforms
from src.security import SecureImageStorage, load_key_from_env

# 1. Retrieve encrypted scan in-memory
storage = SecureImageStorage(key=load_key_from_env())
decrypted_bytes, record = storage.retrieve_image(scan_id="<target_scan_id>")

# 2. Decode in-memory without disk write
pil_image = Image.open(io.BytesIO(decrypted_bytes)).convert("RGB")

# 3. Load trained model & inference preprocessing
ckpt = torch.load("models/densenet121_pneumonia_best.pth", map_location="cpu", weights_only=False)
transform = transforms.Compose([
    transforms.Grayscale(num_output_channels=3),
    transforms.Resize((ckpt["image_size"], ckpt["image_size"])),
    transforms.ToTensor(),
    transforms.Normalize(ckpt["normalization"]["mean"], ckpt["normalization"]["std"])
])

tensor = transform(pil_image).unsqueeze(0)
# (Run model inference and update database record with prediction)
```

---

## 8. Security Limitations & Phase 2 Outlook

- **Local SQLite Scope**: SQLite is ideal for single-node local development. For multi-user hospital deployments, migration to PostgreSQL with encrypted connections (TLS) and disk volume encryption is recommended.
- **Key Rotation**: Future iterations can implement key-versioning in the container header to support seamless cryptographic key rotation.
- **Role-Based Access Control**: Access control is currently at the storage API layer. Phase 2 will implement authenticated endpoints with JWT tokens to verify doctor/radiologist authorization before scan retrieval.
