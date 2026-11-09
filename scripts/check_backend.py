"""Read-only development checks. Never starts the API or initializes its database."""

import base64
import importlib
import os
from pathlib import Path
import sys


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    try:
        for module in (
            'dotenv', 'fastapi', 'uvicorn', 'torch', 'torchvision', 'numpy',
            'PIL.Image', 'cryptography.hazmat.primitives.ciphers.aead',
            'jwt', 'bcrypt', 'multipart',
        ):
            importlib.import_module(module)
    except Exception as error:
        print(f'Backend dependency check failed ({type(error).__name__}).', file=sys.stderr)
        print('Install the Python dependencies using README.md. For Windows application-control errors, use the documented CPU package versions.', file=sys.stderr)
        return 1

    from dotenv import load_dotenv
    load_dotenv(root / '.env', override=False)
    try:
        encoded_key = os.environ.get('IMAGE_ENCRYPTION_KEY', '')
        key = base64.b64decode(encoded_key.encode('ascii'), altchars=b'-_', validate=True)
        jwt_secret = os.environ.get('JWT_SECRET_KEY', '')
        if len(key) != 32 or len(jwt_secret) < 32 or 'REPLACE_WITH' in jwt_secret:
            raise ValueError('Invalid local keys')
    except (ValueError, UnicodeError):
        print('Local secrets are missing or invalid. Follow the environment setup in README.md; preserve the key used by existing scans.', file=sys.stderr)
        return 1

    checkpoint = Path(os.environ.get('MODEL_CHECKPOINT_PATH', 'models/densenet121_pneumonia_best.pth'))
    if not checkpoint.is_absolute():
        checkpoint = root / checkpoint
    if not checkpoint.is_file():
        print('Model checkpoint missing. Restore the model at MODEL_CHECKPOINT_PATH before starting the app.', file=sys.stderr)
        return 1

    from src.compute import select_device
    try:
        device = select_device()
        print(f'Compute check: {device}.')
    except (ValueError, RuntimeError) as error:
        print(f'Compute check failed: {error}', file=sys.stderr)
        return 1

    print('Backend dependencies, local keys, and model checkpoint are available. No server was started.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
