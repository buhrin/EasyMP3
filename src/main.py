import sys
import tkinter as tk
from tkinter import messagebox

from app import EasyMP3App
from config import BIN_DIR, FFMPEG_PATH, YTDLP_PATH


def check_dependencies():
    """Check if yt-dlp and ffmpeg executables exist."""
    if not YTDLP_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: yt-dlp.exe not found in expected location: {BIN_DIR}")
        return False
    if not FFMPEG_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: ffmpeg.exe not found in expected location: {BIN_DIR}")
        return False
    return True


if __name__ == "__main__":
    # Dependencies checked by check_dependencies() called earlier if needed
    # Recommend installing dependencies if running directly:
    # pip install pyperclip sv_ttk

    if not check_dependencies():
        sys.exit(1)  # Exit if yt-dlp/ffmpeg dependencies are missing

    root = tk.Tk()
    app = EasyMP3App(root)
    root.mainloop()
