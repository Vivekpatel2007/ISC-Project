# Local Setup and Turborepo Development Commands

These instructions apply to a fresh checkout on **Windows x86-64 or Linux/WSL x86-64**. They contain no developer-specific directories or required GPU model. All commands run from the repository root, containing `package.json`, `requirements.txt`, `src/` and `frontend/`.

The source and saved checkpoint are needed to run the app. A training dataset, Kaggle account and new training run are not required. See [requirements and GPU eligibility](../README.md#system-requirements-read-before-setup) first. macOS/MPS, ARM, ROCm and Jetson are not covered by this installer.

## 1. Prerequisites

Install Python **3.11**, Node.js **22.13+ within 22.x, 24.x, or 26+**, and npm **10+**. Older 22.x releases and Node 23/25 do not satisfy the locked frontend test dependencies. Package engines declare the same range. Make sure the selected binaries are on PATH.

Check versions:

```powershell
# Windows PowerShell; the Python launcher must have Python 3.11 installed.
py -3.11 --version
node --version
npm.cmd --version
```

```bash
# Linux / WSL
python3.11 --version
node --version
npm --version
```

Clone/download the source first, then change into its root using your own checkout location. Paths below are relative to that directory. Turbo and project Python libraries are installed locally rather than globally.

## 2. Create the project environment

Skip creation if this checkout already has the correct `.venv`. Do not replace an existing environment casually while its backend is running.

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

```bash
# Linux / WSL
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
```

Direct interpreter paths make activation optional and avoid changing PowerShell execution policy. If desired, activate with `.\.venv\Scripts\Activate.ps1` on PowerShell or `source .venv/bin/activate` on Bash, then use `python` for that environment. If activation is blocked, keep using the direct paths shown here.

## 3. Install Python dependencies

Preview the hardware plan, then apply it:

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe scripts/setup_compute.py
.\.venv\Scripts\python.exe scripts/setup_compute.py --install
```

```bash
# Linux / WSL
.venv/bin/python scripts/setup_compute.py
.venv/bin/python scripts/setup_compute.py --install
```

The first command is read-only. `--install` installs the qualifying torch/torchvision CPU/CUDA pair, **then installs `requirements.txt`** using compatibility constraints, runs `pip check` and verifies device execution. It only installs into the project's Python 3.11 `.venv`. CUDA wheels are large; allow sufficient disk space and download time.

| Option added to the command | Behavior |
| --- | --- |
| `--device auto --install` | Default: qualifying CUDA profile, with CPU recovery if CUDA install/execution fails |
| `--device cpu --install` | Deliberately install CPU packages |
| `--device cuda --install` | Require qualifying CUDA and fail clearly rather than silently switch |

There is no requirement to own a particular GPU. GPU selection uses capability, memory and driver checks. Drivers are not installed by this project. The standalone CUDA Toolkit is not required for its prebuilt wheels.

### Dependency-file roles

| File | Purpose |
| --- | --- |
| `requirements.txt` | Shared direct API/model/training/test libraries |
| `constraints-local.txt` | Shared backend compatibility pins |
| `requirements/compute-cpu.txt` | Exact CPU torch/torchvision pair |
| `requirements/compute-cu126.txt` | Exact supported CUDA 12.6 pair |
| `requirements/compute-cu130.txt` | Exact supported CUDA 13.0 pair |

The shared file excludes hardware-dependent torch packages. It is not a complete fresh installation by itself. If manually installing a profile, use its matching official index, then shared dependencies. For example, CPU only:

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r requirements/compute-cpu.txt --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints-local.txt
.\.venv\Scripts\python.exe -m pip check
```

```bash
# Linux / WSL
.venv/bin/python -m pip install -r requirements/compute-cpu.txt --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r requirements.txt -c constraints-local.txt
.venv/bin/python -m pip check
```

For manual CUDA installation, use the qualifying `compute-cu126.txt` with `/cu126` or `compute-cu130.txt` with `/cu130`, followed by shared requirements. The automatic helper is preferred because it checks eligibility. To reinstall shared libraries later, run only the second and third commands without replacing the selected compute pair.

## 4. Install JavaScript dependencies

```powershell
# Windows PowerShell
npm.cmd ci
npm.cmd ci --prefix frontend
```

```bash
# Linux / WSL
npm ci
npm ci --prefix frontend
```

Both lockfiles matter: root dependencies provide Turbo and frontend dependencies provide Next.js/UI/test tooling. `npm ci` uses their committed versions. Neither command starts the services. Use a supported Node version before installation.

## 5. Create configuration and check the model

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe scripts/setup_local_env.py
Test-Path .\models\densenet121_pneumonia_best.pth
```

```bash
# Linux / WSL
.venv/bin/python scripts/setup_local_env.py
ls -lh models/densenet121_pneumonia_best.pth
```

The helper creates missing `.env` and `frontend/.env.local`, generates separate encryption/JWT secrets and prints no keys. Existing files are preserved. `.env` follows the `.env.example` settings; the frontend's public API URL defaults to `http://127.0.0.1:8000`.

**Preserve existing encryption keys when retaining scans.** Creating new keys is not a repair for unreadable old images. Environment files and medical storage are ignored by Git.

The bundled original checkpoint is required at the configured path. If missing, obtain a trusted project artifact or deliberately configure a compatible finalized DenseNet checkpoint via `MODEL_CHECKPOINT_PATH`; do not rename an arbitrary candidate. Optional candidates under `data/experiments/` are ignored and do not accompany a code-only clone. [Model inventory](PATIENT_WORKFLOW_AND_STORAGE.md).

## 6. Verify without starting servers

```powershell
# Windows PowerShell
npm.cmd run dev:check
.\.venv\Scripts\python.exe scripts/check_compute.py --model
```

```bash
# Linux / WSL
npm run dev:check
.venv/bin/python scripts/check_compute.py --model
```

Preflight checks imports, configuration/key formats, checkpoint existence and a small compute kernel. It does not load model weights or initialize the app database. The optional `--model` check loads the checkpoint and runs a synthetic image offline; it verifies execution, not medical accuracy, and writes no patient predictions.

## 7. Start manually

```powershell
# Windows PowerShell
npm.cmd run dev
```

```bash
# Linux / WSL
npm run dev
```

Turborepo runs preflight once, then launches FastAPI and Next.js with labelled logs. Backend changes under `src/` trigger reload; Next.js handles frontend development refresh. Ctrl+C stops both. A later normal launch needs no reinstall or new environment/configuration generation.

| Service | URL |
| --- | --- |
| Staff login | http://localhost:3000/login/staff |
| Radiologist login | http://localhost:3000/login/radiologist |
| API docs | http://127.0.0.1:8000/docs |
| Readiness | http://127.0.0.1:8000/health/ready |

Wait for backend startup completion. Demo accounts, if enabled, are seeded only when the users table is empty: `doctor1` / `DoctorPassword123!` for staff and `radiologist1` / `RadioPassword123!` for radiologists. Existing/renamed accounts persist; these public passwords are not production credentials. Patients have no logins.

API docs accept a bearer token obtained by JSON `POST /auth/login`. Local development is loopback HTTP; HTTPS/TLS is a separate remote-deployment requirement.

## Development and verification commands

The examples below use `npm`, which works on Linux and usual shells; use `npm.cmd` in PowerShell if its `npm.ps1` shim is blocked.

| Command from root | Action |
| --- | --- |
| `npm run dev` | Preflight and both services |
| `npm run dev:check` | Read-only preflight |
| `npm run dev:plan` | Print Turbo plan without executing tasks |
| `npm run dev:frontend` | Frontend only; run preflight first |
| `npm run dev:backend` | Backend only using project `.venv`; run preflight first |
| `npm --prefix frontend test` | Frontend test suite |
| `npm --prefix frontend run lint` | Frontend lint |
| `npm --prefix frontend run build` | Production build; does not start a server |

Run backend tests with `.\.venv\Scripts\python.exe -m pytest -q` on Windows or `.venv/bin/python -m pytest -q` on Linux. They use isolated temporary storage. Live end-to-end verification is separate and requires services already started manually.

The Turbo service tasks are persistent/uncached and depend on preflight when launched through `npm run dev`. The direct one-service scripts do not themselves run the shared preflight. Turbo orchestrates processes; Next.js Turbopack compiles frontend code.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Python 3.11 unavailable | Install that interpreter; confirm the specific launcher command before creating `.venv`. |
| Missing `venv` support on Linux | Install your distribution's Python 3.11 venv support, then recreate only the intended project environment. |
| Unsupported Node/engine warning | Select Node 22.13+ within 22.x, 24.x or 26+, reopen the shell and rerun both `npm ci` commands. |
| `npm.ps1` blocked | Use `npm.cmd`; no security-policy change is required. |
| Missing imports | Install compute and shared requirements with the project interpreter; check `pip check`. |
| Missing configuration | Run `setup_local_env.py`; it will not overwrite existing files. |
| Existing invalid keys | Restore/correct the intended configuration; preserve keys matching retained scans. |
| GPU present but CPU selected | Check driver/capability/VRAM eligibility, CUDA-enabled wheel, `PULMOSCAN_DEVICE` and `CUDA_VISIBLE_DEVICES`. |
| Windows blocks a native DLL | Capture the exact error and repair the trusted installation or consult the device administrator. Changing CPU/GPU profiles alone is not an established fix; do not disable Application Control. |
| Ports 3000/8000 occupied | Stop your previous development instances before relaunching; do not kill unrelated processes blindly. |
| New upload gives an unexpected class | A valid image is not necessarily a suitable X-ray. Check model limitations; do not edit thresholds to make a demonstration label look correct. |
| Dataset hash failure during optional training | Stop and investigate the source; do not overwrite hashes to accept changed data. |

For later updates, reinstall Node dependencies when their lockfiles change and Python dependencies when their pins change. Back up needed keys, medical storage and ignored experiment artifacts. Keep dataset/training instructions separate from app installation.
