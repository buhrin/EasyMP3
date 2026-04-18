import os
import shutil
import subprocess
from pathlib import Path

from utils import get_subprocess_creationflags


def download_audio(task_id, link, output_dir, ytdlp_path, update_task):
    """Download a single YouTube URL to MP3 and return the final file path."""
    update_task(task_id, "Status", "Downloading...")

    temp_download_subdir = Path(output_dir) / f"_temp_dl_{os.urandom(4).hex()}"
    try:
        temp_download_subdir.mkdir(parents=True, exist_ok=True)
        output_template = str(temp_download_subdir / "%(channel)s - %(title)s.%(ext)s")

        command = [
            str(ytdlp_path),
            "-f",
            "bestaudio/best",
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output",
            output_template,
            "--force-overwrite",
            "--no-progress",
            link.strip(),
        ]

        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=get_subprocess_creationflags(),
        )
        print("yt-dlp stderr:", result.stderr)

        downloaded_files = list(temp_download_subdir.glob("*.mp3"))
        if not downloaded_files:
            raise FileNotFoundError(f"No MP3 file found in {temp_download_subdir} after download.")

        original_mp3_path = downloaded_files[0]
        update_task(task_id, "Filename", original_mp3_path.name)

        target_mp3_path = Path(output_dir) / original_mp3_path.name
        shutil.move(str(original_mp3_path), str(target_mp3_path))
        print(f"Moved {original_mp3_path.name} to {target_mp3_path}")
        return target_mp3_path, temp_download_subdir

    except subprocess.CalledProcessError as error:
        update_task(task_id, "Status", "Error: Download failed")
        print(f"Error during download: {error}\nStderr:\n{error.stderr}")
    except FileNotFoundError as error:
        update_task(task_id, "Status", "Error: File Missing")
        print(f"Error: {error}")
    except Exception as error:
        update_task(task_id, "Status", "Error: Download failed")
        print(f"An unexpected error occurred during download: {error}")

    _cleanup_temp_directory(temp_download_subdir)
    return None, None


def _cleanup_temp_directory(temp_download_subdir):
    try:
        if temp_download_subdir.exists():
            shutil.rmtree(temp_download_subdir)
    except Exception as cleanup_error:
        print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
