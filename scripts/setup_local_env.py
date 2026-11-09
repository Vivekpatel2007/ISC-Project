"""Create local configuration once, without overwriting existing keys or settings."""

import base64
from pathlib import Path
import secrets


def setup_local_env(root: Path) -> list[str]:
    created = []
    backend = root / '.env'
    if not backend.exists():
        template = (root / '.env.example').read_text(encoding='utf-8')
        template = template.replace(
            'REPLACE_WITH_GENERATED_BASE64_256BIT_KEY',
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'),
        ).replace(
            'REPLACE_WITH_CRYPTOGRAPHICALLY_RANDOM_SECRET_KEY', secrets.token_hex(32),
        )
        # Exclusive creation also prevents a concurrent setup from replacing keys.
        with backend.open('x', encoding='utf-8') as handle:
            handle.write(template)
        created.append('.env')

    frontend = root / 'frontend' / '.env.local'
    if not frontend.exists():
        with frontend.open('x', encoding='utf-8') as handle:
            handle.write('NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n')
        created.append('frontend/.env.local')
    return created


if __name__ == '__main__':
    for name in setup_local_env(Path(__file__).resolve().parent.parent):
        print(f'Created {name}.')
    print('Existing configuration files were preserved. No keys were printed.')
