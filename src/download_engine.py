import logging
import os
import shutil
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config import FFMPEG_PATH, YTDLP_PATH
from ffmpeg_wrapper import crop_thumbnail
from ytdlp_wrapper import DownloadError, download_audio

LOGGER = logging.getLogger(__name__)
TaskUpdate = Callable[[str, str, str], None]


@dataclass(frozen=True)
class DownloadResult:
    success: bool
    output_path: Path | None = None
    error: str | None = None


_target_locks: dict[str, tuple[threading.Lock, int]] = {}
_target_locks_guard = threading.Lock()
_STAGING_PREFIX = ".easymp3-"


@contextmanager
def _target_lock(path: Path):
    key = os.path.normcase(str(path.resolve()))
    with _target_locks_guard:
        lock, users = _target_locks.get(key, (threading.Lock(), 0))
        _target_locks[key] = (lock, users + 1)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _target_locks_guard:
            current_lock, users = _target_locks[key]
            if users == 1:
                del _target_locks[key]
            else:
                _target_locks[key] = (current_lock, users - 1)


def run_download(task_id: str, url: str, output_path: str | Path, update_task: TaskUpdate) -> DownloadResult:
    """Download and process one track, then atomically publish it."""
    destination = Path(output_path)
    staging_dir = destination / f"{_STAGING_PREFIX}{task_id}-{uuid.uuid4().hex}"

    try:
        destination.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir()
        staged_mp3, _ = download_audio(
            task_id,
            url,
            staging_dir,
            YTDLP_PATH,
            update_task,
            ffmpeg_path=FFMPEG_PATH,
        )
        if not crop_thumbnail(task_id, staged_mp3, FFMPEG_PATH, update_task):
            return DownloadResult(False, error="Thumbnail processing failed")

        target = destination / staged_mp3.name
        with _target_lock(target):
            os.replace(staged_mp3, target)
        update_task(task_id, "Status", "Completed")
        return DownloadResult(True, output_path=target)
    except DownloadError as error:
        LOGGER.error("Download job %s failed: %s", task_id, error)
        return DownloadResult(False, error=str(error) or error.__class__.__name__)
    except Exception as error:
        LOGGER.exception("Download job %s failed", task_id)
        try:
            update_task(task_id, "Status", "Error: Unexpected")
        except Exception:
            LOGGER.exception("Could not report failure for download job %s", task_id)
        return DownloadResult(False, error=str(error) or error.__class__.__name__)
    finally:
        try:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
        except OSError:
            LOGGER.exception("Could not clean staging directory %s", staging_dir)
