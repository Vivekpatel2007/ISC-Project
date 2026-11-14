# Final application review — 13 November 2026

This review keeps the existing classification model and optional Grad-CAM scope. It does not add finding detection, retrain weights, tune the decision threshold, promote a Kaggle candidate, start app servers or commit changes.

## Corrections

- **Session expiry:** authenticated API 401 responses clear the matching in-memory session and its mounted private page state. Responses for an older token cannot sign out a replacement session. Idle sessions also expire using the server's reported lifetime, with focus/visibility checks after a suspended tab resumes. A transient profile-fetch network failure no longer signs out a valid session.
- **Request feedback and privacy:** cancelled fetches retain their cancellation error; malformed JSON is distinguished from a connection failure. API fetches use `cache: no-store`; backend responses set `Cache-Control: no-store, private`, including authentication and scan metadata. Validation errors return only their type, location and message, omitting Pydantic's rejected input values so passwords are not echoed.
- **Authentication:** tokens require expiry, issuance, not-before and complete account identity/version claims. Invalid claim types produce 401. The old alternate role helper now delegates to the same authenticated, database-backed role check as the main routes. Unknown-user checks use a valid cost-12 bcrypt dummy hash. Password hashing explicitly rejects inputs exceeding bcrypt's 72 UTF-8-byte limit. OpenAPI now describes bearer-token authorization correctly: call the JSON login endpoint, then paste its access token into **Authorize**; it no longer advertises an unsupported OAuth2 password form.
- **Uploads:** decoding, encryption and SQLite work now run in the worker pool. A streaming body limit rejects oversized declared and chunked request bodies before full multipart consumption; the total allowance is the configured image limit plus 64 KiB of form overhead. The handler still enforces the exact image-byte limit. Storage failures return a sanitized retryable response rather than internal file/error details.
- **Resource use:** rate limiting bounds tracked client keys, removes idle entries and rounds retry times upward. This is a per-process limiter, not a distributed deployment design.
- **Model preprocessing:** valid numeric normalization metadata is converted to floating-point values before constructing transforms. Previously, numeric strings could pass validation and then fail during image preprocessing.
- **Tooling:** Vitest uses an explicit ESM config, removing its configuration-format warning. A narrow `minimatch` override fixes the transitive TypeScript-eslint tooling advisory; lint and frontend tests verify compatibility.

The upload body limit reduces unbounded ingestion; it does **not** establish zero plaintext disk use. Permitted multipart images may still spool temporarily before encryption. Existing stored images are encrypted, and prediction/explanation decrypt in memory.

## Runtime updates

The shared API pins are FastAPI **0.162.6**, Starlette **1.10.0**, and the existing compatible Pydantic **2.10.6**. Local compute profiles pair PyTorch **2.14.1** with torchvision **0.29.1**: `cpu`, `cu126` for documented Turing–Hopper GPUs, and `cu130` for documented Blackwell GPUs. Old `cu124`/`cu128` install profiles were replaced; driver baselines and commands in README.md were updated.

The older PyTorch loader is affected even with `weights_only=True`; see [the PyTorch advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p). The selected matched builds are listed in [PyTorch's official version matrix](https://pytorch.org/get-started/previous-versions/). Starlette's older multipart implementation has a published [upload-spooling advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-2c2j-9gv5-cj73). Version-specific checks against the public OSV database were used to select replacements; absence of listed advisories is not proof of security.

Checkpoint files remain trusted local artifacts. The app does not accept model uploads. Keep the artifact fingerprints and avoid loading unfamiliar `.pth` files. The historical Kaggle experiment results/runtime records remain unchanged; old resume states must not be represented as exactly reproducible under a different runtime. No new Kaggle run is required for this application update.

## Verification

All final checks passed:

| Check | Result |
| --- | --- |
| Full backend suite, updated runtime | **232 passed** |
| Frontend suite | **106 passed** |
| Frontend lint / production build | Passed |
| `npm.cmd run dev:check` | Passed; actual selected device `cuda:0` |
| `pip check` | No broken requirements |
| OSV lookup of all 57 installed Python packages | No known advisories returned at review time |
| Frontend `npm audit`, including tooling | Zero known vulnerabilities |
| Protected-file fingerprints | All five settings/storage/checkpoint files unchanged |

The local environment now runs **torch 2.14.1+cu126**, **torchvision 0.29.1+cu126**, FastAPI 0.162.6 and Starlette 1.10.0. Pip was updated from 23.2.1 to 26.3 after its old version was flagged by the dependency lookup. The 2.42 GiB PyTorch wheel was verified against the SHA-256 in the official PyTorch index before installation. CPU-only and Blackwell installer profiles are covered by selection tests; the actual hardware execution check used this laptop's GTX 1650.

Eight offline checks used the original and Kaggle v2 DenseNet checkpoints, two already-reviewed dataset images, and CPU/CUDA execution. Predictions and explanation scores agreed at API rounding precision; in-memory model state stayed unchanged. The original model's CPU scores matched the pre-update CPU reference at returned precision, and its selected classes stayed unchanged on both devices. CUDA float16 scores differed from the old CPU float32 reference by at most **0.0021** (0.21 percentage points); this comparison does not isolate a runtime-version effect or promise bit-identical devices. These two cases cannot establish equivalence for every image, improved accuracy or clinical reliability.

The remaining test warnings are Starlette's supported-but-deprecated `httpx` test-client adapter and the intentionally triggered Pillow decompression-bomb warning. Deprecated HTTP status constant names in project code were updated. The former Vite configuration-format warning is resolved. No browser session was driven by the assistant; the manual application review remains yours.

Review evidence is kept under ignored `data/review/final_20261113/`, including the pre-update protected-file hashes and two fixed-image CPU inference references. These are runtime regression checks, not a new accuracy benchmark or independent validation. Tests use temporary storage and synthetic records; application scans must remain untouched.

The optional legacy `src/evaluate_test.py` script has a separate Windows Application Control block on a scikit-learn native DLL. Its installed native files match the official PyPI wheel, so reinstalling identical bytes is not an established fix. No Windows security policy was disabled or bypassed. Current inference, Grad-CAM and the maintained manifest-based evaluation path do not import that legacy evaluator.

## Manual review before committing

Start the application yourself with `npm.cmd run dev`. Review login/logout and the chosen portal, upload a permitted X-ray, run screening, generate an explanation, inspect Original/Heatmap and enlarged views, check patient follow-up and profile edits, and confirm that another practitioner cannot access restricted scans. See [the handoff](PROJECT_HANDOFF.md) for the complete checklist.

This is still an academic screening prototype. Model overconfidence, false positives, input suitability and lack of independent clinical validation are not solved by dependency or interface improvements.
