# AI-Based Pneumonia Detection with Secure Storage & Transmission of Medical Data

An educational healthcare software engineering project implementing end-to-end secure medical radiograph storage, deep learning diagnostic screening, and practitioner workflows.

---

## System Requirements: Read Before Setup

These are practical baselines for running the frontend and backend locally with one-image screening. They are not certified hard minimums or multi-user server sizing guarantees.

| Component | CPU-only system | CPU + supported NVIDIA GPU |
|---|---|---|
| Processor | Modern 4-core Intel Core i5 / AMD Ryzen 5 class x86-64 CPU or better | Same; the CPU still handles the API, image decoding, and storage |
| System RAM | 8 GB baseline; 16 GB recommended with browser and development tools | 8 GB baseline; 16 GB recommended |
| Graphics | No dedicated GPU required; Intel/AMD integrated graphics are fine | At least 4 GB dedicated VRAM and a compatible NVIDIA driver; see GPU profiles below |
| Free SSD space | Plan for at least 20 GB for tools, dependencies, and caches | Plan for at least 30 GB for tools, CUDA wheels, and caches |
| Extra storage | Add space for uploaded images and any training dataset | Same |
| Supported installer platforms | Windows 10/11 64-bit or Linux x86-64 | Same |
| Software | Python **3.11**, Node.js **22+**, npm **10+** | Same; NVIDIA driver also required |

The existing **i5-11400H / GTX 1650 4 GB / 16 GB RAM** laptop meets this local-development baseline. A 512 GB SSD is sufficient in capacity; check free space rather than total capacity. The trained checkpoint is required for prediction; the training dataset is not.

### GPU compatibility and automatic CPU fallback

CUDA is NVIDIA technology. This setup accelerates compatible NVIDIA GPUs; AMD/Intel graphics use CPU. Apple Silicon/MPS, ROCm, Windows ARM, Jetson, and other ARM platforms are outside this installer's supported matrix. It does not claim support for every GPU ever released.

| Detected GPU family | Dependency profile | Conservative driver baseline: Windows / Linux |
|---|---|---|
| Turing, Ampere, Ada, Hopper: GTX 16, RTX 20/30/40 and matching workstation/datacenter GPUs; compute capability 7.5, 8.0, 8.6, 8.9, 9.0 | PyTorch `2.5.1+cu124`, torchvision `0.20.1+cu124` | `551.61+` / `550.54.14+` |
| Blackwell: RTX 50 and matching GPUs; compute capability 10.0 or 12.0 | PyTorch `2.7.1+cu128`, torchvision `0.22.1+cu128` | `570.65+` / `570.26+` |
| No NVIDIA GPU, older/unknown architecture, less than 4 GB VRAM, or insufficient driver | PyTorch `2.5.1+cpu`, torchvision `0.20.1+cpu` | No NVIDIA driver needed |

