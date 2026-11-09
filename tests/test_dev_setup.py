"""Test environment creation using temporary folders, never the developer's keys."""

import base64
from pathlib import Path
import tempfile
import unittest

from scripts.setup_local_env import setup_local_env


class LocalEnvironmentSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'frontend').mkdir()
        (self.root / '.env.example').write_text(
            'IMAGE_ENCRYPTION_KEY=REPLACE_WITH_GENERATED_BASE64_256BIT_KEY\n'
            'JWT_SECRET_KEY=REPLACE_WITH_CRYPTOGRAPHICALLY_RANDOM_SECRET_KEY\n',
            encoding='utf-8',
        )

    def test_generates_valid_distinct_keys_and_frontend_url(self):
        self.assertEqual(setup_local_env(self.root), ['.env', 'frontend/.env.local'])
        values = dict(line.split('=', 1) for line in (self.root / '.env').read_text().splitlines())
        self.assertEqual(len(base64.urlsafe_b64decode(values['IMAGE_ENCRYPTION_KEY'])), 32)
        self.assertEqual(len(values['JWT_SECRET_KEY']), 64)
        self.assertNotEqual(values['IMAGE_ENCRYPTION_KEY'], values['JWT_SECRET_KEY'])
        self.assertEqual(
            (self.root / 'frontend/.env.local').read_text(),
            'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n',
        )

    def test_rerunning_preserves_existing_configuration_byte_for_byte(self):
        setup_local_env(self.root)
        backend = (self.root / '.env').read_bytes()
        frontend = (self.root / 'frontend/.env.local').read_bytes()
        self.assertEqual(setup_local_env(self.root), [])
        self.assertEqual((self.root / '.env').read_bytes(), backend)
        self.assertEqual((self.root / 'frontend/.env.local').read_bytes(), frontend)

    def test_creates_missing_frontend_file_without_changing_existing_backend(self):
        (self.root / '.env').write_text('EXISTING_KEY=preserve-me\n')
        self.assertEqual(setup_local_env(self.root), ['frontend/.env.local'])
        self.assertEqual((self.root / '.env').read_text(), 'EXISTING_KEY=preserve-me\n')


if __name__ == '__main__':
    unittest.main()
