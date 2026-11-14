# Result locations

This is a **legacy output directory**, not the maintained pipeline's active experiment folder. No evaluation or training is required to run the saved-model app.

| Artifact | Location |
| --- | --- |
| Checked-in default application model | `models/densenet121_pneumonia_best.pth` |
| Training/checkpoint/history artifacts and imported candidates | `data/experiments/<run>/` |
| Dataset audit, diagnostics and verification evidence | `data/review/` |
| Prepared source manifests | `data/prepared/<protocol>/` |

Ignored experiment artifacts do not accompany a normal code-only clone; back them up separately. Preserve the cohort manifest, checkpoint hash, preprocessing, cutoff and runtime alongside each metric. Do not describe an old plot as a new result. See [current model inventory](../docs/PATIENT_WORKFLOW_AND_STORAGE.md), [saved model metrics](../docs/CALIBRATION_AND_EXTERNAL_VALIDATION.md) and [final application verification](../docs/FINAL_REVIEW_2026-11-13.md).

Historical generated plots, metrics, threshold files, and model-evaluation reports were removed before the new training runs. They remain recoverable from Git history.

New training outputs are isolated under `data/experiments/<timestamp>/<model>/`, including `train.log`, `history.json`, `best.pt`, and `last.pt`. Suite comparisons and final test results live in the timestamped suite directory. See [the manual training guide](../docs/TRAINING.md).

Preserve the relevant audits under `data/review/` and exact prepared manifests under `data/prepared/<protocol>/` when reproducing an experiment. These preparation records are not required for normal saved-model app startup. Checkpoints under `models/` are retained until a reviewed replacement is deliberately promoted.

This directory is reserved for explicitly invoked legacy tools. Newly generated legacy outputs are ignored by Git; the active training runner does not read or write them.