The setup helper checks actual GPU capability, VRAM, and driver rather than assuming any installed graphics card can run CUDA. These versioned profiles follow the [official PyTorch build matrix](https://pytorch.org/get-started/previous-versions/) and conservative toolkit-driver pairings from [NVIDIA CUDA 12.4](https://docs.nvidia.com/cuda/archive/12.4.0/cuda-toolkit-release-notes/index.html) and [CUDA 12.8](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html). Other GPU models in the same supported capability groups can qualify; successful execution is verified after installation. The Blackwell profile is provided for compatibility but has not been physically tested on this GTX 1650 laptop.

**Default behavior:** setup selects a matching CUDA build when a GPU qualifies; otherwise it selects CPU. If CUDA installation or its execution check fails, automatic setup attempts to restore CPU dependencies and reports the failure. At application startup, `PULMOSCAN_DEVICE=auto` tries a real GPU kernel and warms up the actual model; unavailable or unusable CUDA falls back to CPU with a warning. No packages or drivers are installed when starting the app. A runtime out-of-memory error during a later request is not silently retried on another device.

Leave `PULMOSCAN_DEVICE=auto` in `.env` for GPU preference with CPU fallback. Set it to `cpu` to force CPU, or `cuda` to require a GPU and fail clearly instead of falling back. Installing the standalone CUDA Toolkit is unnecessary for these prebuilt PyTorch wheels; a compatible NVIDIA driver is required. A CPU-only PyTorch installation cannot use a GPU until dependencies are changed.

On the GTX 1650 laptop, the CUDA 12.4 profile has been installed and the real checkpoint has completed offline predictions on both `cuda:0` and forced CPU. Other GPU profiles are covered by simulated selection tests; they have not all been physically tested. In containers or virtual machines, the GPU must also be exposed to that environment.

**Training is separate:** 16 GB system RAM is a starting point, with 32 GB more comfortable. A 4 GB GPU may need a small batch such as 2; the existing batch size 16 is not guaranteed to fit. Around 8–12 GB VRAM gives more room. CPU training is supported but slower. Add dataset and checkpoint storage beyond the allowances above. Starting the web app never trains or modifies model weights.

---

## Architecture Overview

```mermaid
graph TD
    A[Next.js 16 Healthcare Frontend\nPulmoScan] -->|HTTPS + In-Memory JWT| B[FastAPI Backend\nREST API]
    B -->|RBAC Policy Check| C{Authorization}
    C -->|Doctor / Radiologist| D[AES-256-GCM Storage Engine\nPX01 Format]
    D -->|Encrypted Ciphertext| E[Encrypted Images Directory\nsecure_data/encrypted_images]
    D -->|Metadata Transaction| F[SQLite Database\nsecure_data/metadata.db]
    B -->|In-Memory Decryption & AEAD Tag Verification| G[DenseNet121 Inference Engine\nCPU or compatible CUDA runtime]
    G -->|Tuned Threshold 0.40| H[Class Scores & Screening Output]
```

---

## Core Capabilities by Phase

1. **Phase 1: Cryptography & Secure Storage**
   - **AES-256-GCM authenticated encryption** with NIST SP 800-38D recommended 96-bit nonces.
   - SHA-256 integrity digest verification and HMAC-SHA256 transmission utilities.
   - Atomic disk writes (`.tmp` to `.enc` replace) preventing partial/truncated files.
   - SQLite metadata tracking with pseudonymous identifiers (`ANON-XXXXX`).

2. **Phase 2: FastAPI Backend & RBAC**
   - Signed JWT authentication (HMAC-SHA256, 30-minute expiration).
   - Salted Bcrypt password hashing (cost factor 12) with constant-time verification.
   - Strict role-based access control (Doctor ownership vs Radiologist institutional review).
   - In-memory DenseNet121 inference using CPU, or CUDA when a compatible GPU-enabled PyTorch installation is available.
   - Liveness (`/health`) and readiness (`/health/ready`) probes.

3. **Phase 3: Next.js Frontend ("PulmoScan")**
   - Modern App Router, React 19, TypeScript, and Tailwind CSS.
   - In-memory token management in React state (zero storage in `localStorage` or cookies).
   - Practitioner dashboard, drag-and-drop X-ray upload, real-time preview cleanup.
   - Repository browsing with search and status filtering.
   - Probability visualization and clinical decision support disclaimers.

4. **Phase 4: Security Hardening & End-to-End Validation**
   - Production configuration validation preventing insecure default keys.
   - Thread-safe sliding-window rate limiting on login (10 req/min) and inference (30 req/min).
   - Pillow decompression bomb safeguards (`MAX_IMAGE_PIXELS = 16.7M`).
   - OWASP security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options).
   - Live end-to-end integration test suite and key recovery verification.

5. **Phase 5: Deployment, Release Preparation & Benchmarking**
   - Earlier project benchmark reports include CPU and CUDA inference measurements; these are not timing guarantees for other machines. See the [model and hardware guide](docs/MODEL_AND_HARDWARE.md) for the verified local setup and measurement scope.
   - Multi-stage Docker containerization and Docker Compose orchestration with persistent storage.
   - Graceful hardware fallback from CUDA to CPU.
   - Operational staging deployment guide, disaster recovery runbook, and release checklist.

