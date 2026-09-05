import ctypes
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
}
SHORT_YOUTUBE_HOSTS = {"youtu.be", "www.youtu.be"}
_external_subprocesses_prepared = False


@dataclass(frozen=True)
class ParsedYouTubeUrl:
    kind: str
    video_id: str | None = None
    playlist_id: str | None = None

    @property
    def video_url(self):
        if not self.video_id:
            return None
        return build_video_url(self.video_id)

    @property
    def playlist_url(self):
        if not self.playlist_id:
            return None
        return build_playlist_url(self.playlist_id)


def get_base_path():
    """Get the base path for bundled resources or the project root."""
    meipass_path = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass_path:
        return Path(meipass_path)
    return Path(__file__).parent.parent


def get_run_directory():
    """Get the directory containing the running executable or script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def get_subprocess_creationflags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def prepare_external_subprocesses():
    """Restore the normal Windows DLL search path for external executables.

    PyInstaller sets a process-wide DLL directory for bundled Python modules.
    External yt-dlp and FFmpeg processes must not inherit that directory. Call
    this once on the main thread, after bundled modules have been imported and
    before worker threads start.
    """
    global _external_subprocesses_prepared
    if _external_subprocesses_prepared:
        return

    if sys.platform == "win32" and getattr(sys, "frozen", False):
        if not ctypes.windll.kernel32.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())

    _external_subprocesses_prepared = True


def truncate_display_value(value, max_length=60):
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def build_video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def build_playlist_url(playlist_id):
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def parse_youtube_url(url):
    if not url:
        return None

    candidate = url.strip()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed_url = urlparse(candidate)
    host = parsed_url.netloc.lower()
    path = parsed_url.path.strip("/")
    query = parse_qs(parsed_url.query)

    video_id = None
    playlist_id = _extract_single_query_value(query, "list")

    if host in SHORT_YOUTUBE_HOSTS:
        video_id = path.split("/", 1)[0] if path else None
    elif host in YOUTUBE_HOSTS:
        path_parts = [part for part in path.split("/") if part]
        if path == "watch":
            video_id = _extract_single_query_value(query, "v")
        elif path == "playlist":
            video_id = None
        elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "live"}:
            video_id = path_parts[1]
        elif path_parts:
            maybe_video_id = path_parts[-1]
            if len(maybe_video_id) == 11:
                video_id = maybe_video_id
    else:
        return None

    if video_id and playlist_id:
        return ParsedYouTubeUrl(kind="video_in_playlist", video_id=video_id, playlist_id=playlist_id)
    if playlist_id and (path == "playlist" or not video_id):
        return ParsedYouTubeUrl(kind="playlist", playlist_id=playlist_id)
    if video_id:
        return ParsedYouTubeUrl(kind="video", video_id=video_id)
    return None


def is_valid_youtube_url(url):
    return parse_youtube_url(url) is not None


def _extract_single_query_value(query, key):
    values = query.get(key)
    if not values:
        return None
    value = values[0].strip()
    if not value:
        return None
    return value
