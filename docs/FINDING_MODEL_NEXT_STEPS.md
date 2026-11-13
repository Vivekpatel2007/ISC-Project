# Next phase: findings, locations and grounded descriptions

**Deferred on 13 November 2026 at the user's request. No dataset download, access application, upload or training is needed now.** The team may revisit this plan later. The current delivery uses the existing model with [Grad-CAM image/text explanations](EXPLAINABILITY.md); see the [project handoff](PROJECT_HANDOFF.md).

The proposal below was recorded on 11 November 2026 and applies only if this phase is resumed. The finding detector and its training notebook are not implemented. The included notebook checks training annotation CSVs only.

## Recommended approach

Add a separate finding detector, then generate controlled text from its actual finding labels and boxes. Retain the existing screening result as a separate output. This allows a clinician to inspect what was detected, where it was detected, and whether the finding supports their interpretation.

For the initial research baseline I recommend **Torchvision Faster R-CNN with a ResNet-50 FPN backbone**. It fits our PyTorch codebase and returns finding classes, scores and boxes. The exact variant, resolution and batch size will be selected after data inspection and GPU memory measurement. This is a baseline choice, not a claim that it is the most accurate model. Compare a lighter detector if laptop latency or memory is unacceptable. [Official model documentation](https://docs.pytorch.org/vision/stable/models/faster_rcnn.html).

Start with common, sufficiently annotated findings actually present in the downloaded label vocabulary. Do not invent labels for consolidation, opacity or effusion, merge them automatically, or interpret disease-level labels as finding boxes. Low sample counts may require fewer classes or more data.

The eventual flow is:

```text
Authorized X-ray -> finding detector -> classes + boxes + scores
                                    -> deterministic finding descriptions
                                    -> clinician review/edit/approval
```

For example, IF a future validated detector returns an opacity box, a draft could say: **"Possible opacity in the marked region. Review this finding alongside the screening output and clinical information."** This is a proposed template, not an observation made by our current model. No-box output must not automatically become "normal." Disagreement between screening and detection should remain visible.

Displayed-image coordinates can be described. Patient left/right, lung lobes, severity, cause, progression and definite diagnosis require appropriate supervision and verified orientation/context. Current Grad-CAM text describes score contributions only. Neither component establishes a clinician's reasoning or a definitive pneumonia diagnosis.

## First-choice data

Use the official **[VinDr-PCXR / PediCXR resource](https://physionet.org/content/vindr-pcxr/1.0.0/)** and its [research paper](https://www.nature.com/articles/s41597-023-02102-5). It is pediatric and provides radiologist finding boxes plus image-level labels. The release describes `train/`, `test/`, `annotations_train.csv`, `annotations_test.csv`, `image_labels_train.csv`, and `image_labels_test.csv`; images are DICOM. Obtain the full authorized release, including annotation documentation. Verify the downloaded schema/version before conversion; the landing page has inconsistent boilerplate, so it is not enough to hard-code a clinical vocabulary.

The current Paul Mooney NORMAL/PNEUMONIA folders do not supply finding boxes or reports. Repeating their training cannot create supervised finding localization. Keep those data and previous models for the existing task; do not combine their binary labels with finding-detector targets.

## Steps only if the team resumes this phase

1. Open the official PhysioNet resource, create/sign in to your own account, and complete its listed access steps and data-use agreement. Check the live **Files** section for your account's requirements; do not assume another dataset's credentialing requirements apply.
2. Download the authorized release into **`data/vindr-pcxr/`** if working locally. The root `data/` folder is already ignored by Git. Do not place it under `models/`, application scan storage, or tracked `kaggle/` sources. Preserve the original files and splits.
3. Run the CSV intake check below. It needs only standard Python and the two **training** CSVs; GPU, image conversion and dependency installation are unnecessary.
4. Inspect the generated report locally. Tell me where the authorized files are, or provide the aggregate class counts/schema if your agreement permits sharing those. Do not share account credentials or restricted image/annotation examples.
5. We then implement and verify DICOM preprocessing, visual box checks, leakage-safe development splits, selected classes, and the Kaggle detector training/export notebook against the actual release. **Do not use the old `PulmoScan_Training*.ipynb` notebooks to train a finding detector.**

The resource's [license](https://physionet.org/content/vindr-pcxr/view-license/1.0.0/) and [agreement](https://physionet.org/content/vindr-pcxr/view-dua/1.0.0/) restrict sharing access and require secure handling. **Private Kaggle visibility alone does not establish permission to upload or process these data there.** Confirm that your agreement and provider guidance permit the intended cloud arrangement before uploading images or annotations. If unclear, ask the provider using its official contact options; local inspection can proceed meanwhile. Do not publish a restricted dataset, notebook outputs containing it, or a public mirror. This project does not accept an agreement or upload data on your behalf.

### Local annotation check

With the existing environment, from the project root:

```powershell
.\.venv\Scripts\python.exe scripts/check_finding_annotations.py --annotations "data/vindr-pcxr/annotations_train.csv" --image-labels "data/vindr-pcxr/image_labels_train.csv" --output "data/review/finding_intake_01.json"
```

Adjust the paths if the release contains another enclosing directory. Use a new output filename on subsequent runs: the tool refuses overwrites. It prints and saves schema, SHA-256 fingerprints, class counts, valid boxes, and structural issues. It does not export image identifiers or example rows. A blocked report returns exit code 2. A successful check returns **`needs_review`**, never training approval.

This checker expects the documented `image_id`, `class_name`, `x_min`, `y_min`, `x_max`, `y_max` box columns and an `image_id` image-label column. Optional class IDs are checked for mapping conflicts. It rejects unsupported schemas rather than guessing. It does not validate image-level label meanings, decode DICOM, check box/image dimensions, establish negative images, detect duplicate pixels, or approve development splits. Test files are not discovered or opened automatically.

### Kaggle annotation check, only where permitted

Import **[PulmoScan_Finding_Data_Check.ipynb](../kaggle/PulmoScan_Finding_Data_Check.ipynb)** into a permitted private notebook. Attach the authorized input containing the two training CSVs through **Add Input**. Set `DATA_ROOT` to the directory directly containing them, or leave `None` if only one matching dataset is mounted. Run the cells in order. Use CPU; Internet and extra packages are unnecessary. It embeds its own checker, reads no images, performs no training, and writes a timestamped `pulmoscan_finding_intake_*.json` report under `/kaggle/working/`. Keep reports private until their sharing terms have been checked.

Notebook maintenance:

```powershell
.\.venv\Scripts\python.exe kaggle/build_finding_data_check.py
.\.venv\Scripts\python.exe kaggle/build_finding_data_check.py --check
.\.venv\Scripts\python.exe -m pytest tests/test_finding_annotation_intake.py -q
```

## If that dataset is inaccessible

The **[official RSNA Pneumonia Detection Challenge](https://www.kaggle.com/c/rsna-pneumonia-detection-challenge/data)** is an alternative localization research task with DICOM images and bounding-box labels. It requires its own competition terms. It is not a substitute for a multi-finding pediatric release. Choosing it means implementing a separate schema adapter and explicitly reviewing population/task compatibility. Do not mount an arbitrary re-upload or merge it with the current classifier and call the combined system validated. The current intake tool deliberately does not accept RSNA CSVs.

## How we decide whether a trained model is better

- Audit the actual labels, missing annotations, source geometry, decoding and annotation completeness; inspect overlays before training. Preserve hash fingerprints and image preprocessing settings.
- Split the training pool into separate model-selection and operating-threshold/calibration subsets, with verified patient groups and duplicate checks. Keep the official test set untouched during development. Different data sources require provenance and independent evaluation; an in-source test is not external validation.
- Measure per-finding box AP, recall and false positives per image at chosen overlap thresholds; measure sensitivity at the selected operating point. Review normal cases, difficult negatives and missed findings. A detection score is not the probability that a patient has pneumonia.
- Check that every sentence agrees with the returned label/location and that no unsupported anatomical or causal details appear. Review clinically meaningful errors with qualified readers before making clinical claims.
- Measure peak GPU memory and single-image CPU/GTX 1650 latency, then compare alternatives against the same held-out protocol. Train on an available Kaggle GPU only in a permitted environment; available GPU types, memory and quotas vary. Current classifier hardware measurements do not establish the detector's requirements.
- Export weights, class mapping, preprocessing, thresholds, hashes, metrics and runtime versions together. Review locally before any serving integration or checkpoint promotion.

No new medical finding model has been trained, downloaded, installed or activated by this step. Existing scan records, settings and checkpoints are unchanged. There is no defensible "best accuracy" promise before measuring these outcomes.
