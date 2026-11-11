# Patient workflow, scan storage, and model inventory

Updated 11 November 2026.

## Why every old result was 93.75%

The 10 existing uploads were copies of **one identical solid-gray 100×100 PNG** (RGB value 128 in every pixel), not chest X-rays from the dataset. All 10 decrypted files had SHA-256 `fd34f921596ccd0390f4f5b0047760a11218d9f586fcb7519ebcc8278183f30c`. The source is the synthetic upload fixture in `tests/test_security_hardening.py::test_doctor_scan_isolation`. Earlier tests could write into the application database. Repeating screening on identical inputs explains identical scores; the stored non-null scores were `0.9375`.

This was a test-data isolation bug. It was not a measurement of 93.75% model accuracy. The default test suite now uses private temporary application storage and separate keys before API configuration is imported. Tests cannot repopulate the regular scan library through the former fixture setup.

At the user's request, **10 scan records and their 10 encrypted image files were removed**. User accounts, source dataset, model weights, and environment settings were preserved. No sample patient scans are seeded on startup. `SEED_DEMO_USERS` now seeds demonstration accounts only when the users table is empty, so editing a demonstration account's username does not recreate the old default login on restart.

## Patients and follow-up X-rays

Patients do **not** have login accounts. A patient record is a group of accessible scans with the same pseudonymous `patient_id`; there is no separate patient demographics table.

1. Choose **Upload radiograph**, select a PNG/JPEG, and enter a pseudonymous patient ID. Uploading creates the first patient scan with status **Pending**.
2. Open the scan. The protected image preview can be enlarged by clicking it. The viewer supports zoom, fit-to-view, scrolling, a close button, and Escape. The viewer adds no medical annotations.
3. Click **Run AI screening** to obtain the actual backend model output.
4. Open **Patients** to see one entry per accessible patient ID. The **newest upload** supplies the current screening status. A new, unscreened upload is pending even if an earlier scan was screened.
5. Use **Add follow-up X-ray** to upload another image under the same ID. The new scan opens; run screening there. If its output is `NORMAL`, the patient list displays **Normal** under **Latest AI output**. Previous pneumonia outputs remain in the expandable X-ray history.
6. **Edit patient ID** renames the ID across that patient's scans the caller can manage. Renaming into an existing accessible patient ID is rejected to avoid accidental history merging.
7. **Delete patient** asks for explicit confirmation and deletes that patient's accessible scan records, encrypted images, and saved AI outputs. Original source files, datasets, models, and staff accounts are unaffected. If deleting an encrypted file fails, its metadata is retained and the API reports the incomplete operation; refresh and retry. A group deletion may have removed earlier files before a later filesystem error.

A doctor can manage only their own uploads. A radiologist or administrator can manage all institutional scans. If two doctors used the same patient ID, one doctor's rename/deletion affects only that doctor's scans; institutional users see the combined accessible history. Use consistent pseudonymous identifiers operationally.

**Normal** and **Pneumonia** describe model screening outputs. They do not establish a confirmed diagnosis, recovery, or treatment outcome. The score is uncalibrated and is not a percentage accuracy claim.

## Editable practitioner accounts

Staff, radiologists, and administrators can edit their own display name, sign-in username, and password under **Profile & preferences → Edit your profile**. The current password is required. Leave the new-password fields empty to keep the existing password; a new password needs at least eight characters and at most 72 UTF-8 bytes.

The immutable account UUID and assigned role cannot be edited through this form. Renaming an account updates scan ownership in the same SQLite transaction. Any successful account change increments its session version, invalidates older tokens, and gives the current tab a replacement token held only in memory. Password fields clear after a submitted save, including failed saves. Other sessions must sign in again. The normal refresh/close-tab sign-in behavior is unchanged.

The backend adds the `auth_version` column to existing user tables during normal initialization. No database reset or package installation is required. Restart the backend manually to use the new routes and migration.

## Where uploaded files go

| Item | Default location | Representation |
|---|---|---|
| Scan records, patient IDs, ownership, timestamps, saved AI class/score | `secure_data/metadata.db`, table `scans` | SQLite metadata; the database file itself is not encrypted |
| Practitioner accounts | Same database, table `users` | Display name, username, role, UUID, bcrypt password hash, session version; no plaintext passwords |
| Uploaded image | `secure_data/encrypted_images/<scan-uuid>.enc` | AES-256-GCM encrypted container with a fresh nonce |
| Training dataset | `data/train`, `data/val`, `data/test`, and prepared manifests | Separate from the scan library; uploading does not train the model or add images to training |

