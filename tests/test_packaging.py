import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.package_release import package_release


class PackagingTests(unittest.TestCase):
    def test_archives_extract_to_install_ready_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dist" / "EasyMP3Host" / "_internal").mkdir(parents=True)
            (root / "dist" / "EasyMP3Host" / "EasyMP3Host.exe").write_bytes(b"host")
            (root / "dist" / "EasyMP3Host" / "_internal" / "runtime.dll").write_bytes(b"dll")
            (root / "extension" / "tests").mkdir(parents=True)
            (root / "extension" / "manifest.json").write_text("{}")
            (root / "extension" / "background.js").write_text("")
            (root / "extension" / "tests" / "background.test.js").write_text("")
            (root / "extension" / "package.json").write_text("{}")
            (root / "scripts").mkdir()
            for name in ("install-native-host.ps1", "uninstall-native-host.ps1"):
                (root / "scripts" / name).write_text(name)

            host_zip, extension_zip = package_release(root, root / "package")

            with ZipFile(host_zip) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "native-host/EasyMP3Host.exe",
                        "native-host/_internal/runtime.dll",
                        "native-host/install-native-host.ps1",
                        "native-host/uninstall-native-host.ps1",
                    },
                )
            with ZipFile(extension_zip) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"extension/manifest.json", "extension/background.js"},
                )


if __name__ == "__main__":
    unittest.main()
