# Dataset download and preparation

## Which dataset this repository refers to

The [teammate's evaluation report](../results/model_evaluation_report.md) identifies **Pediatric Chest X-Ray Images (Pneumonia), Kaggle / Kermany et al.** Its example filenames and the preparation script match the expected two-class Kaggle layout.

Download [Chest X-Ray Images (Pneumonia), published by Paul Mooney on Kaggle](https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia). Use the dataset page's download action; Kaggle may request sign-in. No Kaggle Python package or API token is needed for a browser download. Keep the downloaded archive name/version and download date for your experiment records.

The related [original Mendeley Data record by Kermany, Zhang, and Goldbaum](https://data.mendeley.com/datasets/rscbjbr9sj/2) contains OCT and chest X-ray data and lists a CC BY 4.0 license. The chest X-ray portion is relevant here; the retinal OCT images are not inputs for this project. Follow the downloaded dataset's attribution and licensing information.

This identifies the dataset family and likely download source. **The exact archive version, prepared file lists, and original training run have not been independently reproduced from this checkout.** Downloading the same public dataset alone does not establish that you have the exact same split as the checkpoint.

## What you need it for

| Task | Dataset needed? |
| --- | --- |
| Run the frontend/backend with the existing checkpoint | No |
| Run the existing automated backend tests | No; they use temporary storage and synthetic images |
| Try the upload/prediction workflow with real X-rays | A few suitable examples are sufficient; this does not measure model accuracy |
| Measure accuracy, sensitivity, specificity, and errors | Yes, with an audited labeled evaluation split |
| Train or fine-tune a new checkpoint | Yes, with separate training and validation data and a held-out test set |

Package installation and dataset download are separate. `requirements.txt` installs Python libraries; no requirements file downloads this dataset or initiates training.

## Extract the raw images

From the project root, create the destination folder if needed:

```powershell
New-Item -ItemType Directory -Force data/chest_xray
```

Extract the downloaded archive manually. Place the contents of its actual `chest_xray` folder here:

```text
Pneumonia-Detection/
  data/
    chest_xray/
      train/
        NORMAL/
        PNEUMONIA/
      val/
        NORMAL/
        PNEUMONIA/
      test/
        NORMAL/
        PNEUMONIA/
```

Some archives contain nested copies of the dataset folder. The required path is `data/chest_xray/train/NORMAL`, not `data/chest_xray/chest_xray/train/NORMAL`. Keep archive metadata folders such as `__MACOSX` outside the class directories. Preserve original image filenames because the existing grouping code uses them.

Allow several GB beyond the software allowance for the downloaded archive, extracted images, and a second prepared copy. Downloaded images in `data/chest_xray/`, prepared copies in `data/model_data*/`, and archives in `data/downloads/` or `data/*.zip` are ignored by Git. The images are not bundled or automatically downloaded by this repository.

## Check the download without starting services

From the project root:

```powershell
.\.venv\Scripts\python.exe src/check_dataset.py
```

The existing script scans `data/chest_xray`, reports class counts, and attempts image verification with Pillow. Investigate missing folders, empty classes, or invalid images before proceeding. This is a basic image-file check; it does not audit patient separation, labels, duplicate leakage, or model accuracy. It currently reports problems in its output rather than returning a strict validation failure code.

Do not replace the project's live checkpoint simply to check the download. The dataset check does not start an API, train a model, or change stored scans.

## Raw images versus prepared training data

The current training configuration expects a **prepared** dataset at `data/model_data/`, also with `train`, `val`, and `test` folders containing the two class folders. Extracting to `data/chest_xray/` alone does not populate it.

The existing `src/prepare_dataset.py` builds training and validation subsets from the **raw train folder**, defaulting to 85% / 15% with seed 42. It copies the raw test set and does not incorporate the bundled raw validation folder. It supports patient grouping and exact-file deduplication of the training candidate pool.

For a later reviewed experiment, an example preparation command is:

```powershell
.\.venv\Scripts\python.exe src/prepare_dataset.py --data_dir data/chest_xray --output_dir data/model_data_patient_split --patient_grouping --deduplicate
```

This copies images and writes a dataset summary; it does not train. Use a new, empty destination per experiment. The current script skips already present filenames rather than cleaning the destination, so reusing an old prepared directory can retain stale images. Point a separate experiment configuration's `data.data_dir` at the new prepared folder before any later training.

**These options are not a guarantee of a leak-free dataset.** Patient IDs are inferred heuristically from filenames; complete authoritative patient metadata is not supplied by this project. Deduplication in the preparation script covers the raw training pool, not an independent audit of all training/validation/test boundaries. Identical images, patient overlap, and conflicting labels still need review across all splits.

## What to review before retraining

The existing evaluation report and files under `results/diagnostics/` describe patient overlap and exact duplicates in an earlier validation split. Treat those as recorded findings to reproduce, not as verified facts about a newly downloaded archive. In particular:

- Audit image hashes and patient identifiers across all splits, including the copied test set.
- Keep the test set out of training, threshold selection, hyperparameter selection, and repeated model selection.
- Record class counts, exclusions, split file lists, random seed, dataset version, and configuration.
- Evaluate the existing checkpoint before deciding whether retraining improves it. This dataset is pediatric; results on it do not establish adult or general clinical performance.
- On the GTX 1650, begin any later training memory trial with a small batch, such as 2. The current batch size 16 has not been verified to fit its 4 GB VRAM.

Obtain the following from your teammate if exact reproduction matters: the original dataset archive/version, the final split manifests or prepared dataset summary, preprocessing/exclusion choices, the exact training configuration/command, the checkpoint checksum, and the threshold-tuning/evaluation commands. The public download cannot recover undocumented experiment choices.

For now, download, extract, and check the files. No training or dataset preparation has been run automatically. Backend request/storage tests and model-quality evaluation are separate tasks; passing the former does not establish the latter.
