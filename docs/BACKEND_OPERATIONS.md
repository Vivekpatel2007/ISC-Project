# Backend lifecycle, readiness, and model identity

This step improves backend reliability and test isolation. It does not change the loaded model's weights, threshold, calibration, or measured classification performance. Frontend/backend startup and neural training remain manual.

## Service initialization

Database, encrypted-storage, and inference-engine instances are published only after their constructors finish. Initialization is protected by a process-local reentrant lock. Simultaneous first requests therefore cannot allocate duplicate copies of the model or race the service constructors. A failed constructor is not cached; a later explicit retry can succeed.

This guarantee applies **within one Python process**. Multiple server workers still load separate models. Keep the documented single-worker local setup on the GTX 1650 4 GB unless capacity has been measured for another configuration.

## Readiness observes services without initializing them

`GET /health/ready` now reads the instances already initialized during application startup. It does not load a model, create storage, or initialize a database as a side effect of a probe.

- An uninitialized or unavailable component produces a structured **HTTP 503** response with `checks` and `components` statuses. Constructor failures no longer occur ahead of this handler through eager readiness dependencies.
- The database probe uses SQLite URI **read-only** mode and checks for the expected `scans` and `users` tables. A missing database is not recreated; an empty SQLite file is not treated as initialized.
- The storage probe checks that the initialized storage directory exists as a directory. It does not establish free space, write permissions, successful encryption, or throughput.
- The model probe checks the initialized model, checkpoint-file presence, and loaded metadata. It does not perform a GPU forward pass or hash the disk file on every request.
- Component failures expose only generic states to clients, without local paths, secrets, or exception messages.
- `architecture` is the model name (`densenet121`); the class list is returned separately as `class_names`. Liveness and the application now use the same API version constant.

The response explicitly includes **`readiness_scope='operational_only'`**. HTTP 200 means these operational checks passed; it does not establish clinical validation, calibrated probabilities, input suitability, or predictive accuracy.

## Identify the exact active model

The loader reads checkpoint bytes once, computes their SHA-256, and deserializes those same bytes with the existing restricted loader. The fingerprint therefore identifies the file contents actually used by the loaded engine, even if a file at the same path is replaced later. It is an identity/provenance field, not proof of trusted authorship or a workaround for the documented PyTorch loader advisories.

Readiness returns a `model` object with:

- Architecture, classes, epoch, image size, and resize mode.
- The loaded `checkpoint_sha256`, optional `source_manifest_sha256`, and manifest-based finalization status.
- Decision threshold, current device, and the existing uncalibrated-score interpretation.

No local checkpoint path, arbitrary training configuration, free-form checkpoint text, keys, or patient metadata is included. Prediction responses also include `model_checkpoint_sha256`, allowing callers to identify the model that produced that response. This field is not yet stored as a new database column; it does not reconstruct provenance for older stored predictions.

The fingerprint is captured at loading time. Readiness does not continuously attest that bytes currently on disk still match it, or that internal model parameters have never been modified by other Python code. A deliberate model-file change requires a reviewed reload/restart; replacing a file alone does not switch the in-memory model.

## Reject provisional and resume artifacts

Manifest-based checkpoints must contain a valid manifest digest, `finalized=true`, saved preprocessing, and a saved threshold. A training `last.pt` or provisional `best.pt` is rejected before reconstructing the network, instead of silently using default stretch preprocessing and threshold 0.40. The legacy teammate checkpoint has no preparation manifest and remains supported as a legacy artifact. Its active identity is:

```text
5419fadee007300222c7f85e03bd2cb940fb2742864de5fe0b2be83c80bacd1f
```

Finalized means the experiment tool finished checkpoint/threshold selection. It is **not** an approval or clinical-validation flag. No experimental Kaggle model or temperature profile is automatically promoted by this change.

## Automated tests use separate storage and keys

`tests/conftest.py` sets temporary application paths and random test-only cryptographic/JWT keys **before test collection imports API configuration**. This prevents lifespan/security tests from adding accounts or synthetic uploads to the user's configured application database. The suite uses CPU by default, with bounded test-only CPU threads; mocked CUDA-selection regressions remain covered. This does not change `.env`, the shell's environment, or the app's GPU selection when started separately.

Tests run in a fresh Python process. If API configuration was imported before isolation could be applied, the suite refuses that unsafe embedded invocation. Private temporary test storage is cleaned up after the run. Tests that need per-case databases can still use their own fixtures.

During review, the existing application database contained **10 records matching the old security-test synthetic marker** (`ANON-DOC1-01` uploaded by `doctor1`). Earlier test setup could mix test data with application data. Those records were left unchanged; matching a marker alone is not sufficient authorization to delete records. Existing app data, keys, and model files are preserved. The new isolation prevents subsequent pytest runs from adding more such records to live storage.

`tests/e2e_live_verification.py` is a separate, explicitly invoked live workflow tool. It requires a manually running backend and intentionally exercises that service; it is not part of the isolated default pytest collection.

Verification on 11 November 2026: the full default suite passed **160 tests**. Before/after SHA-256 checks matched for `.env` and the active checkpoint. The application storage file list, sizes, and modification times also matched, and the existing synthetic-marker count stayed at 10. The two test warnings were a dependency deprecation and the intentional oversized-image rejection case.

## Manual checks

Run tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

The read-only development preflight remains:

```powershell
npm.cmd run dev:check
```

To inspect readiness in a running app, start the services yourself when ready:

```powershell
npm.cmd run dev
```

Then visit `http://127.0.0.1:8000/health/ready`. Compare `model.checkpoint_sha256` with the intended artifact rather than assuming a downloaded model is active. The assistant does not start these services.