Selecting a file initially creates only a browser preview. **Uploading sends its bytes to the backend**, which saves an encrypted copy in the project storage and registers its metadata in SQLite. The original file in its original directory is not moved, renamed, or edited. Its source directory is not copied or monitored. Configuration can override storage/database paths through `SECURE_STORAGE_DIR` and `METADATA_DB_PATH`.

The authenticated image endpoint, `GET /scans/{scan_id}/image`, verifies scan permissions **before** decrypting and authenticating the stored file. It returns PNG/JPEG bytes with `Cache-Control: no-store, private`. The browser creates a temporary blob URL and revokes it on leaving the preview. Tokens are sent in the Authorization header, never image URLs. This endpoint writes no plaintext preview files into the project. Multipart upload ingestion may temporarily spool large uploads through the web framework before encryption; see the existing backend review for that separate limitation.

`secure_data/` and `data/` remain ignored by Git. Clearing patients affects application scan storage, not the dataset.

## Which models exist and which one is active?

All five supplied archives remain in Downloads: `pulmoscan_models.zip`, `(1).zip`, `(2).zip`, `(3).zip`, and `pulmoscan_diagnostics.zip`. The latest completed v2 bundle `(3).zip` was checksum-verified and imported without replacing existing files:

| Model | Local checkpoint | Status |
|---|---|---|
| Teammate's original DenseNet121 | `models/densenet121_pneumonia_best.pth` | Current default/configured app model; epoch 5, stretch preprocessing, threshold 0.40 |
| Kaggle v2 DenseNet121 | `data/experiments/kaggle-v2-20261110T094413Z/densenet121/best.pt` | Present locally; finalized, epoch 20, letterbox preprocessing, saved threshold `0.9999873042106628`; not automatically activated |
| Kaggle v2 EfficientNet-B0 | `data/experiments/kaggle-v2-20261110T094413Z/efficientnet_b0/best.pt` | Present locally; finalized, epoch 16, letterbox preprocessing; requires architecture support before use by the current DenseNet-specific API engine |

The imported directory also contains experiment reports, dataset provenance, source snapshots, and the import receipt. It is ignored by Git because it lives under `data/`; keep a separate model archive backup when moving the project.

Verified checkpoint SHA-256 values:

```text
Active legacy DenseNet121:
5419fadee007300222c7f85e03bd2cb940fb2742864de5fe0b2be83c80bacd1f
Kaggle v2 DenseNet121:
92dcecf92620b19cd9120710e49687ad8e01f14d8ef3e61c3c4690ea211b2dc2
Kaggle v2 EfficientNet-B0:
8c7f999a4ead3a21efebc0ed8afc1ca496d7e39eee74d4afcb000b1ee57b521e
```

Check **Profile & preferences → Active model**, or `GET /health/ready`, for the fingerprint of the bytes actually loaded by a running backend. Current prediction responses include that fingerprint too. Replacing a file on disk does not change a model already in memory.

The Kaggle DenseNet v2 previously achieved **86.57% accuracy** on the 618-image, previously reviewed Kaggle benchmark: **81 false positives and 2 false negatives**. These are experiment results, not results of the gray test images or a claim of clinical validity. Development performance was much higher; independent validation remains pending because only the current Kaggle dataset is available. The saved temperature profile is experimental and is not loaded by the API. See [logit diagnostics](LOGIT_DIAGNOSTICS.md) and [calibration and external validation](CALIBRATION_AND_EXTERNAL_VALIDATION.md).

No Kaggle model was automatically promoted, no weights were retrained, and no services were started by this work.

## Verification

The updated code passed **172 backend tests**, **70 frontend tests**, frontend lint, and the Next.js production build. Tests cover ownership-scoped image access and deletion, tamper rejection, account rename/password changes and old-token rejection, follow-up history/latest-result behavior, enlarged-image controls, blob-URL cleanup, and password-field clearing. After the full tests, application storage still contained **zero scans and zero encrypted images**.

An offline CPU smoke check on two actual normal and two pneumonia-labelled dataset images produced four distinct pneumonia scores (`0.08`, `0.0333`, `0.9998`, `0.9965`) with the unchanged original checkpoint. This confirms the output is not a fixed 93.75%; four samples do not estimate accuracy. Results are recorded locally in ignored `data/review/prediction_smoke_20261111.json`. No samples were uploaded into application storage during this check.

## Manual review

Start or restart the services yourself from the project root:

```powershell
npm.cmd run dev
```

Sign in, upload an actual dataset test image or your own appropriately de-identified chest X-ray, enlarge it, and run screening. Then add a follow-up under the same patient ID and check the Patients page and history. A particular class cannot be guaranteed in advance. Test account edits with your current password, and patient deletion only on records you intend to remove.
