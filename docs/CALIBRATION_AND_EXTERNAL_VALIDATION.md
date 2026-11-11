# Stable scoring, postprocessing, and external validation

The v2 diagnostics confirmed a numerical reporting issue: on the same 618 reviewed images, probability ROC-AUC was 0.83648 while raw-logit-margin ROC-AUC was **0.97321**. Predictions still contained **81 false positives and 2 false negatives**, with **86.57% accuracy**. Numerical reporting and probability calibration must not be presented as fixes for those classification errors.

## Changes in the backend and training tools

- The inference engine now returns full-precision `logit_margin`, `log_probability_normal`, and `log_probability_pneumonia` alongside the existing response fields. It explicitly reports `probabilities_calibrated=false` and `score_interpretation='uncalibrated_model_score'`.
- Existing API decisions, rounded probability fields, decision threshold, database behavior, live model file, and `.env` are preserved. The experimental temperature profile described below is **not loaded by the API**.
- Fresh training profiles explicitly use `ranking_score_space='logit_margin'` and record `selection_metric='val_logit_margin_auc'`. Probability-based AUC remains available as a separate diagnostic. This avoids selecting checkpoints using ranking information lost to float32 softmax saturation.
- Saved legacy run configurations without that field retain their old probability-AUC behavior. Suites cannot mix the two ranking criteria. Resume old Kaggle runs with their original notebook/source versions.
- Future validation predictions also store raw margins. Existing downloaded artifacts and benchmark reports were not rewritten. No new neural-network training is needed to use the completed diagnostic CSVs.

## Temperature-only development experiment: 11 November 2026

A single positive temperature was fitted from saved **calibration** logits. The fit uses deterministic class-balanced candidate-group splits: **499 temperature-fit images / 214 temperature-check images**, with seed 2026. The raw network weights and original raw-margin decision boundary remain fixed. The model-selection validation set is assessed descriptively; the benchmark CSV is not parsed for fitting or assessment. ZIP members are checksum-verified, including members that are not used in fitting.

The fitted temperature is **4.835636650248675**. The old probability threshold corresponds to raw-margin boundary **11.274227471859334**. After scaling scores by that temperature, the equivalent display-probability threshold is approximately **0.91145148**. It represents the same raw decision boundary, not a newly optimized threshold.

That transformed probability threshold applies only to temperature-scaled scores. Do not substitute it for the API's current threshold while using unscaled scores. The frozen raw-margin boundary is the authoritative decision policy for the experimental profile.

| Development check | Before temperature scaling | After |
| --- | ---: | ---: |
| Temperature-check NLL, 214 images | 0.16556 | **0.04782** |
| Temperature-check Brier score | 0.01852 | **0.01550** |
| Temperature-check binned ECE | 0.01834 | 0.01541 |
| Model-selection validation NLL | 0.02147 | 0.01293 |
| Model-selection validation Brier score | 0.00346 | 0.00327 |
| Model-selection validation binned ECE | 0.00431 | 0.00666 |

The fit/check group sets are disjoint. No decisions changed when expressing the original boundary as a margin on any of the fit/check/validation rows. The check subset is held out from temperature fitting, but it participated in the earlier threshold experiment. This is not a new external test. Some metrics improve while binned validation ECE increases; do not claim that every calibration measure improved.

