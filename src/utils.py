import re
import subprocess
import sys
from pathlib import Path


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


def truncate_display_value(value, max_length=60):
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def is_valid_youtube_url(url):
    youtube_regex = r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
    return re.match(youtube_regex, url)
