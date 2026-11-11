# Kaggle model review: validation/test gap

The completed `kaggle-20261110T025210Z` bundle passed checksum verification. Both checkpoints load strictly into their expected architectures and produce finite synthetic forward outputs locally. Saved predictions, labels, paths, and the selected threshold reproduce the reported metrics. The learned tensors and split assignments also match the earlier validation-only export; differing archive/checkpoint hashes include changed run metadata.

The current API checkpoint was not replaced. No training or additional real-image model inference was run during this investigation.

## Recorded results

DenseNet121 was selected by validation ROC-AUC, using epoch 7 and the validation-selected threshold `0.01807975023984909`.

| Metric | Validation: 713 images | Reviewed benchmark: 618 images |
| --- | ---: | ---: |
| Accuracy | 99.72% | 81.39% |
| Balanced accuracy | 99.80% | 75.11% |
| Pneumonia sensitivity | 99.61% | 100.00% |
| Normal specificity | 100.00% | 50.22% |
| ROC-AUC | 0.99998 | 0.92664 |
| False-positive normal images | 0 / 202 | 115 / 231 |
| Missed pneumonia images | 2 / 511 | 0 / 387 |

The large gap is a generalization concern. The correctly reproduced test report is not evidence of a CUDA or serialization failure. It does not establish the exact cause of poor transfer.

## Encoding/acquisition proxies are strongly associated with development labels

The original dataset audit was joined to the downloaded split manifest by **both relative path and exact byte SHA-256**. Metadata from four training images and one validation image did not match the Kaggle versions and was excluded from these statistics. The metadata analysis therefore covers 4,036 training, 712 validation, and all 618 benchmark images. Prediction-based metrics above still use every saved prediction.

| Split and class | Median file bytes | Median bytes / pixel |
| --- | ---: | ---: |
| Training NORMAL | 545,026.5 | 0.25344 |
| Training PNEUMONIA | 72,511.5 | 0.08013 |
| Validation NORMAL | 544,100.5 | 0.25466 |
| Validation PNEUMONIA | 72,072.0 | 0.08050 |
| Benchmark NORMAL | 173,513.0 | 0.08241 |
| Benchmark PNEUMONIA | 63,275.0 | 0.07819 |

Using **negative file size alone as a fixed score**, with no model fitting or pixel examination, produces validation ROC-AUC **0.99915**. Negative bytes per pixel alone produces **0.99941**. On the matching training metadata, those values are **0.99719** and **0.99862** respectively. No alternative metadata-based classifier or operating threshold was selected on the benchmark.

These are strong dataset clues. Normal benchmark files have a substantially different byte-density distribution from normal development files; that distribution is much closer to the pneumonia files. File size and byte density also depend on dimensions and image content, so they do **not** establish the actual JPEG quality or acquisition process. The CNN receives decoded/resized pixels, not file size. This analysis therefore does not prove it learned a compression shortcut; correlated image-processing or acquisition cues are a plausible hypothesis requiring controlled experiments.

False positives occur in both normal filename families: **29 / 69 `IM-*`** images and **86 / 162 `NORMAL2-IM-*`** images. Fixing just one filename family would not explain all errors. Filename-derived groups and exact pixel hashes were disjoint in the saved protocol, but near-duplicate and true patient independence remain unverified.

## Changes prepared for v2

1. Reserve approximately **70% training / 15% model-selection validation / 15% threshold calibration** inside the eligible development pool. Group/duplicate boundaries apply across all splits. The benchmark remains fixed.
2. Use validation only for checkpoint selection and early stopping. After selection finishes, read the separate calibration split to set the decision threshold. Report validation and calibration metrics separately.
3. Test **training-only JPEG variation** after resizing and the existing mild augmentations: probability 0.75, quality uniformly sampled from 40–95. Both classes receive the same random policy. Deterministic inference preprocessing stays grayscale, full-field letterboxing, and ImageNet normalization.
4. Mark any repeat of the 618-image benchmark as `previously_reviewed_benchmark` and require an explicit diagnostic flag. Do not present it as a new unbiased final holdout.

Separating threshold fitting from repeated checkpoint selection reduces development-set reuse. It does not itself correct a domain shift, and JPEG variation may help, do nothing, or harm performance. This is a new hypothesis-testing experiment, not a claim of improved accuracy. The 95% calibration sensitivity target is an experiment policy, not a clinical requirement or guarantee.

The old validation set was used for both checkpoint and threshold selection; its reported performance was therefore a development result. It was not an unbiased final estimate. Threshold fitting needs properly separated data, and repeated selection/evaluation needs careful holdout design. See the primary [scikit-learn threshold guidance](https://scikit-learn.org/stable/modules/classification_threshold.html) and [nested validation discussion](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html).

For the next run use [the v2 guide](TRAINING_V2.md). Keep the existing benchmark results unchanged. An independent source/patient holdout is still needed for final generalization claims after further development. Do not keep selecting preprocessing, models, or thresholds based on repeated benchmark scores.

## Reproduce the read-only diagnosis

From the project root, choose a new output directory:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_experiment.py --archive "C:\Users\cubes\Downloads\pulmoscan_models (1).zip" --audit data/review/dataset_audit.json --output data/review/new_diagnosis
```

The generated JSON records split metadata, metadata-only development AUCs, saved-score quantiles by filename family, and errors at the original saved threshold. It does not load model weights, fit a model, inspect alternative test thresholds, repair images, or overwrite an existing report. The existing local report is `data/review/diagnosis_v1_20261110/diagnosis.json` (ignored by Git).
