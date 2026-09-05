"""Create release ZIP files with installation-ready directory layouts."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


EXTENSION_EXCLUDES = {"tests", "node_modules", "package.json", "package-lock.json"}


def _write_tree(archive: ZipFile, source: Path, archive_root: str) -> None:
    for path in sorted(source.rglob("*")):
        if path.is_file():
            archive.write(path, Path(archive_root, path.relative_to(source)).as_posix())


def package_release(repo_root: Path, output_dir: Path) -> tuple[Path, Path]:
    host_dir = repo_root / "dist" / "EasyMP3Host"
    extension_dir = repo_root / "extension"
    scripts_dir = repo_root / "scripts"
    if not (host_dir / "EasyMP3Host.exe").is_file():
        raise FileNotFoundError(f"Missing helper build: {host_dir / 'EasyMP3Host.exe'}")
    if not (extension_dir / "manifest.json").is_file():
        raise FileNotFoundError(f"Missing extension manifest: {extension_dir / 'manifest.json'}")

    output_dir.mkdir(parents=True, exist_ok=True)
    host_zip = output_dir / "EasyMP3-native-host.zip"
    extension_zip = output_dir / "EasyMP3-extension.zip"

    with ZipFile(host_zip, "w", ZIP_DEFLATED) as archive:
        _write_tree(archive, host_dir, "native-host")
        for name in ("install-native-host.ps1", "uninstall-native-host.ps1"):
            archive.write(scripts_dir / name, f"native-host/{name}")

    with ZipFile(extension_zip, "w", ZIP_DEFLATED) as archive:
        for path in sorted(extension_dir.rglob("*")):
            relative = path.relative_to(extension_dir)
            if path.is_file() and not any(part in EXTENSION_EXCLUDES for part in relative.parts):
                archive.write(path, Path("extension", relative).as_posix())

    return host_zip, extension_zip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("package"))
    args = parser.parse_args()
    package_release(args.repo_root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
