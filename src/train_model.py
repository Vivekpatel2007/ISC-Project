"""Compatibility entry point for the manifest-based local experiment runner."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.train_models import cli


if __name__ == '__main__':
    raise SystemExit(cli())
