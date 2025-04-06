import os
import subprocess
import sys
import threading
import tkinter as tk
import queue
import re
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil

# Max concurrent downloads
MAX_WORKERS = 10

def get_base_path():
    """Gets the base path for bundled resources (project root for script, temp dir for frozen exe)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    else:
        return Path(__file__).parent.parent

def get_run_directory():
    """Gets the directory where the script/exe is running."""
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
    """Checks if yt-dlp and ffmpeg executables exist."""
    if not YT_DLP_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: yt-dlp.exe not found in expected location: {BIN_DIR}")
        return False
    if not FFMPEG_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: ffmpeg.exe not found in expected location: {BIN_DIR}")
        return False
    return True

# --- Helper to update Treeview safely from other threads ---
def schedule_gui_update(app, item_id, column, value):
    # Truncate long status messages before sending to GUI thread
    if column == "status" and isinstance(value, str) and len(value) > 60:
        value = value[:57] + "..."
    app.root.after_idle(app.update_task_status, item_id, column, value)

def download_audio(task_id, link, output_dir, status_callback, app):
    """Downloads audio, extracts MP3, and embeds thumbnail using original command."""
    schedule_gui_update(app, task_id, "status", "Downloading...")

    temp_download_subdir = output_dir / f"_temp_dl_{os.urandom(4).hex()}"
    temp_download_subdir.mkdir(parents=True, exist_ok=True)

    # Use the original output template structure
    output_template = temp_download_subdir / "%(channel)s - %(title)s.%(ext)s"

    # --- Use ORIGINAL yt-dlp command --- Restored
    command = [
        str(YT_DLP_PATH),
        "-f", "bestaudio/best",
        "--ignore-errors",
        "-o", str(output_template),
        "--no-simulate",
        "--embed-thumbnail",  # Embeds thumbnail during download
        "--extract-audio",
        "--audio-quality", "0",
        "--audio-format", "mp3",
        link.strip()  # Use original link.strip()
    ]

    try:
        schedule_gui_update(app, task_id, "status", "Running yt-dlp...")
        # Run yt-dlp, capture output
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        print("yt-dlp stdout:", process.stdout)
        print("yt-dlp stderr:", process.stderr)

        # Find the downloaded MP3 file (should be only one)
        downloaded_files = list(temp_download_subdir.glob('*.mp3'))
        if not downloaded_files:
            raise FileNotFoundError(f"No MP3 file found in {temp_download_subdir} after download.")

        original_mp3_path = downloaded_files[0]
        schedule_gui_update(app, task_id, "filename", original_mp3_path.name)

        schedule_gui_update(app, task_id, "status", "Download complete")

        # Move the final MP3 file to the target output directory
        target_mp3_path = output_dir / original_mp3_path.name
        shutil.move(str(original_mp3_path), str(target_mp3_path))  # Use shutil.move
        print(f"Moved {original_mp3_path.name} to {target_mp3_path}")

        # Return the path to the final MP3 and the temp dir path for cleanup later
        return target_mp3_path, temp_download_subdir  # Modified return value

    except subprocess.CalledProcessError as e:
        error_message = f"yt-dlp failed (Code: {e.returncode}). Check URL? Stderr: {e.stderr[:200]}..."
        schedule_gui_update(app, task_id, "status", f"Error: Download failed")
        print(f"Error during download: {e}\nStderr:\n{e.stderr}")
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None  # Modified return value
    except FileNotFoundError as e:
        error_message = "MP3 file not found post-download."
        schedule_gui_update(app, task_id, "status", f"Error: {error_message}")
        print(f"Error: {e}")
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None  # Modified return value
    except Exception as e:
        error_message = f"An unexpected error occurred during download: {e}"
        schedule_gui_update(app, task_id, "status", f"Error: Download failed")
        print(error_message)
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None  # Modified return value

# --- Restored original crop_thumbnail logic --- Modified
def crop_thumbnail(task_id, mp3_file, status_callback, app):
    """Extracts, crops, and re-embeds the thumbnail using original ffmpeg logic."""
    if not mp3_file or not mp3_file.exists() or mp3_file.suffix.lower() != '.mp3':
        schedule_gui_update(app, task_id, "status", f"Crop Skip: Invalid MP3")
        print(f"Skipping thumbnail crop: Invalid input file {mp3_file}")
        return False  # Indicate skip/failure

    schedule_gui_update(app, task_id, "status", "Processing thumbnail...")

    # Define temporary file paths within the MP3's directory
    base_name = mp3_file.stem
    temp_dir = mp3_file.parent  # Crop happens in the final output dir
    temp_image_name = temp_dir / f"{base_name}_temp_thumb.jpg"
    cropped_image_name = temp_dir / f"{base_name}_temp_thumb_cropped.jpg"
    final_track_name = temp_dir / f"{base_name}_temp_final.mp3"  # Temp file for re-embedding

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        # 1. Extract Thumbnail
        schedule_gui_update(app, task_id, "status", "Extracting thumbnail...")
        cmd_extract = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3_file), str(temp_image_name)]
        result_extract = subprocess.run(cmd_extract, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)

        if result_extract.returncode != 0:
            # Check common ffmpeg message for missing art
            if "error retrieving cover art" in result_extract.stderr.lower() or "attached picture extraction failed" in result_extract.stderr.lower():
                schedule_gui_update(app, task_id, "status", "No thumbnail found")
                print(f"No thumbnail found in {mp3_file.name}. Skipping crop.")
                return True  # Not an error, just no thumbnail to crop
            else:
                schedule_gui_update(app, task_id, "status", "Error: Extract failed")
                print(f"ffmpeg error extracting thumbnail from {mp3_file.name}:\n{result_extract.stderr}")
                return False  # Extraction failed

        if not temp_image_name.exists():
            schedule_gui_update(app, task_id, "status", "No thumbnail found")  # Treat as if not found
            print(f"Thumbnail file {temp_image_name} not found after extraction attempt for {mp3_file.name}. Skipping crop.")
            return True  # Not an error, just no thumbnail to crop

        # 2. Crop Thumbnail
        schedule_gui_update(app, task_id, "status", "Cropping thumbnail...")
        cmd_crop = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp_image_name), "-vf", "crop=ih:ih", str(cropped_image_name)]
        result_crop = subprocess.run(cmd_crop, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        print(f"ffmpeg crop stdout: {result_crop.stdout}")
        print(f"ffmpeg crop stderr: {result_crop.stderr}")

        if not cropped_image_name.exists():
            raise FileNotFoundError("Cropped image file not found after ffmpeg crop operation.")

        # 3. Re-embed Cropped Thumbnail
        schedule_gui_update(app, task_id, "status", "Re-embedding...")
        cmd_embed = [
            str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(mp3_file),  # Input MP3
            "-i", str(cropped_image_name),  # Input Cropped JPG
            "-map", "0:a",  # Map audio from first input
            "-map", "1",  # Map *all* streams from second input (the image)
            "-c", "copy",  # Copy streams (audio unchanged)
            "-id3v2_version", "3",  # Use ID3v2.3 for compatibility
            "-metadata:s:v", "title=Album cover",  # Set metadata for the image stream
            "-metadata:s:v", "comment=Cover (front)",
            str(final_track_name)  # Output to temporary MP3
        ]
        result_embed = subprocess.run(cmd_embed, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        print(f"ffmpeg embed stdout: {result_embed.stdout}")
        print(f"ffmpeg embed stderr: {result_embed.stderr}")

        if not final_track_name.exists():
            raise FileNotFoundError("Final MP3 with re-embedded thumbnail not found.")

        # 4. Replace original MP3 with the new one
        schedule_gui_update(app, task_id, "status", "Finalizing...")
        os.replace(str(final_track_name), str(mp3_file))  # Use os.replace for atomic move/replace

        schedule_gui_update(app, task_id, "status", "Crop complete")
        print(f"Successfully processed thumbnail for: {mp3_file.name}")
        return True  # Success

    except subprocess.CalledProcessError as e:
        error_message = f"ffmpeg error (Code: {e.returncode}) processing {mp3_file.name}. Stderr: {e.stderr[:200]}..."
        schedule_gui_update(app, task_id, "status", "Error: Crop failed")
        print(f"{error_message}\nFull stderr:\n{e.stderr}")
        return False  # Indicate failure
    except FileNotFoundError as e:
        error_message = f"File not found during thumbnail processing: {e}"
        schedule_gui_update(app, task_id, "status", "Error: Crop File Missing")
        print(error_message)
        return False  # Indicate failure
    except Exception as e:
        error_message = f"Unexpected error processing {mp3_file.name}: {e}"
        schedule_gui_update(app, task_id, "status", "Error: Crop failed")
        print(error_message)
        import traceback
        traceback.print_exc()  # Print full traceback for unexpected errors
        return False  # Indicate failure
    finally:
        # 5. Clean up temporary files
        for temp_file in [temp_image_name, cropped_image_name, final_track_name]:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    print(f"Cleaned up temp file: {temp_file}")
            except OSError as e:
                print(f"Error cleaning up temp file {temp_file}: {e}")

# --- Task processing function --- Modified
def process_task(task_id, url, output_path, app):
    """Wrapper function to run download and crop for a single task."""
    mp3_path, temp_dir = None, None  # Adjusted variables
    try:
        # Call updated download_audio
        mp3_path, temp_dir = download_audio(task_id, url, output_path, schedule_gui_update, app)

        if mp3_path:  # Check if download succeeded
            # Call updated crop_thumbnail (passing only mp3_path)
            crop_result = crop_thumbnail(task_id, mp3_path, schedule_gui_update, app)
            if crop_result:  # True means success or skipped (no thumb)
                # Final status depends if cropping actually happened or was skipped
                # We check the last status set by crop_thumbnail for accuracy
                # This requires crop_thumbnail to reliably set the final status message
                # For simplicity now, just mark Completed if crop didn't return False
                schedule_gui_update(app, task_id, "status", "Completed")
            else:  # False means cropping failed
                schedule_gui_update(app, task_id, "status", "Completed (Crop Failed)")
        else:
            # Download failed, status already set by download_audio
            pass  # Keep error status from download function

    except Exception as e:
        print(f"Unhandled exception in process_task for {url}: {e}")
        schedule_gui_update(app, task_id, "status", "Error: Processing failed")
        import traceback
        traceback.print_exc()
    finally:
        # Final cleanup of the temporary download directory
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp directory: {temp_dir}")
            except Exception as cleanup_error:
                print(f"Error cleaning up final temp directory {temp_dir}: {cleanup_error}")

        # Signal completion to the task manager
        app.task_queue.task_done()  # Let the manager know one task finished
        # Update the count of active workers
        with app.active_workers_lock:
            app.active_workers -= 1
        print(f"Task {task_id} finished. Active workers: {app.active_workers}")
        # Manager thread will automatically check queue for next task

# --- Main Application Class --- (UI setup remains the same)
class EasyMP3App:
    def __init__(self, root):
        self.root = root
        self.root.title("EasyMP3 Downloader")
        self.root.geometry("800x600")

        # --- State Variables ---
        self.active_workers = 0  # Count of tasks currently running
        self.active_workers_lock = threading.Lock()  # Lock for the counter
        self.task_queue = queue.Queue()  # Queue for pending tasks
        self.task_details = {}  # Dictionary to store task info {item_id: {details...}}
        self.next_task_id = 0  # Simple counter for unique Treeview item IDs

        # --- Thread Pool Executor ---
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

        # --- UI Elements ---
        self.setup_ui()

        # --- Start Task Manager Thread ---
        self.manager_thread = threading.Thread(target=self.task_manager, daemon=True)
        self.manager_thread.start()

        # --- Graceful Shutdown ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # Frame for inputs
        input_frame = tk.Frame(self.root)
        input_frame.pack(pady=10, padx=10, fill=tk.X)

        # YouTube URL input
        tk.Label(input_frame, text="YouTube URL:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.youtube_url = tk.StringVar()
        self.url_entry = tk.Entry(input_frame, textvariable=self.youtube_url, width=60)
        self.url_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        # Output directory input
        tk.Label(input_frame, text="Output Folder:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.output_dir = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.dir_entry = tk.Entry(input_frame, textvariable=self.output_dir, width=50)
        self.dir_entry.grid(row=1, column=1, padx=5, pady=5, sticky=tk.EW)
        self.browse_button = tk.Button(input_frame, text="Browse...", command=self.browse_folder)
        self.browse_button.grid(row=1, column=2, padx=5, pady=5)

        input_frame.columnconfigure(1, weight=1)  # Make entry expand

        # Start button
        self.start_button = tk.Button(self.root, text="Start Download & Crop", command=self.add_task)
        self.start_button.pack(pady=5, padx=10)

        # --- Treeview for Task Status ---
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("status", "filename", "url"), show="headings")
        self.tree.heading("status", text="Status")
        self.tree.heading("filename", text="Filename")
        self.tree.heading("url", text="URL")

        self.tree.column("status", width=150, anchor=tk.W)
        self.tree.column("filename", width=250, anchor=tk.W)
        self.tree.column("url", width=350, anchor=tk.W)

        # Scrollbars for Treeview
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def browse_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir.set(directory)

    def add_task(self):
        """Adds a new task to the queue and the Treeview."""
        url = self.youtube_url.get().strip()
        output_path_str = self.output_dir.get().strip()

        if not url:
            messagebox.showwarning("Input Error", "Please enter a YouTube URL.")
            return
        if not output_path_str:
            messagebox.showwarning("Input Error", "Please select an output folder.")
            return

        output_path = Path(output_path_str)
        if not output_path.is_dir():
            messagebox.showerror("Input Error", f"Output path is not a valid directory: {output_path}")
            return

        # Prevent adding duplicates? (Optional)
        # for item in self.tree.get_children():
        #     if self.tree.item(item, 'values')[2] == url:
        #         messagebox.showinfo("Duplicate", "This URL is already in the list.")
        #         return

        # Add item to Treeview
        item_id = f"task_{self.next_task_id}"
        self.next_task_id += 1
        self.tree.insert("", tk.END, iid=item_id, values=("Queued", "", url))  # Initial state

        # Store task details
        task_info = {
            "url": url,
            "output_path": output_path,
            "status": "Queued",
            "item_id": item_id
        }
        self.task_details[item_id] = task_info

        # Add task to the processing queue
        self.task_queue.put(task_info)

        # Clear the URL entry for the next input
        self.youtube_url.set("")
        self.url_entry.focus()  # Set focus back to URL entry

        print(f"Task {item_id} added to queue for URL: {url}")

    def update_task_status(self, item_id, column, value):
        """Safely updates a specific cell in the Treeview."""
        try:
            if self.tree.exists(item_id):
                current_values = list(self.tree.item(item_id, 'values'))
                # Find column index based on display columns order
                columns = self.tree['columns']
                if column in columns:
                    col_index = columns.index(column)
                    # Update the specific value
                    current_values[col_index] = value
                    self.tree.item(item_id, values=tuple(current_values))
                    # print(f"Updated Treeview item {item_id}, column '{column}' to: {value}")  # Reduce console noise
                else:
                    print(f"Warning: Column '{column}' not found in Treeview columns.")
            # else:
            #     print(f"Warning: Attempted to update non-existent item {item_id}")  # Can be noisy
        except Exception as e:
            print(f"Error updating Treeview for item {item_id}: {e}")

    def task_manager(self):
        """Monitors the task queue and submits tasks to the executor."""
        print("Task manager thread started.")
        while True:
            try:  # Add try-except for robustness
                # Check if we can start a new worker
                can_start_new = False
                with self.active_workers_lock:
                    if self.active_workers < MAX_WORKERS:
                        can_start_new = True

                if can_start_new:
                    try:
                        # Get a task from the queue, non-blocking
                        task_info = self.task_queue.get_nowait()
                    except queue.Empty:
                        # Queue is empty, wait a bit before checking again
                        time.sleep(0.5)  # Use time.sleep, Event is overkill here
                        continue  # Go back to the start of the loop

                    # We got a task and can start it
                    with self.active_workers_lock:
                        self.active_workers += 1

                    item_id = task_info['item_id']
                    url = task_info['url']
                    output_path = task_info['output_path']

                    print(f"Manager: Submitting task {item_id} ({url}). Active: {self.active_workers}/{MAX_WORKERS}")
                    # Update Treeview status to "Processing"
                    schedule_gui_update(self, item_id, "status", "Processing...")

                    # Submit the task processing function to the thread pool
                    # Pass necessary arguments including the app instance and task_id
                    self.executor.submit(process_task, item_id, url, output_path, self)
                else:
                    # Max workers reached, wait before checking again
                    # print(f"Manager: Max workers ({self.active_workers}/{MAX_WORKERS}) reached. Waiting...")
                    time.sleep(0.5)

            except Exception as e:  # Catch errors in manager loop
                print(f"!!! Error in Task Manager loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)  # Avoid busy-looping on error

            # Check for application exit signal? (Handled by daemon thread + executor shutdown)

    def on_closing(self):
        """Handles window closing: shutdown executor and exit."""
        print("Shutdown initiated.")
        # Optional: Ask user if they want to cancel ongoing tasks?
        if self.active_workers > 0:
            if not messagebox.askyesno("Confirm Exit", f"{self.active_workers} tasks are still running. Exit anyway? (Tasks will be completed)"):
                return  # Don't close yet

        messagebox.showinfo("Exiting", "Shutting down workers. Please wait for tasks to complete...")
        self.start_button.config(state="disabled")  # Disable adding more tasks
        self.executor.shutdown(wait=True)  # Wait for existing tasks to complete
        print("Executor shutdown complete.")
        self.root.destroy()

if __name__ == "__main__":
    import time  # Import time for sleep
    if not check_dependencies():
        sys.exit(1)  # Exit if dependencies are missing

    root = tk.Tk()
    app = EasyMP3App(root)
    root.mainloop()
