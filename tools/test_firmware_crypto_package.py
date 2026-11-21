"""Host regression test for staging locked CryptoBin inputs into PACKAGES_PATH."""

import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_v91_firmware import stage_crypto_package


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CryptoPackageStageTests(unittest.TestCase):
    def test_stages_exact_locked_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            data = b'locked external crypto include'
            member = source / 'Driver' / 'Bin' / 'CryptoDriver.inc.dsc'
            member.parent.mkdir(parents=True)
            member.write_bytes(data)
            manifest = {'Driver/Bin/CryptoDriver.inc.dsc': sha(data)}
            destination = root / 'workspace' / 'Platforms' / 'EldenBaseCrypto'

            result = stage_crypto_package(source, destination, manifest)

            self.assertTrue(result['verified'])
            self.assertEqual(result['files'], 1)
            self.assertEqual((destination / 'Driver/Bin/CryptoDriver.inc.dsc').read_bytes(), data)
            self.assertNotEqual(member, destination / 'Driver/Bin/CryptoDriver.inc.dsc')

    def test_rejects_hash_mismatch_before_package_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            member = source / 'CryptoDriver.inc.dsc'
            member.write_bytes(b'unexpected content')

            with self.assertRaisesRegex(ValueError, 'CryptoBin input mismatch'):
                stage_crypto_package(
                    source, root / 'workspace' / 'Crypto',
                    {'CryptoDriver.inc.dsc': '0' * 64},
                )

    def test_rejects_unsafe_manifest_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            destination = root / 'workspace' / 'Crypto'

            with self.assertRaisesRegex(ValueError, 'Unsafe CryptoBin manifest path'):
                stage_crypto_package(source, destination, {'../outside': '0' * 64})


if __name__ == '__main__':
    unittest.main()
