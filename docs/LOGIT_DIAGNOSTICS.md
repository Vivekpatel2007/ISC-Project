# Inspect the existing v2 checkpoint without retraining

The returned diagnostic ZIP has now been verified: raw-margin benchmark AUC is **0.97321**, while predictions remain **86.57% accuracy, 81 false positives, and 2 missed pneumonia images**. All 2,044 saved probabilities reproduced exactly. The next work is documented in [calibration and external validation](CALIBRATION_AND_EXTERNAL_VALIDATION.md); another diagnostic or training run is not needed to fit the development-only temperature profile.

Use **[kaggle/PulmoScan_Logit_Diagnostics.ipynb](../kaggle/PulmoScan_Logit_Diagnostics.ipynb)** for the next step. This notebook runs inference on the saved, validation-selected DenseNet121 only. It does not fit a model, choose another candidate, search thresholds, download ImageNet weights, deploy a model, or alter the original results.

## Why this step is needed

On the reviewed 618-image benchmark, v2 recorded 86.57% accuracy, 81 false-positive normal images, and 2 missed pneumonia images at its saved threshold. **75 normal images and 385 pneumonia images received a float32 probability score of exactly 1.0.** The recorded probability-based ROC-AUC was 0.83648 and the logit-based cross-entropy loss was 5.20460.

Once many different outputs round to the same probability, their relative ordering is lost. Binary ROC-AUC can instead use the non-thresholded decision score `logit(PNEUMONIA) - logit(NORMAL)`, preserving information that the float32 softmax representation discarded. Both probabilities and decision values are supported by [scikit-learn's ROC-AUC API](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html). Stable log probabilities are computed directly from logits using [PyTorch log_softmax](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.log_softmax.html).

This is a measurement investigation. A higher raw-margin AUC would **not** fix the 81 false positives at the saved operating point, prove that the scores are calibrated, establish generalization, or justify a new threshold chosen on the benchmark.

## Run on Kaggle

1. Create a **new Kaggle notebook** and import `kaggle/PulmoScan_Logit_Diagnostics.ipynb`.
2. Attach the original `paultimothymooney/chest-xray-pneumonia` dataset.
3. Attach your saved v2 notebook output containing suite **`kaggle-v2-20261110T094413Z`**. Alternatively, create a **private** Kaggle dataset from the downloaded **`pulmoscan_models (3).zip`** and add that input. The tool supports the ZIP itself or its unpacked `bundle.json` / `suite/` directory tree. You do not need both representations.
4. Select an available GPU for inference. Internet can remain off when the standard torch, torchvision, NumPy, scikit-learn, and Pillow libraries are present. No pretrained download is required. Set `REQUIRE_GPU=False` deliberately if using CPU instead.
5. Keep `SUITE_NAME='kaggle-v2-20261110T094413Z'`. Leave `ARTIFACT_PATH=None` and `DATA_ROOT=None` for automatic discovery; set them explicitly if the input paths are ambiguous. The artifact path can be a ZIP, an unpacked bundle root, or the suite folder directly containing `comparison.json`.
6. Keep `PRECISION='saved'`. This follows the saved model's AMP preference on CUDA. `INCLUDE_REVIEWED_BENCHMARK=True` deliberately inspects the already observed benchmark errors; set it False for validation/calibration only. There is no threshold search or model comparison on the benchmark.
7. Use **Run All in this diagnostic notebook**. There are no training cells. Download **`pulmoscan_diagnostics.zip`** and send it back for review. Save the notebook version including output files before ending the session.

Adding saved notebook outputs or model ZIPs does not resume training. The diagnostic workspace is `/kaggle/working/pulmoscan_diagnostics/`, separate from both training workspaces. The input data and original checkpoints remain read-only. Dataset mounts can differ from the original run only if all saved source file hashes still match; the original manifest is never rewritten.

For general Kaggle input/output controls see [Kaggle's notebook documentation](https://www.kaggle.com/docs/notebooks). GPU availability and account requirements are controlled by Kaggle.

## Outputs

| File | Contents |
| --- | --- |
| `diagnostic_results.json` | Probability AUC and raw-margin AUC, stable logit loss, fixed-threshold metrics, saturation counts, reference agreement, and runtime metadata |
| `val_predictions.csv`, `calibration_predictions.csv`, optional `test_predictions.csv` | Original paths/labels/hashes, both logits, raw margins, float32 scores, stable log probabilities, per-image loss, and predictions at the unchanged threshold |
| `logit_distributions.png` | Fixed-model margin distributions by class and split |
| `false_positive_examples.png` | Up to 12 incorrect normal images, ordered by raw margin, labelled with the saved-cut prediction and original label |
| `README_results.md` | Compact metric summary and interpretation limits |
| `diagnostic_source_index.json` | Exact embedded diagnostic source hashes |
| `diagnostic_bundle.json` | Checksums of every file in the diagnostic ZIP |

The image gallery uses public benchmark images. No anatomical assessment or clinical diagnosis is made. Matplotlib is optional: if unavailable, CSV/JSON results are still produced.

`reference_comparison` reports probability differences and changed decisions relative to the saved predictions. The old float32 decision is retained, and softmax is computed on the inference device before copying scores to CPU. Different devices, kernels, framework versions, or precision can still change results. Inspect reference agreement before claiming exact reproduction. The optional `PRECISION='fp32'` is for a separately labelled numerical-sensitivity diagnostic; do not select whichever mode gives the best benchmark score.

Any included test results are labelled `previously_reviewed_benchmark`. They are not a fresh independent evaluation. No original CSV/JSON/checkpoint is overwritten. New output directories and ZIP names preserve earlier evidence.

## Local equivalent on verified sources

The current laptop source tree has unresolved integrity failures. Do not run against altered bytes or regenerate the original manifest to accept them. On a system with a verified identical source copy, replace the paths below:

```powershell
.\.venv\Scripts\python.exe scripts/inspect_checkpoint.py --artifact "C:\Users\cubes\Downloads\pulmoscan_models (3).zip" --data-dir data/clean_chest_xray --output data/review/logit_diagnostic --include-reviewed-benchmark --device auto --export data/review/pulmoscan_diagnostics.zip
```

`--device auto` uses a working GPU or CPU fallback. `--device cpu` selects CPU explicitly. A diagnostic never starts frontend/backend servers. Only trusted locally produced checkpoints should be loaded; source files contained in model ZIPs are treated as data and are not executed.

## Repository changes

- Shared operating metrics moved to `src/scoring.py`. Historical result files and saved run configurations remain unchanged. Updated fresh-run profiles now explicitly use raw-margin ROC-AUC for checkpoint ranking; legacy saved profiles retain their original probability-AUC rule.
- `scripts/inspect_checkpoint.py` adds fixed-model, fixed-threshold logit inspection and checked diagnostic exports.
- Future executions of `scripts/evaluate_experiment.py` now additionally save raw logits, margins, saturation counts, and `roc_auc_logit_margin`. Its existing `metrics.roc_auc` field remains probability-based for compatibility. Existing results remain protected from overwriting.
- Future training fingerprints include `src/scoring.py` and record the file list explicitly. Existing Kaggle runs must be resumed with their original notebook/source versions.

The notebook builder and automated tests compile all diagnostic cells, verify the source bootstrap, test an analytical saturation example, exercise read-only inspection on synthetic data, verify ZIP checksums, and check input discovery. No full-model training or real benchmark inference is started by these tests.
