"""Read-only compute check with an optional offline model smoke test. No servers or DB."""

import argparse
import io
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='store_true', help='Also run the checkpoint on a synthetic image')
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    import torch
    from src.compute import select_device

    device = select_device()
    print(f'PyTorch: {torch.__version__}; packaged CUDA: {torch.version.cuda or "none"}')
    print(f'Preference: {os.getenv("PULMOSCAN_DEVICE", "auto")}; actual device: {device}')
    if device.type == 'cuda':
        properties = torch.cuda.get_device_properties(device)
        print(f'GPU: {properties.name}; VRAM: {properties.total_memory / 1024**3:.1f} GiB')
    if args.model:
        from PIL import Image
        from src.api.model_service import DenseNetInferenceEngine
        engine = DenseNetInferenceEngine()
        payload = io.BytesIO()
        Image.new('L', (224, 224), 90).save(payload, format='PNG')
        result = engine.predict(payload.getvalue())
        print(f'Checkpoint prediction succeeded on {result["device"]}. Synthetic input; not an accuracy test.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
