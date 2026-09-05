import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import utils


class PrepareExternalSubprocessesTests(unittest.TestCase):
    def setUp(self):
        utils._external_subprocesses_prepared = False

    def tearDown(self):
        utils._external_subprocesses_prepared = False

    def test_source_run_is_a_noop(self):
        kernel32 = SimpleNamespace(SetDllDirectoryW=Mock())
        with (
            patch.object(utils.sys, "platform", "win32"),
            patch.object(utils.sys, "frozen", False, create=True),
            patch.object(utils.ctypes, "windll", SimpleNamespace(kernel32=kernel32), create=True),
        ):
            utils.prepare_external_subprocesses()

        kernel32.SetDllDirectoryW.assert_not_called()

    def test_frozen_windows_run_clears_dll_directory_once(self):
        kernel32 = SimpleNamespace(SetDllDirectoryW=Mock(return_value=1))
        with (
            patch.object(utils.sys, "platform", "win32"),
            patch.object(utils.sys, "frozen", True, create=True),
            patch.object(utils.ctypes, "windll", SimpleNamespace(kernel32=kernel32), create=True),
        ):
            utils.prepare_external_subprocesses()
            utils.prepare_external_subprocesses()

        kernel32.SetDllDirectoryW.assert_called_once_with(None)

    def test_failed_windows_api_call_raises_and_can_be_retried(self):
        set_directory = Mock(side_effect=[0, 1])
        kernel32 = SimpleNamespace(SetDllDirectoryW=set_directory)
        with (
            patch.object(utils.sys, "platform", "win32"),
            patch.object(utils.sys, "frozen", True, create=True),
            patch.object(utils.ctypes, "windll", SimpleNamespace(kernel32=kernel32), create=True),
            patch.object(utils.ctypes, "get_last_error", return_value=5),
            patch.object(utils.ctypes, "WinError", side_effect=lambda code: OSError(code, "access denied"), create=True),
        ):
            with self.assertRaises(OSError):
                utils.prepare_external_subprocesses()
            utils.prepare_external_subprocesses()

        self.assertEqual(set_directory.call_count, 2)


if __name__ == "__main__":
    unittest.main()
