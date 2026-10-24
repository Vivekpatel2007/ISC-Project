# Comprehensive Model Evaluation & Diagnostic Report
**Project Title**: AI-Based Pneumonia Detection from Chest X-Ray Images with Secure Storage and Transmission of Medical Data  
**Subproject**: Machine Learning & Model Training Pipeline  
**Author**: Machine Learning Engineering Team  
**Hardware Used**: NVIDIA GeForce RTX 3050 6GB Laptop GPU (CUDA 12.2 / PyTorch 2.14.1)  
**Dataset**: Pediatric Chest X-Ray Images (Pneumonia) [Kaggle Kermany et al.]  

---

## 1. Executive Summary & Diagnostic Findings

### 1.1 The Generalization Mystery
The initial baseline model achieved seemingly stellar validation performance (~99.0% balanced accuracy, 0.9985 ROC-AUC), yet dropped sharply when evaluated on the held-out test set:
- **Baseline Test Accuracy**: 80.61%
- **Baseline Test Balanced Accuracy**: 74.23%
- **Baseline Test Specificity (Normal Recall)**: **48.72%** (120 out of 234 Normal patients were falsely classified as Pneumonia!)

Our automated diagnostic audit (`src/diagnose_dataset.py`) revealed the structural root causes behind this discrepancy:

1. **Patient Identifier Leakage Between Train and Validation**:
   - The initial split script (`src/prepare_dataset.py`) partitioned `data/chest_xray/train` into 85% train and 15% validation using a standard random stratified split on individual files.
   - Because single pediatric patients frequently had multiple X-ray scans (e.g., `person1000_bacteria_2931.jpeg` and `person1000_virus_1681.jpeg`), images from the **exact same patients** were partitioned into both the training and validation folders.
   - For Pneumonia, **356 patient identifiers** (77.2% of all validation pneumonia patients) were present in the training set.
   - **8 cross-split exact duplicate groups** (byte-for-byte identical MD5 file hashes) were found shared between train and validation.
   - Consequently, the validation metric measured the model's ability to memorize known patient anatomies and photographic artifacts rather than true clinical generalization.

2. **Independence of the Test Set**:
   - The test set was preserved intact from Kaggle's held-out test folder. It contains **zero exact duplicate files** and separate patient cohorts.
   - When exposed to unseen pediatric anatomies, the baseline model faltered on normal chest radiographs, mistaking normal cardiac silhouettes, pediatric thymic shadows, and varying machine contrast as pneumonia opacities.

3. **Narrow Augmentation & Premature Stopping**:
   - The baseline used minimal augmentation (`RandomRotation(7)` and `RandomHorizontalFlip(0.5)`).
   - Because validation loss rapidly dropped to 0.030 due to leaked patients, early stopping halted training before the network could learn robust, generalized lung parenchymal representations.

---

## 2. Improved Pipeline Architecture & Methodology

To rectify these issues without fabricating metrics or overfitting the test set, we introduced systematic improvements:

1. **Conservative, Clinically Realistic Data Augmentation**:
   - `RandomRotation(10)`: Accommodates subtle patient tilt.
   - `RandomAffine(translate=(0.04, 0.04), scale=(0.96, 1.04))`: Models slight positional variations and inspiration depth differences.
   - `ColorJitter(brightness=0.10, contrast=0.10)`: Simulates radiological exposure differences across portable vs. fixed X-ray machines without altering consolidation patterns.
   - `RandomHorizontalFlip(0.30)`: Conservative probability to respect radiological dextrocardia / situs inversus rarity and anatomic marker conventions.
   - **Crucial Rule**: Augmentations applied strictly to the training split; validation and test splits remain unaugmented with standard ImageNet normalization.

2. **Differential Learning Rates & Regularization**:
   - Added `Dropout(p=0.20)` before the final classification head.
   - DenseNet121 backbone fine-tuned at $0.5 \times$ the base learning rate ($5 \times 10^{-5}$) while the classifier head trains at $1 \times 10^{-4}$ using `AdamW` with $1 \times 10^{-2}$ weight decay. This preserves pretrained ImageNet edge and texture detectors while learning pneumonia-specific features.

3. **Optimization & Learning Rate Schedule**:
   - Replaced plateau scheduling with `CosineAnnealingLR` down to $\eta_{\text{min}} = 10^{-6}$.
   - Mixed-precision acceleration (`torch.amp.autocast`) enabling full FP16 throughput on 6 GB VRAM.

