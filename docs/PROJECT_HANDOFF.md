# PulmoScan: current scope and final review

Decision recorded 13 November 2026: **finish and review the current educational screening prototype, then freeze feature scope.** Defer the restricted finding dataset, object detector and generated medical reports unless the team chooses to resume them. No new download, training run or dependency is required for the current explanation feature.

The subsequent [final application review](FINAL_REVIEW_2026-11-13.md) records authentication, upload, privacy and dependency fixes. Maintained dependency pins and the local runtime were updated; no dataset or retraining is needed.

## What the project demonstrates

- Role-based practitioner access, protected image retrieval and encrypted scan storage.
- Image-level NORMAL/PNEUMONIA screening, model identity, class scores and explicit score limitations.
- Patient-linked scan histories and follow-up images, patient record management and account editing.
- Laptop-readable light/dark interfaces, enlarged X-ray inspection and zoom.
- Optional Grad-CAM with image-specific numbered contribution regions, linked text, opacity and Original/Heatmap views.
- Reproducible Kaggle classifier workflows, artifact fingerprints, model evaluation and isolated automated tests.

These address the project's software workflow and image-classification scope as an academic prototype. An actual institutional rubric was not provided, so confirm its required deliverables before declaring the assignment complete. The project does **not** demonstrate definitive diagnosis, clinical deployment readiness, lesion detection, lung-lobe localization, disease severity or clinician-level report generation.

## The minimal explanation we are shipping

The optional explanation uses the already loaded model and the actual scan. Numbered image sections and text summarize positive contributions to the selected class score. They are not invented medical observations. No language model, remote image service, added training or extra infrastructure is involved.

The viewer distinguishes:

- **PNEUMONIA:** highlighted areas contributed to this class score; they do not confirm pneumonia in those locations.
- **NORMAL:** highlighted areas contributed to this class score; they do not establish absence of abnormalities.
- **Broad map:** contributions are spread across the image; numbered sections are reading aids, not separate lesions.
- **No spatial signal:** keep the screening result, show the original image and explain that no useful spatial pattern is available.

Original/Heatmap controls, opacity, linked numbered notes and zoom stay available when applicable. More technical interpretation is behind **How to read this explanation** and **Explanation details**. High model scores do not establish accuracy, calibrated clinical probabilities, severity or explanation reliability. [Grad-CAM method](https://arxiv.org/abs/1610.02391), [saliency-map evaluation research](https://arxiv.org/abs/1810.03292).

## Final manual review

Start the app yourself from the project root:

```powershell
npm.cmd run dev
```

1. Sign in as staff and upload a de-identified X-ray. Open its scan and run screening. Verify that the result, model scores and image are readable in both themes.
2. Select **Explain prediction**, inspect the image-specific numbered notes, and open **How to read this explanation**. No new dataset is needed for this operation. If a selected sample produces no informative map, verify the explicit no-signal message instead of expecting artificial highlights.
3. Select a note, switch to **Original**, and select a note again. Highlights disappear in Original; the note restores its corresponding heatmap region. Test the same sequence in the enlarged viewer and check that its mode label is accurate.
4. Review a different permitted image and compare its result/map. Re-run screening to verify that an old explanation clears. Incorrect classifier predictions remain possible; the heatmap is not evidence that the model is right.
5. Upload a follow-up under the same patient ID. Verify that the latest upload governs the current screening status while previous scans remain in history. Test edits/deletion only with your own disposable records.
6. Check staff/radiologist access boundaries, account editing, logout and login-page behavior. Refreshing or closing the tab should require authentication again while preserving the selected portal preference.

After your review and any assignment-specific checks, review the Git diff and commit the changes yourself. The assistant does not start services, train models or commit on your behalf.

## Model and completion limits

The existing configured DenseNet121 remains active; the downloaded Kaggle candidates remain separate. No checkpoint was promoted as part of explanation polishing. See [model inventory and storage](PATIENT_WORKFLOW_AND_STORAGE.md), [model review](MODEL_REVIEW_2026-11-10.md), and [calibration/external validation](CALIBRATION_AND_EXTERNAL_VALIDATION.md) for results and remaining weaknesses. Adding nicer explanations does not improve classifier accuracy or resolve independent validation.

Verification uses `python -m pytest tests -q` (or `python -m pytest -q`, now configured to discover that folder), `npm.cmd test`, `npm.cmd run lint`, and `npm.cmd run build` in `frontend/` for the npm checks. These do not replace your browser review. The old manual `src/evaluate_test.py` evaluator is outside this automated suite; on this PC its scikit-learn import currently fails with **"An Application Control policy has blocked this file"** for `_radius_neighbors`. That optional legacy evaluator remains unavailable unless the installed dependency/security-policy issue is resolved. The app inference and Grad-CAM paths do not import it; no Windows security policy was modified.

Final results on 13 November 2026: **232 backend tests and 106 frontend tests passed; lint, the production build and development preflight passed.** The final review also records eight CPU/CUDA prediction/explanation checks and clean dependency checks. The Vite configuration-format warning is resolved. Remaining warnings are the Starlette `httpx` test adapter deprecation and the intentional Pillow decompression-bomb test. No live browser review, app server startup or real model training was performed by the assistant.

If the requirement is "secure educational X-ray screening with reviewable AI output," I recommend ending feature development after this final review. If the requirement is "reliable medical diagnosis and finding localization," that goal remains unmet and requires a separate labelled-data and clinical-validation phase. The old runtime advisory findings were addressed by the final dependency update; this is not a clinical or production-deployment certification.

An accurate resume statement is: **Built a role-based chest X-ray screening application with encrypted image storage, reproducible PyTorch/Kaggle experiments, and on-demand Grad-CAM explanations with linked image-region notes and automated checks.** Use only measured metrics with their exact dataset/protocol; avoid claims of doctor-level diagnosis or clinical validation.

The [finding-model proposal](FINDING_MODEL_NEXT_STEPS.md) and annotation-check notebook are future research references, not outstanding tasks for this delivery.
