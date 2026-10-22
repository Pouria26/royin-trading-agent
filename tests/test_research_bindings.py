"""Fixed-byte oracle for the versioned executable binding, independent of checkout."""

import tempfile
import unittest
from pathlib import Path

from royin.evaluation import source_bundle_sha256


class ResearchBindingTests(unittest.TestCase):
    def test_lf_crlf_match_fixed_length_framed_byte_oracle(self):
        # 8-byte big-endian19, path, 8-byte big-endian6, literal b'x = 1\n'.
        expected = "ea3e9a98c83f92f98f60f4c4372f7390835d95092b0eb45378efbc80510af723"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "src/royin/sample.py"
            path.parent.mkdir(parents=True)
            for content in (b"x = 1\n", b"x = 1\r\n"):
                path.write_bytes(content)
                self.assertEqual(source_bundle_sha256(root, [path]), expected)
            for content in (b"x = 2\n", b"x = 1 \n", b"x = 1\r", b"\xef\xbb\xbfx = 1\n"):
                path.write_bytes(content)
                self.assertNotEqual(source_bundle_sha256(root, [path]), expected)

    def test_legacy_raw_contract_remains_byte_sensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "src/royin/sample.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"x = 1\n")
            self.assertEqual(
                source_bundle_sha256(root, [path], binding_schema_version=1),
                "3d66982364c92393e0b62fc09b35582480eae02e41a9a26f017e78766625e50c",
            )
            path.write_bytes(b"x = 1\r\n")
            self.assertNotEqual(
                source_bundle_sha256(root, [path], binding_schema_version=1),
                "3d66982364c92393e0b62fc09b35582480eae02e41a9a26f017e78766625e50c",
            )
            for version in (0, 3, True):
                with self.assertRaises(ValueError):
                    source_bundle_sha256(root, [path], binding_schema_version=version)
