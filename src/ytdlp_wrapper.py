import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils import build_video_url, get_subprocess_creationflags

YOUTUBE_EXTRACTOR_ARGS = "youtube:player_client=android,web"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaylistEntry:
    video_id: str
    title: str
    url: str


@dataclass(frozen=True)
class PlaylistInspectionResult:
    title: str
    playlist_id: str | None
    entries: list[PlaylistEntry]
    unavailable_count: int


class DownloadError(RuntimeError):
    """Raised when yt-dlp cannot produce the requested MP3."""


def download_audio(task_id, link, output_dir, ytdlp_path, update_task, ffmpeg_path=None):
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
            "--extractor-args",
            YOUTUBE_EXTRACTOR_ARGS,
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
        ]
        if ffmpeg_path is not None:
            command.extend(["--ffmpeg-location", str(Path(ffmpeg_path).parent)])
        command.append(link.strip())

        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=get_subprocess_creationflags(),
        )
        if result.stderr:
            LOGGER.debug("yt-dlp stderr: %s", result.stderr)

        downloaded_files = list(temp_download_subdir.glob("*.mp3"))
        if not downloaded_files:
            raise FileNotFoundError(f"No MP3 file found in {temp_download_subdir} after download.")

        original_mp3_path = downloaded_files[0]
        update_task(task_id, "Filename", original_mp3_path.name)

        target_mp3_path = Path(output_dir) / original_mp3_path.name
        shutil.move(str(original_mp3_path), str(target_mp3_path))
        LOGGER.debug("Moved %s to %s", original_mp3_path.name, target_mp3_path)
        return target_mp3_path, temp_download_subdir

    except subprocess.CalledProcessError as error:
        update_task(task_id, "Status", "Error: Download failed")
        LOGGER.error("Download failed: %s\nStderr:\n%s", error, error.stderr)
        _cleanup_temp_directory(temp_download_subdir)
        raise DownloadError("Download failed") from error
    except FileNotFoundError as error:
        update_task(task_id, "Status", "Error: File Missing")
        LOGGER.error("Required download file is missing: %s", error)
        _cleanup_temp_directory(temp_download_subdir)
        raise DownloadError(str(error)) from error
    except Exception as error:
        update_task(task_id, "Status", "Error: Download failed")
        LOGGER.exception("Unexpected error during download")
        _cleanup_temp_directory(temp_download_subdir)
        raise DownloadError(str(error)) from error


def inspect_playlist_metadata(playlist_url, ytdlp_path):
    command = [
        str(ytdlp_path),
        "--flat-playlist",
        "--dump-single-json",
        "--extractor-args",
        YOUTUBE_EXTRACTOR_ARGS,
        "--ignore-errors",
        "--quiet",
        "--no-warnings",
        playlist_url.strip(),
    ]

    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=get_subprocess_creationflags(),
    )

    payload = json.loads(result.stdout)
    title = payload.get("title") or payload.get("playlist_title") or "Playlist"
    playlist_id = payload.get("id")

    entries = []
    unavailable_count = 0
    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            unavailable_count += 1
            continue

        video_id = entry.get("id") or entry.get("url")
        if not video_id:
            unavailable_count += 1
            continue

        entry_title = entry.get("title") or f"Video {len(entries) + 1}"
        entries.append(
            PlaylistEntry(
                video_id=video_id,
                title=entry_title,
                url=build_video_url(video_id),
            )
        )

    return PlaylistInspectionResult(
        title=title,
        playlist_id=playlist_id,
        entries=entries,
        unavailable_count=unavailable_count,
    )


def _cleanup_temp_directory(temp_download_subdir):
    try:
        if temp_download_subdir.exists():
            shutil.rmtree(temp_download_subdir)
    except Exception as cleanup_error:
        LOGGER.warning("Could not clean temporary directory %s: %s", temp_download_subdir, cleanup_error)
