# v2 compression-robustness experiment

The v2 diagnostics have since been returned and verified. See [calibration and external validation](CALIBRATION_AND_EXTERNAL_VALIDATION.md) for the current development-only postprocessing results and the remaining need for separate data. No additional network training is needed for that work. Fresh-run configs now explicitly rank checkpoints by raw logit-margin AUC; the archived v2 experiment below used its original probability-AUC rule.

**Completed benchmark and diagnostic stage:** accuracy was 86.57%, with 81 false positives and 2 missed pneumonia images. [Inference-only diagnostics](LOGIT_DIAGNOSTICS.md) confirmed that score saturation hid ranking information: raw-margin AUC was 0.97321. Keep these outputs fixed.

Use **[kaggle/PulmoScan_Training_v2.ipynb](../kaggle/PulmoScan_Training_v2.ipynb)** for the next Kaggle experiment. Keep your completed v1 notebook and downloaded ZIPs unchanged. The [model review](MODEL_REVIEW_2026-11-10.md) explains the evidence and its limitations.

## Run on Kaggle

1. Create a **new notebook/session** and import `kaggle/PulmoScan_Training_v2.ipynb`.
2. Attach `paultimothymooney/chest-xray-pneumonia` using **Add Input**. Select an available GPU and enable Internet for the official pretrained weights.
3. Leave `PROFILE='v2'`, `DATA_ROOT=None`, and **`RUN_FINAL_TEST=False`**. Leave `RESUME_SOURCE=None` for the first run. The notebook uses `/kaggle/working/pulmoscan_training_v2/` and a `kaggle-v2-...` suite name, separate from v1 outputs.
4. Run cells in order. It audits the actual Kaggle inputs and makes a new manifest at `data/prepared/robustness-v2/manifest.json` without copying, modifying, or re-encoding source files.
5. It trains DenseNet121 and EfficientNet-B0 sequentially, then selects thresholds on their separate calibration holdout. Inspect the **validation and calibration results**, and download the exported model ZIP. Save the notebook version with output files before ending the session.

No local training or servers are started by the assistant. Kaggle availability, runtime settings, file downloading, and output saving are covered in [the general Kaggle guide](../kaggle/README.md).

## What changed

| Part | v1 | v2 |
| --- | --- | --- |
| Eligible development pool | Approximately 85% training / 15% validation | Approximately 70% training / 15% selection validation / 15% threshold calibration |
| Checkpoint/early stopping | Validation ROC-AUC, validation loss breaks exact ties | Same; calibration is not used to select epochs or models |
| Threshold data | Same validation predictions used during selection | Separate calibration predictions, read after checkpoint selection finishes |
| Training augmentation | Mild affine + brightness/contrast | Same, plus random JPEG variation at 224px |
| Inference preprocessing | Grayscale, full-field letterbox, ImageNet normalization | Same |
| Existing test benchmark | Already inspected | Preserved and explicitly labelled as previously reviewed |

JPEG variation applies to both classes with probability 0.75 and quality 40–95, entirely in memory after resizing/augmentation. It is intended to test sensitivity to encoding-related cues. There are no random anatomy crops, source-image edits, test-time augmentation, or changes to the old model's threshold. It is not established that JPEG variation improves this problem. A controlled future ablation can use `augmentation_profile='standard'` with the same v2 split; choose any experiment using development validation, not benchmark results.

The calibration split is held out from **this run's** optimizer, checkpoint selection, and early stopping. It is threshold calibration, not probability calibration. Do not repeatedly choose architectures/settings using calibration results and still describe it as independent of that choice. The pool itself has been used in earlier experiments; this is not a new external dataset.

The calibration sensitivity target remains 0.95. Metrics on validation and calibration may disagree, and that disagreement is useful evidence. Do not force a threshold to make either report look good. No generalization improvement or accuracy percentage is promised before the experiment runs.

## Output and review

The ZIP includes both `best.pt` checkpoints and the existing validation summaries, plus:

- `<model>/calibration_predictions.json`: unrounded scores from the separate threshold holdout.
- `<model>/calibration_summary.json`: threshold-fit metrics, loss, and manifest identity.
- Checkpoint/summary `threshold_split='calibration'` and saved threshold provenance.
- A manifest with four disjoint splits and `test_role='previously_reviewed_benchmark'`.

Model ranking still uses validation ROC-AUC; the calibration summaries do not change the ranking rule. Use the reviewed bundle/import workflow in [kaggle/README.md](../kaggle/README.md) to bring outputs back. No downloaded candidate replaces the live API model automatically.

## The old benchmark cannot become fresh again

Leave `RUN_FINAL_TEST=False` while reviewing the next experiment. The original 618-image results are fixed: 81.39% accuracy, 115 false-positive normal images, and no missed pneumonia images at the saved v1 threshold.

If you deliberately need a diagnostic repeat, set `RUN_FINAL_TEST=True` and run only the settings, benchmark, and export cells. The notebook passes `--allow-reviewed-benchmark`; the resulting report records `evaluation_role='previously_reviewed_benchmark'` and a caveat. This result is **not** a new unbiased final performance estimate. Do not use repeated benchmark scores to choose the winning model or threshold. Obtain an independent source/patient holdout for final claims after these changes.

## Local CPU/GPU workflow

The same code supports local GPU training and CPU fallback. The current laptop dataset still has an unresolved checksum failure, so do not use a fresh audit merely to accept those damaged bytes. Use independently restored/verified sources. With a clean source at `data/clean_chest_xray/`, create a fresh audit and v2 manifest:

```powershell
.\.venv\Scripts\python.exe scripts/audit_dataset.py --data-dir data/clean_chest_xray --output data/review/clean_v2_audit.json
.\.venv\Scripts\python.exe src/prepare_dataset.py --data-dir data/clean_chest_xray --audit data/review/clean_v2_audit.json --output-dir data/prepared/robustness-v2 --train-ratio 0.70 --calibration-ratio 0.15
.\.venv\Scripts\python.exe scripts/check_training_data.py --manifest data/prepared/robustness-v2/manifest.json --passes 2
.\.venv\Scripts\python.exe scripts/train_models.py --config configs/train_robustness_v2.json --check
```

After those checks pass, manually start training:

```powershell
.\.venv\Scripts\python.exe -u scripts/train_models.py --config configs/train_robustness_v2.json
```

The local profile keeps physical batch 2 / accumulation 8; Kaggle uses 16 / 1. Both have effective batch 16. Existing v1 manifests, profiles, and reports remain supported. Resume a run with its original notebook/source versions and configuration, rather than mixing v1 artifacts with v2 code.
