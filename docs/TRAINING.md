# Local training and preprocessing

Current postprocessing and validation status is documented in **[CALIBRATION_AND_EXTERNAL_VALIDATION.md](CALIBRATION_AND_EXTERNAL_VALIDATION.md)**. The completed v2 experiment is described in [TRAINING_V2.md](TRAINING_V2.md), preserving the v1 results and profiles below. See [the model review](MODEL_REVIEW_2026-11-10.md) for the original validation/test gap and metadata evidence.

## Run this in your terminal

**Current laptop status, 10 November 2026:** after the fresh restart, training stopped during epoch 3 because `train/PNEUMONIA/person1411_bacteria_3610.jpeg` no longer matched its prepared checksum. Two subsequent full integrity passes confirmed that mismatch. The underlying cause is unknown. The source and manifest have not been changed to bypass it; use the [standalone Kaggle notebook](../kaggle/README.md) for the requested cloud training workflow. The local code remains usable with verified sources and automatic GPU/CPU selection, and reports integrity failures with expected/actual hashes and a nonzero exit status. This is not a claim that repository changes repair the device.

The two earlier interrupted suites (`20261109T181731Z` and `20261109T182129Z`) were previously archived under `data/recovery/retired_experiments_20261110/` at your request to start fresh. The subsequent failed run and its logs/checkpoints remain available as evidence. Dataset audits, recovery evidence, pretrained weight cache, and the current API checkpoint remain.

