"""Disk preparation is exact-scoped and must drop root before the workload starts."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import entrypoint


class VolumeBootstrapTests(unittest.TestCase):
    def test_root_requires_mount_before_any_mutation(self):
        with patch.object(entrypoint.os, "getuid", return_value=0, create=True), \
             patch.object(entrypoint.os.path, "ismount", return_value=False), \
             patch.object(entrypoint.os, "chown", create=True) as chown, \
             self.assertRaises(ValueError):
            entrypoint.provision_and_drop(Path("/missing-volume"))
        chown.assert_not_called()

    def test_only_named_directories_are_owned_and_root_is_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "existing-private.bin"
            private.write_bytes(b"synthetic-private-state")
            with patch.object(entrypoint.os, "getuid", side_effect=[0, 10001], create=True), \
                 patch.object(entrypoint.os.path, "ismount", return_value=True), \
                 patch.object(entrypoint.os, "chown", create=True) as chown, \
                 patch.object(entrypoint.os, "chmod") as chmod, \
                 patch.object(entrypoint.os, "setgroups", create=True) as groups, \
                 patch.object(entrypoint.os, "setgid", create=True) as gid, \
                 patch.object(entrypoint.os, "setuid", create=True) as uid:
                entrypoint.provision_and_drop(root)
            self.assertEqual(chown.call_count, 7)
            self.assertEqual(chmod.call_count, 7)
            self.assertNotIn(private, [call.args[0] for call in chown.call_args_list])
            self.assertEqual(private.read_bytes(), b"synthetic-private-state")
            groups.assert_called_once_with([])
            gid.assert_called_once_with(10001)
            uid.assert_called_once_with(10001)


if __name__ == "__main__":
    unittest.main()
