
from pathlib import Path
from PIL import Image

data_dir = Path("data/chest_xray")

for split in ["train", "val", "test"]:
    print(f"\n--- {split.upper()} ---")

    for class_name in ["NORMAL", "PNEUMONIA"]:
        folder = data_dir / split / class_name

        if not folder.exists():
            print(f"{class_name}: folder not found at {folder}")
            continue

        image_paths = [
            path for path in folder.iterdir()
            if path.is_file()
        ]

        valid_count = 0
        invalid_count = 0

        for path in image_paths:
            try:
                with Image.open(path) as image:
                    image.verify()
                valid_count += 1
            except Exception:
                invalid_count += 1

        print(f"{class_name}: {len(image_paths)} files")
        print(f"  Valid: {valid_count}")
        print(f"  Invalid: {invalid_count}")