For local training, first verify the prepared sources with `scripts/check_training_data.py`. Do not train while that check reports failures. Stop the backend with **Ctrl+C** first if it is running, so it releases GPU memory. With a verified dataset, run from the project root:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py
```

This trains **DenseNet121 followed by EfficientNet-B0**, sequentially on the available compute device. It prints the GPU name, batch progress, epoch ETA, losses, validation metrics, and peak allocated VRAM. Logs and checkpoints are also saved under `data/experiments/<UTC timestamp>/<model>/`.

The assistant runs preparation, forward-only checks, and synthetic unit tests. Real-model training is started manually by you.

The runner does not evaluate the test set, replace the API checkpoint, edit `.env`, or start services. Completing a run does not automatically deploy a candidate. The current API remains on its existing DenseNet121 model.

Old generated training/evaluation results have been removed from `results/`, along with the old local baseline prediction JSON. Dataset integrity audits and the prepared manifest remain because the new workflow needs them. All new training results go into fresh timestamped `data/experiments/` directories, so they do not mix with historical reports.

Actual model quality will be determined from validation and final test results; these candidates and preprocessing choices are starting experiments, not a guaranteed best architecture or accuracy percentage.

## Dataset integrity and prepared splits

Raw images remain at `data/train`, `data/val`, and `data/test`. The prepared file is:

```text
data/prepared/screening-v1/manifest.json
```

It refers to the original image paths, so preparation does not duplicate the 1.15 GiB dataset. Transforms run in memory during training. All `data/` contents, including experiment weights and logs, are ignored by Git.

| Prepared split | NORMAL | PNEUMONIA | Total |
| --- | ---: | ---: | ---: |
| Training | 1,144 | 2,891 | **4,035** |
| Validation | 202 | 510 | **712** |
| Test | 231 | 387 | **618** |

The protocol combines the raw training and tiny raw validation pools, then performs a deterministic class-balanced group split with seed 42 and approximately 85%/15% image proportions. It chooses among 64 group-shuffle partitions per class based only on class image counts, not model predictions. Images connected by a candidate subject ID or identical decoded pixels remain in one component. Components touching the original test set cannot enter training or validation.

The legacy normal-ID parser is fixed: `NORMAL2-IM-0383-...` and `NORMAL2-IM-0384-...` now have distinct candidate IDs. Filename-derived IDs still do **not** establish authoritative patient identities or exclude near-duplicates; this is a conservative protocol for the available metadata.

The preparation manifest records these exclusions:

- **457** raw train/validation images belong to components reserved for test because of candidate-ID overlap.
- **22** additional decoded-pixel duplicates were removed from the eligible training pool.
- **6** duplicate test images were omitted from the prepared test manifest. The original 624 files remain untouched; the new test set has 618 unique decoded images.
- **6** images in components associated with unexpectedly changed source files were excluded, as described below.

The prepared test set is different from the earlier 624-image baseline. Its future metrics must identify the new protocol and cannot be presented as a direct same-cohort improvement over that baseline. The raw test cohort has already been inspected for the baseline; the deduplicated subset is a reserved benchmark, not a new external unseen cohort. Neither the original checkpoint's provenance nor external clinical generalization is established.

Manifest SHA-256:

```text
1d9d2d06b64a4811cfb2fd84b7eabff52b49c1f37fcada539db04be1a2ccfb5a
```

### Unexpected source-file changes

Four raw images had different file hashes **and decoded pixels** from the earlier audit. You confirmed that you had not edited or re-extracted them. The fresh audit still decoded all 5,856 images, but these four files and linked candidate groups were conservatively excluded rather than silently accepted:

```text
train/NORMAL/IM-0337-0001.jpeg
train/NORMAL/NORMAL2-IM-0894-0001.jpeg
train/PNEUMONIA/person1009_virus_1694.jpeg
train/PNEUMONIA/person1294_virus_2221.jpeg
```

The source images were not moved, deleted, or repaired. Original and fresh audits remain under `data/review/dataset_audit.json` and `data/review/dataset_audit_training.json`. The manifest records both old and new file hashes for the changed files.

Windows' read-only storage status reported **Healthy/OK**, and repeated reads plus full included-image hash checks were stable during setup. That status does not explain the changes or rule out an underlying system issue. Earlier package-directory and bytecode damage is recorded in [the backend review](BACKEND_REVIEW.md).

Training checks every included image's SHA-256 **every time it is loaded**, in addition to startup verification. If an integrity error appears, stop and investigate the source files/system. Do not regenerate the manifest simply to silence the error.

### Recovery of the interrupted local run

After the first training epoch, two additional included sources differed from the original manifest, each by one byte:

```text
train/NORMAL/IM-0502-0001.jpeg
train/PNEUMONIA/person1502_bacteria_3923.jpeg
```

Both originals were fetched individually from the same [Kaggle dataset](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia) and accepted only after their SHA-256 hashes exactly matched the original manifest. The changed versions remain in `data/recovery/source_recovery_20261110/changed_sources/`; `recovery.json` in that directory records the source URLs and before/after hashes. No manifest, split assignment, or checkpoint was rewritten. The four earlier excluded sources remain excluded.

Before/after evidence is saved as `data/review/training_integrity_before_recovery_20261110.json` and `data/review/training_integrity_after_recovery_20261110.json`. All 5,365 included sources matched in three consecutive post-recovery passes, and both GPU forward checks passed. The saved epoch-1 checkpoint was checked without advancing training, then archived with its interrupted suite at your request to start over. Archived checkpoint paths recorded in the old logs refer to their previous locations; use the fresh-start command above. The original manifest remains unchanged. The cause of the byte changes is still unknown; the read-only Windows storage status did not diagnose it. A passing checksum check establishes the bytes read during that check, not future system reliability.

For a complete integrity report without loading a model or training:

```powershell
.\.venv\Scripts\python.exe -u scripts/check_training_data.py --passes 3
```

This checks all prepared splits, lists every mismatch or unreadable source, and writes a new report under `data/review/`. It returns a nonzero exit code on failure and never repairs images, changes the manifest, or overwrites previous reports. If failures recur, preserve that report and investigate before resuming; accepting changed hashes or repeatedly excluding files would hide the problem.

## Models and preprocessing

Both candidates start from Torchvision's default ImageNet weights, not from the teammate's potentially overlapping pneumonia checkpoint. [DenseNet121 weights](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.densenet121.html), [EfficientNet-B0 weights](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html)

The preprocessing experiment uses:

- Full image decoding and RGB conversion, then grayscale represented in three channels.
- **224 × 224 aspect-preserving letterboxing** with centered black padding, retaining the image field rather than stretching anatomy or applying a center crop.
- The saved ImageNet normalization values for both models.
- Training-only mild affine changes: up to 5° rotation, 2% translation/scale change, and small brightness/contrast jitter.
- No random flips, aggressive crops, CLAHE, or unvalidated image enhancement.
- Deterministic preprocessing for validation and test; no test-time augmentation or randomness.

These are reasonable conservative choices to evaluate, not proof that letterboxing is optimal for every dataset. Checkpoint metadata stores the resize policy. The API understands this policy for new DenseNet checkpoints, while legacy checkpoints without the field retain their original stretch preprocessing. A regression check verifies unchanged legacy tensors. EfficientNet candidates are supported by the experiment tools; serving/UI integration is a later review step if EfficientNet wins.

## Configuration for the GTX 1650

Defaults are in [configs/train_local.json](../configs/train_local.json):

| Setting | Default |
| --- | --- |
| Candidate models | DenseNet121, EfficientNet-B0 |
| Image size / physical batch | 224 / **2** |
| Gradient accumulation | **8**, approximately 16 images per optimizer update |
| Maximum epochs | **25 per candidate** |
| Classifier warm-up | 2 epochs with backbone parameters frozen |
| Fine-tuning | All layers after warm-up; lower backbone learning rate |
| Batch normalization | Running statistics frozen for small-batch stability |
| Loss | Inverse-frequency class weights from the training split only |
| Optimizer / schedule | AdamW / cosine learning-rate decay |
| Mixed precision | CUDA only |
| Early stopping | 7 fine-tuning epochs without a qualifying validation AUC gain |
| Data-loader workers | 0 for straightforward Windows behavior and epoch resume |
| Random seed | 42 |

Class weights remain effective with tiny single-class batches because loss is accumulated as a weighted sample sum, normalized by the actual accumulation-window sample count. The final partial window is handled explicitly. Gradient accumulation reduces activation memory compared with a physical batch of 16, but is not equivalent to running batch-normalization statistics on 16 images. AMP overflows are reported and handled by the scaler. [PyTorch AMP accumulation examples](https://docs.pytorch.org/docs/stable/notes/amp_examples.html)

The forward-only preflight passed on the actual GTX 1650 for both models. It does not measure full backward/optimizer peak memory or guarantee training speed. The terminal reports observed epoch timing and GPU memory rather than assuming a completion time.

If CUDA reports out of memory, preserve the log and start a new run with a smaller physical batch:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py --batch-size 1 --accumulation-steps 16
```

