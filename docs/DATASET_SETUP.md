# Dataset download and preparation

## Which dataset this repository refers to

The project uses **Pediatric Chest X-Ray Images (Pneumonia), Kaggle / Kermany et al.** The downloaded image filenames and folders match the expected two-class Kaggle layout. The teammate's generated evaluation report was removed during the old-results cleanup; the current preparation protocol is documented in [the training guide](TRAINING.md).

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

The current local download instead places `train/`, `val/`, and `test/` **directly under `data/`**. This layout is valid for the new audit/evaluation tools; there is no need to move or duplicate the images. Pass `--data-dir data` as shown below. The legacy scripts with defaults pointing to `data/chest_xray` or `data/model_data` need explicit paths or a separate experiment configuration before later use.

Allow several GB beyond the software allowance for the downloaded archive, extracted images, and a second prepared copy. The **entire `data/` directory is ignored by Git**, including the current raw images, prepared datasets, archives, and local review reports. The images are not bundled or automatically downloaded by this repository.

## Check the download without starting services

From the project root:

```powershell
.\.venv\Scripts\python.exe scripts/audit_dataset.py --data-dir data
```

This reads and fully decodes the images, counts classes, records SHA-256 hashes, detects exact byte/pixel duplicates, and reports candidate subject IDs shared between splits. It writes `data/review/dataset_audit.json` and does not change source images. Missing folders or decode errors cause a failing exit code. If your raw folders are under `data/chest_xray`, use `--data-dir data/chest_xray` instead.

The legacy `src/check_dataset.py` remains a basic header check hardcoded to `data/chest_xray`; use the audit tool for this local layout. A clean audit does not prove correct labels, authoritative patient identities, absence of near-duplicates, or medical accuracy.

Do not replace the project's live checkpoint simply to check the download. The dataset check does not start an API, train a model, or change stored scans.

## Raw images versus prepared training data

The current training workflow uses `data/prepared/screening-v1/manifest.json`, already prepared for this download. It points to raw image files directly, with **4,035 train / 712 validation / 618 test images**. The [training guide](TRAINING.md) explains exclusions, changed-file findings, preprocessing, and the manual command to start training.

`src/prepare_dataset.py` now creates immutable split manifests rather than copying images into ImageFolder directories. It corrects normal-ID parsing, connects candidate subject IDs and exact-pixel duplicates, reserves test-connected components, deduplicates each evaluation/training pool, and makes a class-balanced train/validation split from eligible raw train/validation images. It refuses nonempty output directories and records source hashes and exclusions. The older `data/model_data` workflow and nested `configs/train_config.json` are historical; use `configs/train_local.json` for the new runner.

For a new reviewed source version, create a fresh audit and a new manifest directory as documented in the training guide. Do not rerun preparation to start the already prepared local experiment.

**Candidate-ID separation is not proof of patient independence.** Filename conventions are heuristic; authoritative patient metadata and near-duplicate review are still needed. The new prepared test set omits six exact-pixel duplicates from the original 624-image test set, so future results must identify that changed protocol.

## What to review before retraining

The [historical backend review](BACKEND_REVIEW.md) records the earlier overlap findings. Old generated files under `results/` have been removed; use the current integrity audits and split manifest for new experiments. In particular:

- Audit image hashes and patient identifiers across all splits, including the copied test set.
- Keep the test set out of training, threshold selection, hyperparameter selection, and repeated model selection.
- Record class counts, exclusions, split file lists, random seed, dataset version, and configuration.
- Evaluate the existing checkpoint before deciding whether retraining improves it. This dataset is pediatric; results on it do not establish adult or general clinical performance.
- On the GTX 1650, begin any later training memory trial with a small batch, such as 2. The current batch size 16 has not been verified to fit its 4 GB VRAM.

Obtain the following from your teammate if exact reproduction matters: the original dataset archive/version, the final split manifests or prepared dataset summary, preprocessing/exclusion choices, the exact training configuration/command, the checkpoint checksum, and the threshold-tuning/evaluation commands. The public download cannot recover undocumented experiment choices.

At the review stage, audit the downloaded files and establish a fixed-model baseline before preparing a new experiment. No training or dataset preparation has been run automatically. Backend request/storage tests and model-quality evaluation are separate tasks; passing the former does not establish the latter.
