# Train on Kaggle, run the app locally

**Scope update (13 November 2026):** finding detection is **deferred**. You do not need another dataset or Kaggle run for the current explanation feature. The [finding-model plan](../docs/FINDING_MODEL_NEXT_STEPS.md) and [PulmoScan_Finding_Data_Check.ipynb](PulmoScan_Finding_Data_Check.ipynb) are retained for possible future work; that notebook checks annotations only and is not a required setup step. The existing classifier notebooks below are reproduction references.

**Current status:** the v2 diagnostic results have been verified. The next scoring/calibration work can use the downloaded CSVs locally, without another Kaggle training run. See [calibration and external validation](../docs/CALIBRATION_AND_EXTERNAL_VALIDATION.md). Only the original dataset is available so far; independent validation remains pending.

**Completed diagnostic reference:** [PulmoScan_Logit_Diagnostics.ipynb](PulmoScan_Logit_Diagnostics.ipynb) and [the diagnostic guide](../docs/LOGIT_DIAGNOSTICS.md) are retained to reproduce raw-logit ranking and saturation measurements. The returned diagnostic ZIP is already verified.

**v2 training reference:** [PulmoScan_Training_v2.ipynb](PulmoScan_Training_v2.ipynb) and [the v2 instructions](../docs/TRAINING_V2.md) describe the completed threshold-holdout/JPEG experiment. The [model review](../docs/MODEL_REVIEW_2026-11-10.md) records the motivating evidence. Another run is not required for the current postprocessing work.

## v1 reference workflow

Upload **[PulmoScan_Training.ipynb](PulmoScan_Training.ipynb)** to Kaggle. It is self-contained: it embeds the current shared training sources and needs no project ZIP, private GitHub access, local images, `.env`, or API credentials. The other files in this folder maintain the notebook; you do not need to upload them separately.

## Start a training run