Temperature scaling is a one-parameter postprocessing method, not network retraining. A positive temperature preserves score ordering; it cannot repair domain shift, improve raw-margin ROC-AUC, or remove false positives at a fixed raw decision boundary. Its effectiveness must be checked on representative, independently held-out data. Primary references: [Guo et al., On Calibration of Modern Neural Networks](https://arxiv.org/abs/1706.04599), [scikit-learn probability calibration](https://scikit-learn.org/stable/modules/calibration.html).

The local, ignored outputs are:

```text
data/review/postprocessing_20261111/postprocessing_profile.json
data/review/postprocessing_20261111/development_assessment.json
```

The profile is bound to the exact v2 checkpoint and original manifest. It is labelled `experimental_not_promoted` and `independent_validation_required=true`. It does not change any `.pt` file or API configuration.

To reproduce using a **new** output directory, from the project root:

```powershell
.\.venv\Scripts\python.exe scripts/calibrate_saved_logits.py --diagnostics "C:\Users\cubes\Downloads\pulmoscan_diagnostics.zip" --model-artifact "C:\Users\cubes\Downloads\pulmoscan_models (3).zip" --output data/review/new_postprocessing_review
```

This performs a bounded convex optimization of one scalar on CPU using saved numbers. It does not load images, execute the model, run a neural optimizer, start services, or use benchmark scores to choose a parameter. The original model ZIP and diagnostic ZIP remain unchanged.

## Independent validation is still pending

Only the original Kaggle dataset is currently available. Re-splitting it, downloading another mirror, or tuning on the already reviewed benchmark does not create an independent external cohort.

Prepare genuinely separate, labelled **PNG/JPEG** images and a CSV based on [the template](examples/external_labels.csv):

```csv
path,label,patient_id,source_id
NORMAL/example_normal.png,NORMAL,real_pseudonymous_patient_a,actual_source_identifier
PNEUMONIA/example_pneumonia.png,PNEUMONIA,real_pseudonymous_patient_b,actual_source_identifier
```

The template contains placeholders, not real data. Labels must be supported by the source annotations; other diagnoses or ambiguous findings must not silently be mapped to NORMAL. Record the actual origin, label basis, acquisition/rendering process, and stable pseudonymous source/patient identifiers. Freeze the model, profile, and sampling plan before using new holdout labels for assessment. If any new-source examples are used to adapt the model, reserve other patient/source groups for subsequent validation.

The preparation tool:

1. Fully decodes every supplied image and checks the existing input constraints.
2. Records byte/pixel hashes, source/patient IDs, class counts, and provenance.
3. Rejects exact byte **or decoded-pixel** overlap with all images recorded in the old manifest, including excluded original images.
4. Rejects repeated paths and duplicates inside the new cohort, without silently removing them.
5. Labels the manifest as a **candidate** external cohort. Hash checks cannot establish true patient independence, near-duplicate absence, label validity, or authentic source provenance.

Example setup after obtaining and reviewing the new data:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_external_validation.py --labels data/external_labels.csv --data-dir data/external_images --reference-artifact "C:\Users\cubes\Downloads\pulmoscan_models (3).zip" --output data/prepared/external_candidate.json --source-description "Actual source, acquisition details, annotation basis, and cohort sampling plan"
```

Then evaluate the already frozen checkpoint/profile, without fitting anything on external labels:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_external_validation.py --model-artifact "C:\Users\cubes\Downloads\pulmoscan_models (3).zip" --manifest data/prepared/external_candidate.json --profile data/review/postprocessing_20261111/postprocessing_profile.json --output data/review/external_validation --device auto
```

`--device auto` selects a working GPU or CPU fallback. The optional `--profile` is verified against the exact checkpoint, source manifest, and original boundary. The evaluator reports legacy probability decisions, stable raw-margin decisions, any numerical disagreement, probability-quality measures, and full raw predictions. It never chooses a threshold or candidate from external performance. Keep all outputs and identify any cohort reuse in subsequent experiments; an output-directory guard alone does not prevent research-design leakage.

### A possible source to review later

[VinDr-PCXR / PediCXR on PhysioNet](https://physionet.org/content/vindr-pcxr/1.0.0/) is a candidate additional pediatric source with 9,125 DICOM studies and radiologist-provided labels. The official page currently requires registration and a data-use agreement for file access. It is **not a drop-in input** for this JPEG/PNG workflow: access conditions, exact label mapping, age/view inclusion criteria, patient independence, and a reproducible DICOM rendering/conversion process need review first. No account was accessed and no dataset was downloaded. See also [the source paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10133237/).

This is an option for obtaining additional evidence, not a statement that the current model is validated on that dataset.
