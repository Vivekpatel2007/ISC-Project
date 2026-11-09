# Backend and model review — 9 November 2026

Follow-up: [the manual training workflow](TRAINING.md) now fixes the preparation/parser issues described below and uses source-backed audited manifests with separate experiment outputs. This document preserves the earlier 624-image baseline and findings; no new model has been trained or promoted by the assistant.

Cleanup note: historical generated files under `results/` and `data/review/model_baseline.json` were removed at the user's request. Metrics below are historical review snapshots, not results of the new training workflow. Integrity audits, prepared manifests, and the app checkpoint were preserved. The reproduction commands near the end intentionally recreate historical review reports if explicitly run; use the training guide for new experiments.

## Result

The request/authentication/encrypted-storage/inference path is a working local prototype. It is **not ready to describe as the best model or as independently validated clinical software**. The provided checkpoint has a high false-positive rate on the downloaded test set, patient independence remains unverified, and several training/security issues need work before the next experiment or deployment.

This review changed no learned weights, decision threshold, image labels, or source dataset splits. No servers or training were started. The new evaluation tool uses the actual backend inference engine rather than a separately reconstructed model.

## Verified dataset

The downloaded images are directly under `data/train`, `data/val`, and `data/test`. All of `data/` is now ignored by Git; no dataset files were tracked when checked.

| Split | NORMAL | PNEUMONIA | Total |
| --- | ---: | ---: | ---: |
| Train | 1,341 | 3,875 | 5,216 |
| Validation | 8 | 8 | 16 |
| Test | 234 | 390 | 624 |
| Total | 1,583 | 4,273 | 5,856 |

All 5,856 files fully decoded. No missing class folders, decode failures, or images outside the current API format/dimension/size policy were found. Image payloads total **1,236,482,806 bytes**, approximately **1.15 GiB**.

No **exact byte or decoded-pixel duplicate groups across splits** were detected. This does not rule out near-duplicates, different views of one patient, incorrect labels, or distribution leakage.

The audit found **170 candidate pneumonia subject IDs shared between raw train and test**, based on `person<number>` filename prefixes. These are potential overlap indicators, not 170 confirmed shared patients: the source must establish whether numbering is globally unique. No candidate filename-ID overlap was found for raw train/validation or validation/test. Earlier reports that simply call this test set independent need that claim rechecked.

The raw validation split contains only **8 examples per class**. It is too small to support confident model/threshold comparisons. Build and audit a suitable validation split during the next training-preparation step rather than selecting settings from test results.

Audit manifest SHA-256, binding relative filenames to file hashes:

```text
e318bd045726b9d8f0941b88e9a791f314ff4531705077df48f2f4e83c5fc6fe
```

## Measured model baseline

Evaluation covered **all 624 provided test images** on the GTX 1650 (`cuda:0`, PyTorch `2.5.1+cu124`) through the production validation/preprocessing/prediction code. The saved threshold stayed **0.40**. No threshold sweep, checkpoint selection, or weight updates were performed.

| Metric | Result |
| --- | ---: |
| Accuracy | **84.94%** (530/624 correct) |
| Balanced accuracy | **80.00%** |
| Pneumonia sensitivity / recall | **99.74%** (389/390) |
| Normal specificity / recall | **60.26%** (141/234) |
| Pneumonia precision | **80.71%** |
| Macro F1 | **82.11%** |
| ROC-AUC from returned scores | **0.9632** |

| Actual class | Predicted NORMAL | Predicted PNEUMONIA |
| --- | ---: | ---: |
| NORMAL | 141 | **93 false positives** |
| PNEUMONIA | **1 false negative** | 389 |

At this threshold the model finds almost every labeled pneumonia image, but incorrectly flags **39.74% of normal images**. This is the main measured classification weakness. A single overall accuracy figure conceals that tradeoff; balanced accuracy averages class recall. [scikit-learn balanced accuracy documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.balanced_accuracy_score.html)

These are image-level results on the supplied public test split, not a clinical accuracy claim or proof of unseen-patient generalization. The original checkpoint's split manifest/provenance is unavailable. ROC-AUC here uses the API's four-decimal scores; it is not directly comparable to historical unrounded-score evaluations. Correct/incorrect counts match the repository's previous test result, but that does not establish the original experiment's provenance.

Checkpoint SHA-256:

```text
5419fadee007300222c7f85e03bd2cb940fb2742864de5fe0b2be83c80bacd1f
```

## Corrections made in this review

- **Bounded upload-handler reads:** read at most the configured file limit plus one byte before rejecting an oversized image. This bounds the handler's read; it does not solve pre-handler multipart parsing/body limits.
- **Complete image decoding:** malformed JPEGs that pass Pillow header verification but fail pixel decoding now become image-validation errors, rather than escaping conversion as unexpected server failures. Image objects are closed after use.
- **Checkpoint metadata validation:** fail early for unsupported architecture, reversed class order/mapping, invalid image size, invalid normalization, and non-finite/out-of-range thresholds. This prevents silently mislabeled or undefined outputs.
- **Non-finite output rejection:** NaN/Inf or incorrectly shaped class scores cannot become predictions or new persisted screening results.
- **Serialized forward passes:** concurrent threads sharing one inference engine execute one model forward at a time to bound activation/workspace memory on a 4 GB GPU. This is not a multi-process load/capacity guarantee.
- **Restricted checkpoint loading:** the API uses `weights_only=True` rather than unrestricted pickle loading. This is a narrower loader, **not a security guarantee for the currently pinned PyTorch versions**; see the dependency finding below.

