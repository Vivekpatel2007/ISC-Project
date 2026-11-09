# Result locations

Historical generated plots, metrics, threshold files, and model-evaluation reports were removed before the new training runs. They remain recoverable from Git history.

New training outputs are isolated under `data/experiments/<timestamp>/<model>/`, including `train.log`, `history.json`, `best.pt`, and `last.pt`. Suite comparisons and final test results live in the timestamped suite directory. See [the manual training guide](../docs/TRAINING.md).

Dataset integrity audits remain under `data/review/` and the prepared split manifest under `data/prepared/screening-v1/`. These are preparation records required by the current workflow, not old training results. Model checkpoints under `models/` are retained so the app can run until a reviewed replacement is promoted.

This directory is reserved for explicitly invoked legacy tools. Newly generated legacy outputs are ignored by Git; the active training runner does not read or write them.