---

## Project Documentation Index

- [Local Setup and Turborepo Commands](docs/LOCAL_SETUP.md)
- [How the Model Works, CPU/GPU Selection & Hardware Requirements](docs/MODEL_AND_HARDWARE.md)
- [Complete User Guide, Page Map & RBAC Guide](USER_GUIDE_AND_ACCESS_CONTROL.md)
- [Security Audit Report](docs/SECURITY_AUDIT.md)
- [End-to-End Testing Report](docs/END_TO_END_TESTING.md)
- [Deployment Preparation & Operations Guide](docs/DEPLOYMENT.md)
- [API Documentation](docs/API_DOCUMENTATION.md)
- [Secure Storage Cryptography Specification](docs/SECURE_STORAGE.md)
- [Frontend Documentation](frontend/README.md)
- [Frontend Appearance and UX Review](docs/FRONTEND_UX.md)

---

## Local Setup and Running the Application

Follow the [complete setup guide](docs/LOCAL_SETUP.md) for prerequisites, creating `.venv`, installing Python and Node dependencies, and generating local configuration. The same steps are included in [section 10 of the user guide](USER_GUIDE_AND_ACCESS_CONTROL.md#10-local-setup--execution-guide-windows-powershell).

From the project root, create an environment if needed, install dependencies for the detected hardware, and create local configuration:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
# Read-only preview of the selected CPU/CUDA dependency profile:
.\.venv\Scripts\python.exe scripts/setup_compute.py
# Apply that profile and install the shared backend dependencies:
.\.venv\Scripts\python.exe scripts/setup_compute.py --install
npm.cmd ci
npm.cmd ci --prefix frontend
.\.venv\Scripts\python.exe scripts/setup_local_env.py
npm.cmd run dev:check
# Optional offline checkpoint test; does not start an API or frontend:
.\.venv\Scripts\python.exe scripts/check_compute.py --model
```

If `.venv` already exists, skip creating it. Keep your existing `.env` so stored scans remain decryptable. Run `setup_compute.py --install` once to replace an existing CPU-only torch build with CUDA on a qualifying GPU, including the GTX 1650. The installer only modifies the project's `.venv`. Use `--device cpu --install` for CPU dependencies, or `--device cuda --install` for strict GPU setup. Installation never changes encryption keys, trains the model, or starts servers. Stop any manually running backend before replacing its native Python packages.

These commands use Windows PowerShell. On supported Linux x86-64 systems, create the environment with `python3.11 -m venv .venv`, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`, and use `npm` in place of `npm.cmd`.

For later runs, dependency installation is unnecessary unless rebuilding or changing the environment. `scripts/check_compute.py` reports the installed torch build, packaged CUDA runtime, and actual selected device. The offline `--model` test uses a synthetic image to verify execution, not diagnostic accuracy.

Then start both services manually with one command:

```powershell
npm.cmd run dev
```

Turborepo checks setup once, then starts FastAPI and Next.js concurrently with labelled logs. Press **Ctrl+C** to stop both. The launcher uses this project's `.venv` directly; activating it is optional.

| Interface | URL |
|---|---|
| Staff login | http://localhost:3000/login/staff |
| Radiologist login | http://localhost:3000/login/radiologist |
| Backend readiness | http://127.0.0.1:8000/health/ready |
| API documentation | http://127.0.0.1:8000/docs |

Use `npm.cmd run dev:frontend` or `npm.cmd run dev:backend` to launch one service. `npm.cmd run dev:plan` shows Turbo's task plan without executing it.

### Automated Checks

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dev_setup.py -v
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
```

The full backend suite remains available via `.\.venv\Scripts\python.exe -m pytest tests/ -v`. The live workflow check requires an already running backend: `.\.venv\Scripts\python.exe tests/e2e_live_verification.py`.

---

## Clinical Disclaimer

This software is an educational prototype developed for academic demonstration. It is **not** an FDA-cleared diagnostic device and should never replace qualified clinical radiological interpretation.
