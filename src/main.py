import sys
import tkinter as tk

from app import EasyMP3App, show_choice_dialog
from config import BIN_DIR, FFMPEG_PATH, YTDLP_PATH
from utils import prepare_external_subprocesses


def check_dependencies(root):
    """Check if yt-dlp and ffmpeg executables exist."""
    if not YTDLP_PATH.is_file():
        show_choice_dialog(root, "Dependency Error", f"Error: yt-dlp.exe not found in expected location: {BIN_DIR}", [("OK", True)])
        return False
    if not FFMPEG_PATH.is_file():
        show_choice_dialog(root, "Dependency Error", f"Error: ffmpeg.exe not found in expected location: {BIN_DIR}", [("OK", True)])
        return False
    return True


if __name__ == "__main__":
    # Dependencies checked by check_dependencies() called earlier if needed
    # Recommend installing dependencies if running directly:
    # pip install pyperclip sv_ttk

    root = tk.Tk()
    root.withdraw()

    if not check_dependencies(root):
        root.destroy()
        sys.exit(1)  # Exit if yt-dlp/ffmpeg dependencies are missing

    prepare_external_subprocesses()
    app = EasyMP3App(root)
    root.deiconify()
    root.mainloop()
