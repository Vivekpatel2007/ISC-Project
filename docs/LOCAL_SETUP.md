# Local Setup and Turborepo Development Commands

Run all commands from the project root: the folder containing `src/`, `frontend/`, and the root `package.json`. These instructions use Windows PowerShell. If your existing `.venv` already runs the app, keep it and skip steps 1 and 2.

## 1. Install prerequisites and create the environment

Install [Python 3.11](https://www.python.org/downloads/) and [Node.js](https://nodejs.org/en/download/) version 22 or newer, with npm 10 or newer. Python 3.11 is the baseline for the CPU packages below.

```powershell
py -3.11 --version
node --version
npm.cmd --version
py -3.11 -m venv .venv
```

The launcher selects this project's `.venv` directly. Activating it with `Activate.ps1` is optional; these commands work without changing PowerShell's execution policy.

## 2. Install Python dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints-local.txt
.\.venv\Scripts\python.exe -m pip check
```

Install the CPU wheels first, then the requirements with `constraints-local.txt`. These constraints retain the PyTorch, FastAPI, and Pydantic versions that worked on this Windows setup after Application Control blocked newer native libraries. Inference uses CPU. GPU environments can use a separately validated dependency set. See [PyTorch's official version-specific commands](https://pytorch.org/get-started/previous-versions/).

## 3. Install Turborepo and frontend dependencies

```powershell
npm.cmd ci
npm.cmd ci --prefix frontend
```

The root lockfile installs the pinned Turborepo version. The frontend keeps its existing lockfile and dependencies. These commands use the project's local Turbo installation.

## 4. Create local configuration

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_env.py
```

The helper creates missing `.env` and `frontend/.env.local` files. The backend receives independent random encryption and JWT keys; the frontend points to `http://127.0.0.1:8000`. Existing files are preserved byte for byte, and keys are not printed. Keep the existing `.env` when retaining stored scans so they remain decryptable. Both environment files are ignored by Git.

Confirm that the trained checkpoint exists:

```powershell
Test-Path .\models\densenet121_pneumonia_best.pth
```

If this returns `False`, obtain the trained checkpoint from the project owner and place it at that path, or configure `MODEL_CHECKPOINT_PATH` in `.env`. The checkpoint is needed to start the API. The training dataset is not needed to run the web app.

## 5. Verify setup without starting servers

```powershell
npm.cmd run dev:check
```

This checks configuration files, backend imports, key formats, and the checkpoint path. It does not start a server, load model weights, or initialize the application database.

## 6. Start both services with one command

Run this manually from the project root:

```powershell
npm.cmd run dev
```

Turborepo runs the setup check once, then starts FastAPI and Next.js concurrently with labelled logs in the same terminal. FastAPI reloads when files in `src/` change; Next.js provides its normal development refresh. Press **Ctrl+C** in this terminal to stop both.

| Service | URL |
|---|---|
| Staff login | http://localhost:3000/login/staff |
| Radiologist login | http://localhost:3000/login/radiologist |
| Backend readiness | http://127.0.0.1:8000/health/ready |
| API documentation | http://127.0.0.1:8000/docs |

Use `doctor1` / `DoctorPassword123!` at Staff Login, or `radiologist1` / `RadioPassword123!` at Radiologist Login. Enter credentials manually. The last portal is remembered; credentials and access tokens are not persisted by the app.

After starting the app, check readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

Wait for `Application startup complete` in the backend log and a `ready` response before signing in.

## Available development commands

| Command from project root | Action |
|---|---|
| `npm.cmd run dev` | Check setup, then run both services |
| `npm.cmd run dev:check` | Validate setup without starting services |
| `npm.cmd run dev:plan` | Print Turbo's task plan without executing tasks |
| `npm.cmd run dev:frontend` | Start only the frontend |
| `npm.cmd run dev:backend` | Start only the backend using `.venv` |

Both service tasks depend on the same setup check. They are persistent and uncached. `--env-mode=loose` preserves environment overrides already set in the terminal, while each app loads its own local environment file. This uses [Turborepo's single-package task orchestration](https://turborepo.dev/docs/guides/single-package-workspaces); the source folders retain their existing structure. Turborepo coordinates processes; Next.js's Turbopack compiles the frontend.

## Automated checks

These checks do not start development servers:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dev_setup.py -v
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
```

The full backend suite is `.\.venv\Scripts\python.exe -m pytest tests/ -v`. Live end-to-end verification requires an already running backend: `.\.venv\Scripts\python.exe tests/e2e_live_verification.py`.

## Troubleshooting

| Symptom | Action |
|---|---|
| `turbo` is not recognized | Run `npm.cmd ci` in the project root. |
| Missing `.venv` or Python imports | Complete steps 1 and 2; the launcher selects the project's `.venv`. |
| Missing configuration files | Run the setup helper as shown in step 4. |
| Invalid existing keys | Correct the existing `.env` using its original valid keys; setup deliberately preserves the file. |
| Windows blocks a native library | Use the CPU install and constraints in step 2, then rerun `dev:check`. |
| Port 3000 or 8000 is in use | Stop previously running development instances before using the combined command. |
| `npm.ps1` is blocked by PowerShell policy | Use `npm.cmd`, as shown throughout this guide. |

For later checkouts, use `npm.cmd ci` and `npm.cmd ci --prefix frontend` when their respective lockfiles change. Retain the existing `.env` and `.venv` unless intentionally rebuilding the environment.
