import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def get_base_path():
    """Gets the base path for bundled resources (project root for script, temp dir for frozen exe)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent


def get_run_directory():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent


BASE_PATH = get_base_path()
BIN_DIR = BASE_PATH / "bin"
YT_DLP_PATH = BIN_DIR / "yt-dlp.exe"
FFMPEG_PATH = BIN_DIR / "ffmpeg.exe"

DEFAULT_OUTPUT_DIR = get_run_directory()


def check_dependencies():
    if not YT_DLP_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: yt-dlp.exe not found in expected location: {BIN_DIR}")
        return False
    if not FFMPEG_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: ffmpeg.exe not found in expected location: {BIN_DIR}")
        return False
    return True


def download_audio(link, output_dir, status_callback):
    status_callback(f"Starting download for: {link.strip()}")
    temp_download_subdir = output_dir / f"_temp_dl_{os.urandom(4).hex()}"
    temp_download_subdir.mkdir(parents=True, exist_ok=True)

    output_template = temp_download_subdir / "%(channel)s - %(title)s.%(ext)s"

    command = [
        str(YT_DLP_PATH),
        "-f", "bestaudio/best",
        "--ignore-errors",
        "-o", str(output_template),
        "--no-simulate",
        "--embed-thumbnail",
        "--extract-audio",
        "--audio-quality", "0",
        "--audio-format", "mp3",
        link.strip()
    ]

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        status_callback(f"Finished download for: {link.strip()}")

        downloaded_files = list(temp_download_subdir.glob('*.mp3'))
        if not downloaded_files:
            status_callback(f"Error: No MP3 file found after download for {link.strip()} in {temp_download_subdir}")
            return None
        if len(downloaded_files) > 1:
            status_callback(f"Warning: Multiple MP3 files found after download for {link.strip()}, using first: {downloaded_files[0].name}")

        original_mp3_path = downloaded_files[0]
        final_mp3_path = output_dir / original_mp3_path.name

        try:
            original_mp3_path.rename(final_mp3_path)
        except OSError as move_err:
            status_callback(f"Error moving {original_mp3_path.name} to {output_dir}: {move_err}")
            return None
        finally:
            try:
                os.rmdir(temp_download_subdir)
            except OSError:
                pass

        return final_mp3_path

    except subprocess.CalledProcessError as e:
        status_callback(f"Error downloading {link.strip()}: {e}")
        status_callback(f"yt-dlp Stderr:\n{e.stderr}")
        try:
            import shutil
            shutil.rmtree(temp_download_subdir)
        except OSError:
            pass
        return None
    except Exception as e:
        status_callback(f"An unexpected error occurred during download for {link.strip()}: {e}")
        try:
            import shutil
            shutil.rmtree(temp_download_subdir)
        except OSError:
            pass
        return None


def crop_thumbnail(mp3_file, status_callback):
    if not mp3_file or not mp3_file.exists() or mp3_file.suffix.lower() != '.mp3':
        status_callback(f"Skipping thumbnail crop: Invalid input file {mp3_file}")
        return False

    status_callback(f"Processing thumbnail for: {mp3_file.name}")
    base_name = mp3_file.stem
    temp_dir = mp3_file.parent
    temp_image_name = temp_dir / f"{base_name}_temp_thumb.jpg"
    cropped_image_name = temp_dir / f"{base_name}_temp_thumb_cropped.jpg"
    final_track_name = temp_dir / f"{base_name}_temp_final.mp3"

    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW

        cmd_extract = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3_file), str(temp_image_name)]
        result_extract = subprocess.run(cmd_extract, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        if result_extract.returncode != 0:
            if "error retrieving cover art" in result_extract.stderr.lower() or "attached picture extraction failed" in result_extract.stderr.lower():
                status_callback(f"No thumbnail found in {mp3_file.name}. Skipping crop.")
                return True
            else:
                status_callback(f"ffmpeg error extracting thumbnail from {mp3_file.name}:\n{result_extract.stderr}")
                return False

        if not temp_image_name.exists():
            status_callback(f"Thumbnail file {temp_image_name} not found after extraction attempt for {mp3_file.name}. Skipping crop.")
            return False

        cmd_crop = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp_image_name), "-vf", "crop=ih:ih", str(cropped_image_name)]
        result_crop = subprocess.run(cmd_crop, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        if result_crop.returncode != 0:
            status_callback(f"ffmpeg error cropping thumbnail for {mp3_file.name}:\n{result_crop.stderr}")
            if temp_image_name.exists(): os.remove(temp_image_name)
            return False

        cmd_embed = [
            str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(mp3_file),
            "-i", str(cropped_image_name),
            "-map_metadata", "0",
            "-map_metadata:s:1", "0:s:1",
            "-map", "0:a",
            "-map", "1",
            "-c:a", "copy",
            str(final_track_name)
        ]
        result_embed = subprocess.run(cmd_embed, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        if result_embed.returncode != 0:
            status_callback(f"ffmpeg error re-embedding thumbnail for {mp3_file.name}:\n{result_embed.stderr}")
            if temp_image_name.exists(): os.remove(temp_image_name)
            if cropped_image_name.exists(): os.remove(cropped_image_name)
            return False

        os.remove(temp_image_name)
        os.remove(cropped_image_name)
        os.remove(mp3_file)
        os.rename(final_track_name, mp3_file)
        status_callback(f"Successfully processed thumbnail for: {mp3_file.name}")
        return True

    except subprocess.CalledProcessError as e:
        status_callback(f"ffmpeg error processing {mp3_file.name}: {e}")
        if temp_image_name.exists(): os.remove(temp_image_name)
        if cropped_image_name.exists(): os.remove(cropped_image_name)
        if final_track_name.exists(): os.remove(final_track_name)
        return False
    except Exception as e:
        status_callback(f"An unexpected error occurred processing {mp3_file.name}: {e}")
        if temp_image_name.exists(): os.remove(temp_image_name)
        if cropped_image_name.exists(): os.remove(cropped_image_name)
        if final_track_name.exists(): os.remove(final_track_name)
        return False


class EasyMP3App:
    def __init__(self, master):
        self.master = master
        master.title("EasyMP3 Downloader & Cropper")
        master.geometry("600x450")

        self.output_dir = tk.StringVar(master, value=str(DEFAULT_OUTPUT_DIR))
        self.youtube_url = tk.StringVar(master)
        self.is_processing = False

        tk.Label(master, text="YouTube URL:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.url_entry = tk.Entry(master, textvariable=self.youtube_url, width=60)
        self.url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=5, pady=5)

        tk.Label(master, text="Output Folder:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.output_entry = tk.Entry(master, textvariable=self.output_dir, state="readonly", width=50)
        self.output_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.browse_button = tk.Button(master, text="Browse...", command=self.browse_output_dir)
        self.browse_button.grid(row=1, column=2, sticky="ew", padx=5, pady=5)

        self.start_button = tk.Button(master, text="Start Download & Crop", command=self.start_processing)
        self.start_button.grid(row=2, column=0, columnspan=3, pady=10)

        tk.Label(master, text="Status:").grid(row=3, column=0, sticky="nw", padx=5, pady=5)
        self.status_text = scrolledtext.ScrolledText(master, height=15, width=70, state="disabled")
        self.status_text.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        master.grid_columnconfigure(1, weight=1)
        master.grid_rowconfigure(4, weight=1)

    def browse_output_dir(self):
        directory = filedialog.askdirectory(initialdir=self.output_dir.get(), title="Select Output Folder")
        if directory:
            self.output_dir.set(directory)

    def update_status(self, message):
        def _update():
            self.status_text.config(state="normal")
            self.status_text.insert(tk.END, message + "\n")
            self.status_text.see(tk.END)
            self.status_text.config(state="disabled")
        self.master.after(0, _update)

    def start_processing(self):
        if self.is_processing:
            self.update_status("Already processing!")
            return

        url = self.youtube_url.get().strip()
        output_path_str = self.output_dir.get()

        if not url:
            messagebox.showwarning("Input Error", "Please enter a YouTube URL.")
            return

        if not output_path_str:
            messagebox.showwarning("Input Error", "Please select an output folder.")
            return

        output_path = Path(output_path_str)
        output_path.mkdir(parents=True, exist_ok=True)

        if not check_dependencies():
            return

        self.start_button.config(state="disabled", text="Processing...")
        self.status_text.config(state="normal")
        self.status_text.delete('1.0', tk.END)
        self.status_text.config(state="disabled")
        self.is_processing = True
        self.update_status(f"Starting process for URL: {url}")
        self.update_status(f"Output folder: {output_path}")

        thread = threading.Thread(target=self.processing_thread, args=(url, output_path), daemon=True)
        thread.start()

    def processing_thread(self, url, output_path):
        final_mp3_file = None
        try:
            self.update_status("--- Starting Download --- ")
            final_mp3_file = download_audio(url, output_path, self.update_status)
            if final_mp3_file:
                self.update_status("--- Download Complete --- ")
                self.update_status("--- Starting Thumbnail Crop --- ")
                crop_success = crop_thumbnail(final_mp3_file, self.update_status)
                if crop_success:
                    self.update_status("--- Thumbnail Crop Complete --- ")
                else:
                    self.update_status("--- Thumbnail Crop Failed (see errors above) --- ")
            else:
                self.update_status("--- Download Failed (see errors above) --- ")

            self.update_status("\nProcessing finished.")

        except Exception as e:
            self.update_status(f"\nAn unexpected error occurred in processing thread: {e}")
            import traceback
            self.update_status(f"Traceback:\n{traceback.format_exc()}")
        finally:
            self.master.after(0, self.processing_finished)

    def processing_finished(self):
        self.is_processing = False
        self.start_button.config(state="normal", text="Start Download & Crop")


if __name__ == "__main__":
    root = tk.Tk()
    app = EasyMP3App(root)
    root.mainloop()
