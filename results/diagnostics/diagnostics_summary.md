# Generalization Problem Investigation: Diagnostic Report

**Project**: AI-Based Pneumonia Detection from Chest X-Ray Images  
**Report Date**: Sat 10/24/2026  
**Dataset Examined**: `data/model_data` (derived from Kaggle Chest X-Ray / Kermany et al.)  
**Baseline Model**: DenseNet121 (`models/densenet121_pneumonia_best.pth`)  
**Validation Threshold**: 0.62

---

## 1. Executive Summary: Why Does the Model Generalize Poorly?

The held-out test evaluation revealed a stark performance drop:
- **Validation Balanced Accuracy**: 99.00% | **Test Balanced Accuracy**: 74.23%
- **Validation Normal Recall**: 98.51% | **Test Normal Recall**: 48.72%
- **Validation Pneumonia Recall**: 99.48% | **Test Pneumonia Recall**: 99.74%

Out of **234 NORMAL test images**, **120 were incorrectly flagged as PNEUMONIA** (False Positive Rate of 51.3%).

Our diagnostic suite identified four foundational root causes for this generalization gap:

1. **Patient Identifier & Exact Duplicate Leakage Between Train and Validation**:
   - In `prepare_dataset.py`, the training folder was split into 85% train and 15% validation using a simple random stratified split on individual images.
   - Multiple scans belonging to the **exact same patient** were split across train and validation.
   - For Pneumonia, **356 patient identifiers** appear in BOTH train and validation (77.22% of all validation pneumonia patients).
   - **8 exact duplicate image groups (byte-for-byte identical MD5 hashes)** were found shared across train and validation.
   - **Result**: Validation accuracy (99.23%) was severely over-optimistic due to memorization of patient-specific visual features.

2. **Independence of Test Set Patients**:
   - The test set was preserved intact from Kaggle's test split, containing strictly unseen patient cohorts.
   - Because the baseline model memorized patient-specific and dataset-split artifacts rather than generalizable lung pathology, its true generalization ability is reflected by the test set, not the inflated validation set.

3. **Domain & Contrast Shift Between Train and Test Normal Images**:
   - Analysis of pixel intensities reveals significant shifts in mean brightness and contrast between train normal and test normal images.
   - Training normal images have an average grayscale mean of 122.5 (std: 13.0), whereas test normal images exhibit a distinct distribution.
   - Normal pediatric chest X-rays have prominent thymic shadows ("sail sign") and physiologic lung markings that differ across radiological protocols. Without robust data augmentation, the model misinterprets normal pediatric lung density variations as consolidation.

4. **Class Imbalance & Loss Weighting Distortion**:
   - The training set contains 3,293 Pneumonia vs 1,140 Normal images (~2.89 : 1 ratio).
   - Loss weighting combined with extreme model confidence caused the network's predicted logits to be skewed, requiring probability calibration and patient-aware grouping.

---

## 2. Quantitative Diagnostic Findings

### 2.1 Split Counts & Proportions

| Split | NORMAL Images | PNEUMONIA Images | Total | % Normal | % Pneumonia |
|---|---:|---:|---:|---:|---:|
| **Train** | 1,140 | 3,293 | 4,433 | 25.7% | 74.3% |
| **Validation** | 201 | 582 | 783 | 25.7% | 74.3% |
| **Test** | 234 | 390 | 624 | 37.5% | 62.5% |

### 2.2 Exact Duplicate Hash Analysis

- **Total Unique File Hashes**: 5808 across 5840 files.
- **Cross-Split Duplicate Groups**: 8 groups found (all between `train` and `val`).
- **Within-Split Duplicate Groups**: 22 groups found.
- **Test Set Contamination**: 0 exact duplicate matches with `test`, confirming test set isolation from identical raw files.

### 2.3 Patient Leakage Analysis

| Category | Total Unique Patient IDs | Train PIDs | Val PIDs | Test PIDs | Train-Val Overlap | % of Val Leaked |
|---|---:|---:|---:|---:|---:|---:|
| **NORMAL** | 584 | 449 | 82 | 66 | 12 | 14.63% |
| **PNEUMONIA** | 1667 | 1530 | 461 | 202 | 356 | **77.22%** |