Use a fresh run for changed settings; do not change the configuration of an existing resume checkpoint. CPU-only devices can use the same workflow, but training can take substantially longer. The runner honors `PULMOSCAN_DEVICE` from `.env` or the terminal environment.

To train just the first candidate:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py --models densenet121
```

## Logs, checkpoints, and interruption

Each model directory contains:

| File | Contents |
| --- | --- |
| `train.log` | Persistent copy of progress/epoch messages |
| `config.json`, `environment.json` | Resolved settings and runtime versions/device |
| `split_manifest.json` | Exact split protocol, hashes, and exclusions |
| `history.json` | Per-epoch train/validation metrics, time, and peak VRAM |
| `last.pt` | Last fully completed epoch, optimizer/scheduler/scaler, RNG, and loader state |
| `best.pt` | Best validation-AUC checkpoint; finalized with a validation-selected threshold after the run |
| `validation_predictions.json` | Best checkpoint's validation labels and unrounded scores |
| `validation_summary.json` | Completed candidate's validation results and checkpoint checksum |

Checkpoint files are written via a temporary file and atomic replacement. **Ctrl+C** stops training; completed epoch checkpoints remain. Work since the last completed epoch is not preserved. If interrupted before any complete epoch, start a new run.

Environment metadata includes a fingerprint of the training/preparation source files. Keep the code and library versions unchanged when resuming; changing them can change reproducibility even when the saved settings match. Legacy `src/evaluate_test.py` and `src/tune_threshold.py` reject these manifest-based experiment checkpoints to avoid applying the old stretch/ImageFolder protocol accidentally; use the experiment tools above.

To resume, use the exact `last.pt` path printed in your terminal, replacing the example timestamp:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py --resume "data/experiments/<timestamp>/densenet121/last.pt"
```

Resume restores the original configuration, manifest identity, random generators, optimizer, schedule, scaler, and shuffle state. A tiny synthetic-network test verifies that epoch-boundary resume matches an uninterrupted run; this is not a promise of bitwise reproducibility across different GPU hardware or library versions.

An interrupted-model resume command resumes only that model. If DenseNet completes and EfficientNet has not started, add the second candidate to the same suite:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py --models efficientnet_b0 --run-dir "data/experiments/<timestamp>"
```

If EfficientNet already has an incomplete model directory, resume its `last.pt` instead. Completed model directories are protected against accidental replacement.

## Selection, threshold, and final evaluation

Checkpoint and candidate ranking use **validation ROC-AUC**, with lower validation cross-entropy breaking exact ties. At the end of each candidate run, a decision threshold is selected from validation scores to maximize balanced accuracy subject to a configured **validation sensitivity target of 0.95**. This is an experiment policy, not a clinically validated operating point or guaranteed test sensitivity. Probability calibration has not been established.

`data/experiments/<timestamp>/comparison.json` ranks completed candidates and recommends a checkpoint. `suite_plan.json` records the requested candidates. If only one has completed, the comparison lists pending models and final evaluation refuses to run until the plan is complete. A suite with final test results cannot accept more training candidates. Selection never reads test predictions, changes `.env`, or overwrites the live model.

After reviewing the completed validation results, the selected candidate can receive one final test evaluation:

```powershell
.\.venv\Scripts\python.exe -u scripts/evaluate_experiment.py --suite "data/experiments/<timestamp>"
```

This verifies the selected checkpoint hash and source manifest, uses the saved preprocessing/threshold, and writes `final_test_results.json`. Existing final results are protected from accidental reruns. Do not try different candidates or thresholds on test to choose the winner. Model promotion, API compatibility, and UI labeling should be reviewed after the results are known.

The current pinned-runtime checkpoint-loading limitations in [the backend review](BACKEND_REVIEW.md) remain relevant. These tools should load only the trusted local artifacts they produce or trusted official pretrained weights; model training does not resolve deployment security or input-suitability validation.

## Rebuilding preparation for another dataset version

The local manifest is already created. Do not rerun preparation to start the current training run. For a genuinely new reviewed source version, preserve prior audits, generate a fresh audit, and choose a new output directory:

```powershell
.\.venv\Scripts\python.exe -u scripts/audit_dataset.py --data-dir data --output data/review/new_audit.json
.\.venv\Scripts\python.exe -u src/prepare_dataset.py --data-dir data --audit data/review/new_audit.json --previous-audit data/review/dataset_audit.json --output-dir data/prepared/new-version
```

Preparation verifies the source file list/hashes, rejects conflicting duplicate labels and unrecognized subject names, reserves test-connected components, deduplicates exact pixels, and refuses a nonempty destination. Set a copied experiment configuration's `manifest` to the new file and keep its results separate. Missing audit files trigger a fresh audit rather than an unaudited split. No raw images are edited.
