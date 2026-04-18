import sys

from utils import get_base_path, get_run_directory

MAX_WORKERS = 10
ICON_NAME = "icon.ico"

BASE_PATH = get_base_path()
BIN_DIR = BASE_PATH / "bin"
YTDLP_PATH = BIN_DIR / "yt-dlp.exe"
FFMPEG_PATH = BIN_DIR / "ffmpeg.exe"

if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
    ASSETS_DIR = BASE_PATH / "assets"
else:
    ASSETS_DIR = BASE_PATH / "src" / "assets"

ICON_PATH = ASSETS_DIR / ICON_NAME
DEFAULT_OUTPUT_DIR = get_run_directory()

TERMINAL_TASK_STATUSES = {
    "Completed",
    "Error: Download failed",
    "Error: Crop failed",
    "Error: Embed failed",
    "Error: Unexpected",
    "Error: File Missing",
    "Error: MP3 file not found",
    "Error: Extract failed",
    "Error: Embed File Missing",
    "Error: Crop File Missing",
    "Error: Unexpected Worker",
}