1. Sign in to Kaggle and create a Python notebook. Use **File → Import Notebook** to select `kaggle/PulmoScan_Training.ipynb` from this project.
2. Use **Add Input** to attach [Paul Mooney's Chest X-Ray Images (Pneumonia)](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia), the dataset shown in your screenshot.
3. Under session settings, select an available **GPU** and enable **Internet**. Internet is needed for the official Torchvision ImageNet weights and any missing training extras. GPU availability and verification/quota requirements are controlled by Kaggle; the notebook does not assume a specific accelerator is available. See [Kaggle's notebook documentation](https://www.kaggle.com/docs/notebooks).
4. Leave `DATA_ROOT=None` for automatic detection. If more than one unrelated matching dataset is attached, set it to the directory directly containing `train/`, `val/`, and `test/`. Nested copies are never merged.
5. Keep `RUN_FINAL_TEST=False` initially. Run the cells in order, or use **Run All**. The default training cell trains **DenseNet121, then EfficientNet-B0** with live logs.
6. Inspect the validation comparison after both models finish. The ZIP export works with validation results alone. To obtain final test metrics, set `RUN_FINAL_TEST=True` in the settings cell, rerun **only that settings cell and the optional final-test cell**, then rerun the export cell. Test evaluation is explicit and uses only the validation-selected checkpoint and saved threshold.
7. Download **`pulmoscan_models.zip`** from `/kaggle/working/` in the output browser. If you export again after evaluation, the notebook uses a new timestamped filename to preserve the earlier ZIP.
8. Save a notebook version **including output files** before ending the session, and confirm the model files appear in that version's outputs. Draft code autosave alone is insufficient. When offered, use Quick Save with output saving enabled for an already completed interactive run. **Save & Run All executes a fresh run**; choose it deliberately rather than expecting it merely to preserve the current session. Kaggle's controls may change; check the save dialog's output options.

The notebook keeps Kaggle's installed, matching `torch`/`torchvision` GPU pair. It checks torch >= 2.5, the CUDA runtime, a real GPU kernel, pretrained-weight hashes, and finite forward outputs. It installs only missing training extras listed in [requirements.txt](requirements.txt). **Do not install the project's Windows CUDA profiles or full API requirements in Kaggle.** Runtime versions and the exact training-source fingerprint are recorded in every candidate's metadata.

## Settings and protocol

The Kaggle profile is [train_config.json](train_config.json): physical batch 16, accumulation 1, 224px images, 2 classifier warm-up epochs, up to 25 epochs per candidate, and early stopping. One GPU is used; a T4 ×2 session does not automatically use both cards. If GPU memory is insufficient, use batch 8 and accumulation 2 in a new workspace/run. Lower batch sizes remain possible; no accuracy or runtime is promised.

The local default remains physical batch 2 / accumulation 8, with automatic GPU selection or CPU fallback. Both environments use the same `src/` and `scripts/` implementation: weighted loss, aspect-preserving full-image letterboxing, mild training-only augmentation, frozen BatchNorm statistics, AMP on CUDA, gradient clipping, validation-AUC model selection, and a validation-only threshold policy. A configured 95% validation sensitivity target is not a guarantee of test sensitivity, calibrated probabilities, or clinical performance.

Kaggle inputs remain read-only. The notebook fully decodes/audits the attached dataset, records hashes, reserves test-connected candidate-subject/duplicate components, deduplicates exact pixels, and produces a fresh manifest. It never copies the raw dataset into its output directory or silently skips an integrity failure. Every training read verifies the original saved hash.

The laptop's earlier suspect-file exclusions are specific to that source tree and are **not** applied to Kaggle's independently audited inputs. As a result, Kaggle split counts and manifest identity may differ from the laptop's 4,035 / 712 / 618. Use the counts and checksums printed by your actual run. Do not present metrics from different manifests as a direct same-cohort improvement. Filename-derived groups are heuristics, not verified patient identities; near-duplicate and external clinical validation remain unresolved. The reserved benchmark is not a new unseen external cohort.

## What to download

The download ZIP contains:

| File | Purpose |
| --- | --- |
| `suite/<model>/best.pt` | Both completed model candidates with class mapping, normalization, resize mode, and validation-selected threshold |
| `suite/comparison.json` | Validation ranking and recommended checkpoint; whether final test was evaluated |
| `suite/<model>/validation_summary.json`, `validation_predictions.json` | Validation metrics and unrounded scores |
| `suite/<model>/history.json`, `train.log` | Training history, logs, and timings |
| `suite/<model>/split_manifest.json`, `config.json`, `environment*.json` | Exact source file hashes, split policy, settings, and runtime versions |
| `suite/final_test_results.json` | Present only after the explicit final-test step |
| `source/` | Snapshot of the shared preparation, training, and evaluation implementation |
| `bundle.json` | SHA-256 checksums for every included artifact |
| `suite/<model>/last.pt` | Optional larger resume state; enable `INCLUDE_RESUME_IN_ZIP=True` to include it |

The full workspace under `/kaggle/working/pulmoscan_training/` also contains the dataset audit, prepared manifest, embedded sources, logs, and epoch checkpoints. Save this workspace as notebook output for later Kaggle resume. The smaller model ZIP is intended for transferring completed candidates back to the project.

## Bring the ZIP back to this project

From the project root, replace the example path with your actual download:

```powershell
.\.venv\Scripts\python.exe scripts/experiment_bundle.py verify --archive "C:\path\to\pulmoscan_models.zip"
.\.venv\Scripts\python.exe scripts/experiment_bundle.py import --archive "C:\path\to\pulmoscan_models.zip"
```

Import verifies all file checksums and stores the suite under `data/experiments/<original suite name>/`, with its training source under `training_source/`. It refuses to replace an existing suite, loads no checkpoint pickle, starts no server, and does not change the live model or `.env`. Use bundles produced by your own trusted notebook; checksums detect corruption, not the identity of an archive's creator.

The downloaded manifest intentionally preserves the original Kaggle source paths. Do not rewrite it to point at the damaged laptop dataset. Do final test evaluation in the original Kaggle environment. After downloading, review `comparison.json` and any final test results before promotion. The current API accepts DenseNet121; if EfficientNet-B0 wins, serving compatibility and UI labeling must be implemented/reviewed before deployment. Renaming a file alone does not complete that integration.

## Resume on Kaggle

- If the current session is still alive, rerun the training cell. It skips completed candidates and restores incomplete candidates from the last fully completed epoch.
- For another session, attach the saved notebook's output using **Add Input**. Use the original notebook version, set `RESUME_SOURCE` to its `pulmoscan_training` workspace, set `RUN_NAME` to the saved suite name, and retain the original training settings. Keep the original chest-X-ray input attached at the same mount path.
- The setup copies only saved audit/preparation/experiment artifacts into writable storage. It checks the exact embedded source index and original source hashes. Work after the last completed epoch is lost. If a model stopped before its first full epoch, choose a new run name.
- If the source mount or runtime/library versions change, do not claim exact reproducibility. The notebook refuses changed source code/config/manifest instead of silently accepting a different experiment.

## Maintain or verify the notebook locally

```powershell
.\.venv\Scripts\python.exe kaggle/build_notebook.py
.\.venv\Scripts\python.exe kaggle/build_notebook.py --check
.\.venv\Scripts\python.exe -m pytest tests/test_kaggle_workflow.py tests/test_training_pipeline.py tests/test_training_integrity.py -q
```

The builder embeds only its explicit source allowlist, never datasets, trained weights, secrets, or patient storage. Rebuild the notebook after changing shared training code. Automated checks compile every notebook cell, execute the source bootstrap in temporary storage, exercise preparation on synthetic images, test resume routing and tiny-network resume, and verify export/import checksums and path containment. They do not run a real Kaggle session or train the production backbones. The actual Kaggle GPU training run is performed by you.
