# Finalization and setup review — 16 November 2026

This pass preserves the model weights, cutoff, clinical scope, practitioner data and manual-startup policy. No application servers, real model training or dataset benchmark were started. Changes focus on setup compatibility, current documentation and presentation preparation.

## Changes

- Root overview/setup is now organized for a fresh checkout, with complete Windows PowerShell and Linux/WSL commands and repository-relative paths. No particular username, checkout directory or GPU model is required.
- The frontend toolchain's locked packages require a narrower Node range than the old `>=22`: both package manifests now declare **`^22.13.0 || ^24.0.0 || >=26.0.0`**, and both lockfiles are synchronized. The installed Node satisfies that range. Node 22.12, 23 and 25 were explicitly checked as excluded; 22.13, 24 and 26 as included.
- Development preflight error messages now show the correct environment-helper command for the operating system instead of a Windows-only path.
- The local setup guide explains compute/shared dependencies, both npm lockfiles, idempotent environment setup, checkpoint requirements, optional activation, manual launch and troubleshooting. It corrects the old suggestion that a CPU profile alone necessarily resolves a Windows native-DLL policy block.
- Component READMEs distinguish app operation from optional experiments and use general command examples. Historical local dataset counts/paths are not presented as requirements for a new reader.
- The existing private learning pack is retained, with a new challenges/tradeoffs chapter. It covers dataset, architecture, secure storage, backend flow, training/evaluation, actual metrics, Grad-CAM, limitations, presentation rehearsal and 65 evaluator questions. `/learning/` remains Git-ignored.

## Verification

| Check | Result |
| --- | --- |
| Backend suite | **232 passed** |
| Frontend suite | **106 passed** |
| Frontend lint and production build | Passed |
| Development preflight | Passed; working CUDA selected on the verification machine |
| Frontend npm audit | Zero known vulnerabilities returned |
| Lockfile synchronization | Both metadata-only updates completed without installing new packages |
| `pip check` | No broken requirements |
| Fresh shared-requirements resolution | `--dry-run --ignore-installed` completed with the documented compatibility constraints |
| Root/frontend `npm ci` dry runs | Passed with scripts disabled; no packages changed |
| Offline checkpoint check | Synthetic prediction succeeded on the selected CUDA device |
| Documentation checks | 127 relative links across 17 current README/setup/learning files; no missing targets/anchors or unclosed code fences |
| Learning-folder checks | All 11 study files ignored; none tracked; 65 evaluator questions retained |

Shared-dependency resolution evidence is under ignored `data/review/setup_resolution_20261116.json`. Resolution and npm dry runs are not a claim that an empty environment was fully installed or exercised on every platform. Actual runtime tests used the current Windows environment. The `--model` input was synthetic and did not produce a new clinical accuracy estimate.

Backend warnings were the existing supported-but-deprecated Starlette `httpx` test adapter and the deliberately triggered Pillow decompression-bomb warning. These did not fail tests. Linux commands and platform paths were reviewed against the installer/launcher implementation; the automation in this pass ran on Windows. No clean Linux installation, every-GPU compatibility test, live browser session or new clinical evaluation is claimed.

## Scope and handoff

Run `npm run dev` manually after setup (`npm.cmd run dev` in PowerShell). Review authentication, upload/screening, explanations, patient follow-up and profile editing in the browser before committing. API readiness is operational status, not medical validity.

The original DenseNet remains the configured default unless an operator deliberately changes its path. Candidate metrics and hashes retain their original cohort/provenance. No new accuracy claim follows from these setup/documentation checks. See [the main README](../README.md), [setup](LOCAL_SETUP.md), [model inventory](PATIENT_WORKFLOW_AND_STORAGE.md) and [the earlier hardening review](FINAL_REVIEW_2026-11-13.md).
