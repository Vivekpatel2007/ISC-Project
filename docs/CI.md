# Continuous integration

The [CI workflow](../.github/workflows/ci.yml) runs in GitHub Actions on every push, every pull request and manual dispatch. After pushing the workflow, open the repository's **Actions > CI** page to see runs and logs. The **Run workflow** button is available once the workflow is on the default branch. GitHub Actions must be enabled for the repository.

## Checks

Two jobs run independently on Ubuntu 24.04:

| Job | Runtime | Checks |
| --- | --- | --- |
| Backend tests (Python 3.11, CPU) | Python 3.11 and the pinned CPU PyTorch profile | Dependency compatibility, CPU-only installation, full `pytest` suite |
| Frontend tests, lint and build (Node 24) | Node.js 24 and committed npm lockfiles | Root Turborepo dry run, ESLint, Vitest, production build with TypeScript checking |

Both jobs must pass for the workflow to pass. New commits on the same branch or pull request cancel an older in-progress run. Dependency downloads are cached; each run still installs dependencies and executes the checks. Actions are pinned to verified release commit hashes; update their hashes and version comments together when upgrading them.

The backend installs `requirements/compute-cpu.txt` from the official PyTorch CPU index, then `requirements.txt` with both the shared and CPU constraints. This avoids downloading CUDA libraries or requiring a GPU. Local installation continues to use the hardware-aware setup guide.

No repository secrets, `.env` files, dataset downloads or Kaggle account are required. The bundled, tracked DenseNet checkpoint is used by model tests. `tests/conftest.py` creates a temporary database, encrypted-image directory and random test keys before importing the API; those files are cleaned up afterward. Frontend tests mock API calls, and its build uses a loopback API URL without contacting a running backend.

CI does not run application servers, live end-to-end checks, dataset evaluation, GPU checks or production model training. Some unit tests exercise tiny synthetic training cases. A green run verifies the covered software behavior; it does not measure medical accuracy or validate a clinical deployment.

## Reproduce checks locally

Complete the [local setup](LOCAL_SETUP.md) first. From the repository root, use the Python command for your operating system:

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

```bash
# Linux / WSL
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
```

The Node commands are the same on both platforms (`npm.cmd` can be used in PowerShell if its execution policy blocks `npm.ps1`):

```bash
npm ci
npm ci --prefix frontend
npm run dev:plan
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

`npm ci` reinstalls dependencies using the lockfiles. The Turborepo command only prints the execution plan. These checks do not require starting the frontend or backend. The local backend tests force CPU inference even if your installed PyTorch build supports CUDA; CI additionally verifies a CPU-only installation.

## Review and merge

A failing run shows the failed job and step under **Actions > CI**. Fix the issue locally and push another commit to rerun the checks. Fork pull requests may need a maintainer to approve their first workflow run, depending on repository settings.

To enforce passing checks before merging, configure a branch ruleset or branch protection in GitHub after the first run, and require both job names listed above. Adding the workflow alone reports failures but does not prevent merging. This change does not configure deployment or modify repository settings.