Training code, augmentation choices, model architecture, decision threshold, and split preparation were deliberately left for the next reviewed step.

Verification completed after the corrections: **99 backend tests passed**, `pip check` passed, and `npm.cmd run dev:check` passed with compute device `cuda:0`. The regression coverage includes truncated JPEGs, invalid metadata/thresholds/logits, bounded handler reads, serialized forward calls, and audit hash/group behavior. Passing these checks establishes tested software behavior, not clinical model quality or a complete security audit.

## Outstanding findings and priorities

| Priority | Finding and implication | Next action |
| --- | --- | --- |
| Before training | `src/prepare_dataset.py::extract_patient_id` reduces every `NORMAL2-IM-<number>-...` filename to `NORMAL2-IM`. Its grouping option can treat many distinct normal subjects as one group and distort splits. The new audit parses the number correctly; legacy preparation remains unchanged. | Correct and test the preparation parser, audit all split boundaries, record exact split manifests, and verify subject-ID semantics. |
| Before training | The preparation helper defaults to a random file split, deduplicates only its training candidate pool, ignores the bundled raw validation subset, and reuses destination folders without removing stale files. | Design the next experiment's cohort/split policy explicitly. Use fresh output directories and reject leakage before fitting. |
| Before training | Training defaults point to `data/model_data`, which is absent; the local raw data is under `data/`. Batch size 16 has not been verified on this 4 GB GPU. | Use a separate experiment configuration after preparation; begin the later memory trial with a smaller batch and preserve the current checkpoint/results. |
| Before trusting inputs | Any valid permitted PNG/JPEG, including an ordinary photograph or synthetic image, can reach the classifier. Format checking does not establish chest X-ray suitability. | Evaluate a separately validated input-suitability/quality gate; do not equate grayscale pixels with a valid radiograph. |
| Before claiming calibrated risk | The two softmax scores and selected-class confidence are uncalibrated model scores. The 0.40 threshold is not a 40% accuracy statement. | Evaluate calibration and select thresholds on validation data using a predefined error tradeoff. Keep test data out of threshold selection. |
| Before deployment or loading unfamiliar models | CPU/CUDA 12.4 profiles pin PyTorch 2.5.1; the Blackwell profile pins 2.7.1. Published checkpoint-loader advisories affect these versions, including restricted loading. | Validate a currently patched compatible runtime or a safer artifact format, and establish trusted artifact provenance/digests. Do not treat this review's `weights_only=True` change as a complete security repair. |
| Before claiming zero plaintext disk use | Installed Starlette multipart parsing uses `SpooledTemporaryFile` and a **1 MiB** spool threshold, so uploads can reach temporary plaintext files before the endpoint runs. Existing broad zero-plaintext claims are unsupported for ingestion. Inference decryption itself remains in memory. | Design bounded ingress and explicit upload-spooling/storage policy. A bounded `file.read` alone does not fix parser-level spooling. |

The checkpoint-loader findings are supported by PyTorch's [CVE-2025-32434 advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6) and [CVE-2026-24747 advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p). The latter lists fixes from 2.10.0 for that issue; this is not a claim that any particular release has no other vulnerabilities. The current API does not accept uploaded model checkpoints, which limits this specific exposure, but local artifact loading still requires trust.

FastAPI documents the upload spooling behavior in [Request Files](https://fastapi.tiangolo.com/tutorial/request-files/). The installed Starlette `formparsers.py` was also inspected directly. Existing security documents describe historical claims, not a new production security certification.

Avoid leakage when selecting models: preprocessing and tuning must respect train/validation/test separation. [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)

## Reproducing the checks

Run from the project root. The first two commands read source images and write reports under ignored `data/review/`; neither starts services or trains a model.

```powershell
.\.venv\Scripts\python.exe scripts/audit_dataset.py --data-dir data
.\.venv\Scripts\python.exe scripts/evaluate_backend.py --data-dir data
.\.venv\Scripts\python.exe -m pytest tests/ -q
npm.cmd run dev:check
```

`dataset_audit.json` records image hashes, counts, decode results, duplicates, and candidate-ID overlaps. `model_baseline.json` records checkpoint hash, fixed threshold, metrics, and per-image predictions. Use a different `--output` path if preserving multiple review runs. Do not repeatedly evaluate candidate models on this test set as a substitute for validation.

During this session Windows also reported an unreadable SymPy package directory and a Torch bytecode cache whose instructions did not match its readable Python source. SymPy 1.13.1 was restored, and the single mismatched bytecode cache was regenerated from source. Previous contents were preserved under ignored `.venv/_recovery/`. Package imports then succeeded. No OS/disk repair, security-policy changes, or driver modifications were performed; recurring corruption would need separate system investigation.