### 2.4 Baseline Model Performance Comparison (Threshold = 0.62)

| Metric | Validation Set | Held-Out Test Set | Gap (Test - Val) |
|---|---:|---:|---:|
| **Accuracy** | 99.23% | 80.61% | -18.62% |
| **Balanced Accuracy** | 99.00% | 74.23% | -24.77% |
| **ROC-AUC** | 0.9985 | 0.9372 | -0.0613 |
| **PR-AUC (Pneumonia)** | 0.9994 | 0.9516 | -0.0479 |
| **Sensitivity (Pneumonia Recall)** | 99.48% | 99.74% | +0.26% |
| **Specificity (Normal Recall)** | 98.51% | 48.72% | **-49.79%** |
| **Normal Precision** | 98.51% | 99.13% | +0.62% |
| **Pneumonia Precision** | 99.48% | 76.42% | -23.06% |
| **Macro F1** | 99.00% | 75.94% | -23.06% |

### 2.5 Confusion Matrices

**Validation Confusion Matrix**:
```
               Predicted NORMAL   Predicted PNEUMONIA
True NORMAL           198                3    
True PNEUMONIA        3                  579  
```

**Test Confusion Matrix**:
```
               Predicted NORMAL   Predicted PNEUMONIA
True NORMAL           114                120     <-- 120 FALSE POSITIVES
True PNEUMONIA        1                  389     <-- 1 FALSE NEGATIVE
```

---

## 3. Saliency & Visual Artifact Observations (Grad-CAM)

Inspection of Grad-CAM activations on False Positives (`results/diagnostics/error_cases_gradcam.png`) reveals:
1. **Cardiac & Thymus Silhouette Confusion**: In normal pediatric patients, the cardiac silhouette and thymus occupy a larger relative chest volume than in adults. The model frequently activates strongly on the lower left heart border and hilar shadows, erroneously classifying normal density as perihilar infiltrate or consolidation.
2. **Diaphragmatic & Subdiaphragmatic Gas Focus**: Several false positives demonstrate model activation near gastric bubbles and diaphragm contours rather than central parenchymal opacities.
3. **Overconfidence Due to Narrow Augmentation**: The existing pipeline utilized only `RandomRotation(7)` and `RandomHorizontalFlip(0.5)`. The model was never exposed during training to subtle contrast shifts, affine scaling, or brightness variations that characterize real-world portable X-rays.

---

## 4. Remediation Plan

To address these vulnerabilities in the training pipeline:
1. **Reconstruct Patient-Aware Train/Val Split**:
   - Group scans strictly by Patient Identifier so that scans from any given patient appear *either* in `train` *or* in `val`, never both.
   - De-duplicate identical image files across splits.
   - Retain the held-out test split for strict final evaluation.
2. **Conservative, Clinically Sound Augmentation**:
   - Affine transformations (slight translation, scaling 0.95-1.05, rotation +/- 10 degrees).
   - Conservative ColorJitter (brightness +/- 0.15, contrast +/- 0.15) to simulate radiographic exposure variation without altering lung pathology.
3. **Principled Imbalance Handling**:
   - Compare balanced class weighting in CrossEntropyLoss vs. WeightedRandomSampler.
4. **Regularization & Early Stopping on Balanced Validation Metric**:
   - Optimize for validation ROC-AUC or Balanced Accuracy rather than unweighted loss.
   - Use AdamW with Cosine Annealing learning rate schedule.
5. **Calibrated Threshold Tuning**:
   - Tune classification threshold strictly on the leak-free validation set using Balanced Accuracy and Youden's J statistic.

*Diagnostic artifacts generated: `probability_distributions.png`, `roc_pr_curves.png`, `confusion_matrices.png`, `error_cases_gradcam.png`, `duplicate_analysis.json`, `patient_leakage_analysis.json`.*
