"""
Dataset Preparation & Partitioning Pipeline
ISC Project: AI-Based Pneumonia Detection from Chest X-Ray Images

Features:
- Audits and reports duplicate image hashes before splitting.
- Supports both:
  1. Standard stratified split (reproducing existing baseline split).
  2. Patient-aware grouping split (GroupShuffleSplit on patient IDs to prevent data leakage).
- Preserves the held-out test split intact.
- Generates split metadata and class distribution summaries.
"""

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from sklearn.model_selection import train_test_split, GroupShuffleSplit


def compute_md5(filepath: Path) -> str:
    hasher = hashlib.md5()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def extract_patient_id(filename: str, class_name: str) -> str:
    stem = Path(filename).stem
    if class_name == "PNEUMONIA":
        parts = stem.split("_")
        return parts[0]  # e.g. person1000
    else:
        parts = stem.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}-{parts[1]}"
        return stem


def prepare_dataset(
    data_dir: Path,
    output_dir: Path,
    train_ratio: float = 0.85,
    random_seed: int = 42,
    patient_grouping: bool = False,
    deduplicate: bool = False
):
    classes = ["NORMAL", "PNEUMONIA"]
    print("=" * 60)
    print("DATASET PREPARATION PIPELINE")
    print("=" * 60)
    print(f"Source raw data:       {data_dir.resolve()}")
    print(f"Destination folder:    {output_dir.resolve()}")
    print(f"Train / Val ratio:     {train_ratio:.2f} / {1.0 - train_ratio:.2f}")
    print(f"Random seed:           {random_seed}")
    print(f"Patient grouping:      {patient_grouping}")
    print(f"Deduplicate images:    {deduplicate}")

    # Gather images from the raw training folder
    all_paths = []
    all_labels = []
    all_patient_ids = []
    hash_to_path = {}
    duplicates_found = []

    for class_name in classes:
        class_dir = data_dir / "train" / class_name
        if not class_dir.exists():
            raise FileNotFoundError(f"Training folder not found: {class_dir}")

        for path in sorted(class_dir.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                h = compute_md5(path)
                if h in hash_to_path:
                    duplicates_found.append((path.name, hash_to_path[h].name))
                    if deduplicate:
                        continue  # Skip duplicate file
                else:
                    hash_to_path[h] = path

                all_paths.append(path)
                all_labels.append(class_name)
                all_patient_ids.append(extract_patient_id(path.name, class_name))

    print(f"\nDiscovered {len(all_paths)} valid training source images.")
    if duplicates_found:
        print(f"  Identified {len(duplicates_found)} duplicate image pairs.")
        if deduplicate:
            print(f"  Removed duplicates from training candidate pool.")

    # Perform Split
    if patient_grouping:
        print("\nApplying GroupShuffleSplit by Patient ID...")
        gss = GroupShuffleSplit(n_splits=1, train_size=train_ratio, random_state=random_seed)
        train_idx, val_idx = next(gss.split(all_paths, all_labels, groups=all_patient_ids))
        train_paths = [all_paths[i] for i in train_idx]
        train_labels = [all_labels[i] for i in train_idx]
        val_paths = [all_paths[i] for i in val_idx]
        val_labels = [all_labels[i] for i in val_idx]
    else:
        print("\nApplying standard Stratified split...")
        train_paths, val_paths, train_labels, val_labels = train_test_split(
            all_paths,
            all_labels,
            train_size=train_ratio,
            random_state=random_seed,
            stratify=all_labels
        )

    # Check patient overlap
    tr_pids = set(extract_patient_id(p.name, l) for p, l in zip(train_paths, train_labels))
    va_pids = set(extract_patient_id(p.name, l) for p, l in zip(val_paths, val_labels))
    overlap = tr_pids & va_pids
    print(f"Patient overlap between train and val: {len(overlap)} patients.")

    # Copy files into output directory
    for split, paths, labels in [("train", train_paths, train_labels), ("val", val_paths, val_labels)]:
        for class_name in classes:
            folder = output_dir / split / class_name
            folder.mkdir(parents=True, exist_ok=True)

        for path, label in zip(paths, labels):
            dest = output_dir / split / label / path.name
            if not dest.exists():
                shutil.copy2(path, dest)

    # Keep original test set untouched
    for class_name in classes:
        source = data_dir / "test" / class_name
        dest = output_dir / "test" / class_name
        if not source.exists():
            raise FileNotFoundError(f"Test folder not found: {source}")
        dest.mkdir(parents=True, exist_ok=True)
        for path in source.iterdir():
            if path.is_file() and not path.name.startswith("."):
                target = dest / path.name
                if not target.exists():
                    shutil.copy2(path, target)

    # Print summary and save metadata
    summary = {"splits": {}}
    print("\nDataset Partition Summary:")
    for split in ["train", "val", "test"]:
        summary["splits"][split] = {}
        print(f"\n--- {split.upper()} ---")
        for class_name in classes:
            folder = output_dir / split / class_name
            count = sum(1 for p in folder.iterdir() if p.is_file())
            summary["splits"][split][class_name] = count
            print(f"  {class_name}: {count}")

    summary_file = output_dir / "dataset_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDataset preparation finished. Metadata saved to {summary_file}")


def main():
    parser = argparse.ArgumentParser(description="Prepare and partition chest X-ray dataset")
    parser.add_argument("--data_dir", type=str, default="data/chest_xray", help="Raw dataset directory")
    parser.add_argument("--output_dir", type=str, default="data/model_data", help="Output directory")
    parser.add_argument("--train_ratio", type=float, default=0.85, help="Train ratio (default 0.85)")
    parser.add_argument("--random_seed", type=int, default=42, help="Random seed")
    parser.add_argument("--patient_grouping", action="store_true", help="Group by patient ID to avoid leakage")
    parser.add_argument("--deduplicate", action="store_true", help="Remove duplicate images from training pool")
    args = parser.parse_args()

    prepare_dataset(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        train_ratio=args.train_ratio,
        random_seed=args.random_seed,
        patient_grouping=args.patient_grouping,
        deduplicate=args.deduplicate
    )


if __name__ == "__main__":
    main()