4. **Principled Validation Checkpoint Selection**:
   - Checkpoint selection was decoupled from raw validation loss (which is dominated by the majority class).
   - Best checkpoint was selected by **Validation ROC-AUC**, directly optimizing discrimination across both classes.

5. **Validation-Only Decision Threshold Tuning**:
   - Using `src/tune_threshold.py`, the probability decision threshold was selected strictly on validation data to maximize Balanced Accuracy and Youden's J statistic ($J = \text{Sensitivity} + \text{Specificity} - 1$).
   - The optimal validation threshold of **0.40** was embedded directly into the model checkpoint metadata.

---

## 3. Controlled Experiment Comparison

Both experiments were trained and evaluated on the exact same dataset partition for fair, scientific comparison.

| Metric | Baseline DenseNet121 (Val) | Baseline DenseNet121 (Test) | Improved DenseNet121 (Val) | Improved DenseNet121 (Test) | Test Set Delta (Improved vs Baseline) |
|---|---:|---:|---:|---:|---:|
| **Decision Threshold** | 0.62 | 0.62 | 0.40 | 0.40 | Validation Selected |
| **Overall Accuracy** | 99.23% | 80.61% | 99.23% | **84.94%** | **+4.33%** |
| **Balanced Accuracy** | 99.00% | 74.23% | 99.32% | **80.00%** | **+5.77%** |
| **ROC-AUC** | 0.9985 | 0.9372 | 0.9993 | **0.9619** | **+0.0247** |
| **PR-AUC (Pneumonia)** | 0.9994 | 0.9516 | 0.9996 | **0.9650** | **+0.0134** |
| **Sensitivity (Pneumonia Recall)** | 99.48% | 99.74% | 99.14% | **99.74%** | **Maintained (389/390)** |
| **Specificity (Normal Recall)** | 98.51% | 48.72% | 99.50% | **60.26%** | **+11.54% (27 fewer FPs)** |
| **NORMAL Precision** | 98.51% | 99.13% | 97.56% | **99.30%** | **+0.17%** |
| **NORMAL Recall** | 98.51% | 48.72% | 99.50% | **60.26%** | **+11.54%** |
| **NORMAL F1-Score** | 98.51% | 65.33% | 98.52% | **75.00%** | **+9.67%** |
| **PNEUMONIA Precision** | 99.48% | 76.42% | 99.83% | **80.71%** | **+4.29%** |
| **PNEUMONIA Recall** | 99.48% | 99.74% | 99.14% | **99.74%** | **0.00%** |
| **PNEUMONIA F1-Score** | 99.48% | 86.54% | 99.48% | **89.22%** | **+2.68%** |
| **Macro F1-Score** | 99.00% | 75.94% | 99.00% | **82.11%** | **+6.17%** |
| **Weighted F1-Score** | 99.23% | 78.59% | 99.24% | **83.89%** | **+5.30%** |

---

## 4. Confusion Matrix & Clinical Trade-Off Analysis

### 4.1 Test Confusion Matrices

```
BASELINE MODEL (Threshold = 0.62):
                 Predicted NORMAL   Predicted PNEUMONIA
  True NORMAL           114                120        <-- 120 False Positives
  True PNEUMONIA          1                389        <-- 1 False Negative

IMPROVED MODEL (Threshold = 0.40):
                 Predicted NORMAL   Predicted PNEUMONIA
  True NORMAL           141                 93        <-- 93 False Positives (27 fewer!)
  True PNEUMONIA          1                389        <-- 1 False Negative (Preserved!)
```

### 4.2 Clinical Error Analysis: False Positives vs. False Negatives

In chest radiography triage, prediction errors carry asymmetric clinical risks:

1. **False Negatives (Missed Pneumonia)**:
   - *Clinical Consequence*: A patient with active bacterial or viral pneumonia is sent home or left untreated. This can result in rapid respiratory decompensation, pleural effusion, empyema, sepsis, or pediatric mortality.
   - *Model Behavior*: Both the baseline and improved model achieved exceptional sensitivity (**99.74%**), missing only **1 out of 390 pneumonia cases** in the held-out test cohort.
2. **False Positives (Overdiagnosis)**:
   - *Clinical Consequence*: A healthy child or patient is erroneously diagnosed with pneumonia. This causes parental distress, unnecessary hospital admissions, redundant high-dose radiation CT scans, and inappropriate antibiotic prescriptions contributing to antimicrobial resistance.
   - *Model Improvement*: The improved model successfully corrected **27 false positives**, raising Specificity from **48.72% to 60.26%** and NORMAL F1 from **65.33% to 75.00%** while strictly preserving the near-perfect sensitivity.

---

## 5. Visual Explainability (Grad-CAM)

Using `src/plot_predictions.py` and `src/diagnose_dataset.py`, we generated Grad-CAM saliency maps of predictions:
- **Baseline Behavior**: The baseline frequently focused on mediastinal border contours, diaphragm gas shadows, and high-frequency noise near image corners. This explains why normal test images with slight contrast variations were falsely triggered.
- **Improved Model Behavior**: The improved model's attention heatmaps show focused activation over bilateral lower and middle lung fields (where alveolar consolidations and bronchopneumonia infiltrates typically manifest). On normal scans such as `IM-0003-0001.jpeg`, which the baseline misclassified with 92.7% pneumonia confidence, the improved model accurately predicted `NORMAL` with only 3.1% pneumonia probability.

All sample diagnostic visualization cards are preserved in:
`results/diagnostics/predictions_visualized/`

---

## 6. Model Artifacts & Standalone Inference Verification

The model checkpoint is saved with all inference metadata and requires **no retraining**:

- **Checkpoint Location**: `models/densenet121_pneumonia_best.pth`
- **Metadata Embedded in Checkpoint**:
  * `model_state_dict`: Trained model weights.
  * `architecture`: `"densenet121"`
  * `class_names`: `["NORMAL", "PNEUMONIA"]`
  * `class_to_idx`: `{"NORMAL": 0, "PNEUMONIA": 1}`
  * `image_size`: `224`
  * `normalization`: `{"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}`
  * `threshold`: `0.40`
  * `best_epoch`: `5`
  * `validation_metrics`: Full validation metric dictionary.

### Loading Checkpoint for Future Web App Integration:
```python
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

# 1. Load checkpoint
ckpt = torch.load("models/densenet121_pneumonia_best.pth", map_location="cpu", weights_only=False)

# 2. Reconstruct architecture
model = models.densenet121(weights=None)
in_features = model.classifier.in_features
model.classifier = nn.Sequential(nn.Dropout(0.2), nn.Linear(in_features, len(ckpt["class_names"])))
model.load_state_dict(ckpt["model_state_dict"])
model.eval()

# 3. Preprocessing
transform = transforms.Compose([
    transforms.Grayscale(num_output_channels=3),
    transforms.Resize((ckpt["image_size"], ckpt["image_size"])),
    transforms.ToTensor(),
    transforms.Normalize(ckpt["normalization"]["mean"], ckpt["normalization"]["std"])
])

# 4. Predict
img = Image.open("path_to_xray.jpeg").convert("RGB")
tensor = transform(img).unsqueeze(0)
with torch.no_grad():
    probs = torch.softmax(model(tensor), dim=1).squeeze()
    pneumonia_prob = probs[1].item()
    prediction = "PNEUMONIA" if pneumonia_prob >= ckpt["threshold"] else "NORMAL"
```

---

## 7. Remaining Limitations & Recommended Next Steps

1. **Patient-Grouped Repartitioning**:
   - Although our improved pipeline raised test accuracy on the existing benchmark from 80.61% to 84.94%, `data/model_data` retains patient-level overlap between train and val.
   - We updated `src/prepare_dataset.py` with the `--patient_grouping` and `--deduplicate` flags. For a future project iteration, running `python src/prepare_dataset.py --patient_grouping --deduplicate` will produce an entirely leak-free partition (`data/model_data_patient_split`).
2. **Multi-Center / Multi-Domain Testing**:
   - The Kermany dataset originates from a single pediatric medical center. Evaluating on adult cohorts (e.g., NIH ChestX-ray14 or CheXpert) will require domain adaptation or multi-dataset fine-tuning.
3. **Multi-Label Pathology Support**:
   - In real-world clinical radiology, pneumonia frequently co-occurs with effusion, atelectasis, cardiomegaly, or pneumothorax. Transitioning to a multi-label classification head will improve diagnostic richness.

---

> **Educational Disclaimer**: This system is developed as an educational prototype for an ISC engineering project. It is **not clinically validated** for medical diagnosis or clinical decision-making. No medical treatment decisions should be made based on its predictions.
