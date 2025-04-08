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
import uuid
import time
import pyperclip
import sv_ttk

# Max concurrent downloads
MAX_WORKERS = 10

ICON_NAME = "icon.ico" # Define icon filename

def get_base_path():
    """Gets the base path for bundled resources (project root for script, temp dir for frozen exe)."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running as a bundled executable
        return Path(sys._MEIPASS)
    else:
        # Running as a script
        return Path(__file__).parent.parent # Project root

def get_run_directory():
    """Gets the directory where the script/exe is running."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent

BASE_PATH = get_base_path()
BIN_DIR = BASE_PATH / "bin"
YTDLP_PATH = BIN_DIR / "yt-dlp.exe"
FFMPEG_PATH = BIN_DIR / "ffmpeg.exe"

# --- Determine Assets Path Correctly ---
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Frozen executable: Assets are relative to BASE_PATH (_MEIPASS)
    # based on `--add-data "src/assets;assets"` -> destination is "assets"
    ASSETS_DIR = BASE_PATH / "assets"
else:
    # Script: Assets are in src/assets relative to project root (BASE_PATH)
    ASSETS_DIR = BASE_PATH / "src" / "assets"

ICON_PATH = ASSETS_DIR / ICON_NAME

DEFAULT_OUTPUT_DIR = get_run_directory()

def check_dependencies():
    """Checks if yt-dlp and ffmpeg executables exist."""
    if not YTDLP_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: yt-dlp.exe not found in expected location: {BIN_DIR}")
        return False
    if not FFMPEG_PATH.is_file():
        messagebox.showerror("Dependency Error", f"Error: ffmpeg.exe not found in expected location: {BIN_DIR}")
        return False
    return True

# --- Helper to update Treeview safely from other threads ---
def schedule_gui_update(app, item_id, column, value):
    """Safely schedule a GUI update from a worker thread."""
    # Truncate long URLs/filenames for display if necessary
    if (column == "URL" or column == "Filename") and len(value) > 60:
        value = value[:57] + "..."
    # Call the correct update function name
    app.root.after_idle(app.update_task_display, item_id, column, value)

# --- Reverted download_audio logic ---
def download_audio(task_id, link, output_dir, status_callback, app):
    """Downloads audio, extracts MP3, and embeds thumbnail using original command."""
    schedule_gui_update(app, task_id, "Status", "Downloading...")

    # Create a temporary subdirectory within the *output* directory
    temp_download_subdir = Path(output_dir) / f"_temp_dl_{os.urandom(4).hex()}"
    try:
        temp_download_subdir.mkdir(parents=True, exist_ok=True)

        # Use the original output template structure pointing to the temp subdir
        output_template = str(temp_download_subdir / "%(channel)s - %(title)s.%(ext)s") # Restored channel name

        command = [
            str(YTDLP_PATH),
            "-f", "bestaudio/best",
            "--no-playlist",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--embed-thumbnail",
            "--add-metadata",
            "--output", output_template, # Output to temp subdir
            "--force-overwrite", # Overwrite existing files
            "--no-progress",
            link.strip()
        ]

        # schedule_gui_update(app, task_id, "Status", "Running yt-dlp...")
        # Run yt-dlp, capture output
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        # print("yt-dlp stdout:", result.stdout)
        print("yt-dlp stderr:", result.stderr)

        # Find the downloaded MP3 file (should be only one)
        downloaded_files = list(temp_download_subdir.glob('*.mp3'))
        if not downloaded_files:
            raise FileNotFoundError(f"No MP3 file found in {temp_download_subdir} after download.")

        original_mp3_path = downloaded_files[0]
        schedule_gui_update(app, task_id, "Filename", original_mp3_path.name)

        # schedule_gui_update(app, task_id, "Status", "Download complete")

        # Move the final MP3 file to the target output directory
        target_mp3_path = Path(output_dir) / original_mp3_path.name
        shutil.move(str(original_mp3_path), str(target_mp3_path)) # Use shutil.move
        print(f"Moved {original_mp3_path.name} to {target_mp3_path}")

        # Return the path to the final MP3 and the temp dir path for cleanup later
        return target_mp3_path, temp_download_subdir # Modified return value

    except subprocess.CalledProcessError as e:
        error_message = f"yt-dlp failed (Code: {e.returncode}). Check URL? Stderr: {e.stderr[:200]}..."
        schedule_gui_update(app, task_id, "Status", "Error: Download failed")
        print(f"Error during download: {e}\nStderr:\n{e.stderr}")
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None # Modified return value
    except FileNotFoundError as e:
        # This specifically catches the FileNotFoundError raised if original_mp3_path doesn't exist
        error_message = "MP3 file not found post-download."
        schedule_gui_update(app, task_id, "Status", "Error: " + error_message)
        print(f"Error: {e}")
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None # Modified return value
    except Exception as e:
        error_message = f"An unexpected error occurred during download: {e}"
        schedule_gui_update(app, task_id, "Status", "Error: Download failed")
        print(error_message)
        # Clean up temp dir on error
        try:
            if temp_download_subdir.exists():
                shutil.rmtree(temp_download_subdir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_download_subdir}: {cleanup_error}")
        return None, None # Modified return value

# --- Reverted crop_thumbnail logic ---
def crop_thumbnail(task_id, mp3_file, status_callback, app):
    """Extracts, crops to square, and re-embeds thumbnail using ffmpeg."""
    schedule_gui_update(app, task_id, "Status", "Processing...")
    temp_dir = mp3_file.parent / f"_thumb_proc_{mp3_file.stem}_{os.urandom(4).hex()}"
    temp_dir.mkdir(exist_ok=True)

    temp_image_name = temp_dir / "original_thumb.jpg"
    cropped_image_name = temp_dir / "cropped_thumb.jpg"
    final_track_name = temp_dir / mp3_file.name

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        # 1. Extract Thumbnail
        # schedule_gui_update(app, task_id, "Status", "Extracting thumbnail...")
        cmd_extract = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3_file), str(temp_image_name)]
        result_extract = subprocess.run(cmd_extract, check=False, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags) # check=False

        # Check common ffmpeg message for missing art
        if result_extract.returncode != 0:
            if "error retrieving cover art" in result_extract.stderr.lower() or "attached picture extraction failed" in result_extract.stderr.lower():
                schedule_gui_update(app, task_id, "Status", "No thumbnail found")
                print(f"No thumbnail found in {mp3_file.name}. Skipping crop.")
                return True # Not an error, just no thumbnail to crop
            else:
                schedule_gui_update(app, task_id, "Status", "Error: Extract failed")
                print(f"ffmpeg error extracting thumbnail from {mp3_file.name}:\n{result_extract.stderr}")
                return False # Extraction failed

        if not temp_image_name.exists():
            schedule_gui_update(app, task_id, "Status", "No thumbnail found") # Treat as if not found
            print(f"Thumbnail file {temp_image_name} not found after extraction attempt for {mp3_file.name}. Skipping crop.")
            return True # Not an error, just no thumbnail to crop

        # 2. Crop Thumbnail
        # schedule_gui_update(app, task_id, "Status", "Cropping thumbnail...")
        cmd_crop = [str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y", "-i", str(temp_image_name), "-vf", "crop=ih:ih", str(cropped_image_name)]
        result_crop = subprocess.run(cmd_crop, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
        # print(f"ffmpeg crop stdout: {result_crop.stdout}")
        # print(f"ffmpeg crop stderr: {result_crop.stderr}")

        if not cropped_image_name.exists():
            raise FileNotFoundError("Cropped image file not found after ffmpeg crop operation.")

        # 3. Re-embed Cropped Thumbnail
        # schedule_gui_update(app, task_id, "Status", "Re-embedding...")
        cmd_embed = [
            str(FFMPEG_PATH), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(mp3_file), # Input MP3
            "-i", str(cropped_image_name), # Input Cropped JPG
            "-map_metadata", "0",
            "-map_metadata:s:1", "0:s:1", # Map image metadata
            "-map", "0:a", # Map audio stream
            "-map", "1",   # Map new image stream
            "-acodec", "copy",
            str(final_track_name), # Output MP3 path
            '-y' # Overwrite output without asking
        ]

        # Inner try block for the embedding subprocess
        try:
            result_embed = subprocess.run(cmd_embed, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', creationflags=creationflags)
            # print(f"ffmpeg embed stdout: {result_embed.stdout}")
            # print(f"ffmpeg embed stderr: {result_embed.stderr}")

            if not final_track_name.exists():
                raise FileNotFoundError("Final MP3 with re-embedded thumbnail not found.")

            # 4. Replace original MP3 with the new one
            # schedule_gui_update(app, task_id, "Status", "Finalizing...")
            os.replace(str(final_track_name), str(mp3_file)) # Use os.replace for atomic move/replace
            print(f"Successfully processed thumbnail for: {mp3_file.name}")
            return True # Indicate success

        # Exceptions specifically for the embedding step
        except subprocess.CalledProcessError as e:
            error_message = f"ffmpeg error during embed (Code: {e.returncode}) for {mp3_file.name}. Stderr: {e.stderr[:200]}..."
            schedule_gui_update(app, task_id, "Status", "Error: Embed failed")
            print(f"{error_message}\nFull stderr:\n{e.stderr}")
            return False # Indicate failure
        except FileNotFoundError as e:
            # This specifically catches the FileNotFoundError raised if final_track_name doesn't exist
            error_message = f"File not found after embedding: {e}"
            schedule_gui_update(app, task_id, "Status", "Error: Embed File Missing")
            print(error_message)
            return False # Indicate failure

    # Outer except blocks handle errors from extract/crop steps, or unexpected errors
    except subprocess.CalledProcessError as e:
        error_message = f"ffmpeg error (Code: {e.returncode}) processing {mp3_file.name}. Stderr: {e.stderr[:200]}..."
        schedule_gui_update(app, task_id, "Status", "Error: Crop failed")
        print(f"{error_message}\nFull stderr:\n{e.stderr}")
        return False # Indicate failure
    except FileNotFoundError as e:
        error_message = f"File not found during thumbnail processing: {e}"
        schedule_gui_update(app, task_id, "Status", "Error: Crop File Missing")
        print(error_message)
        return False # Indicate failure
    except Exception as e:
        error_message = f"Unexpected error processing {mp3_file.name}: {e}"
        schedule_gui_update(app, task_id, "Status", "Error: Crop failed")
        print(error_message)
        import traceback
        traceback.print_exc() # Print full traceback for unexpected errors
        return False # Indicate failure
    finally:
        # Clean up the temporary directory used for cropping
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                # print(f"Cleaned up thumbnail processing temp dir: {temp_dir}")
        except Exception as e:
            print(f"Error cleaning up temp directory {temp_dir}: {e}")

# --- Reverted process_task logic ---
def process_task(task_id, url, output_path, app):
    """Wrapper function to run download and crop for a single task."""
    print(f"Worker {task_id}: Starting processing for {url} -> {output_path}")
    app.active_workers += 1
    mp3_path, temp_dir = None, None # Keep track of download result and temp download dir

    try:
        # Call the reverted download_audio (now expects string path)
        mp3_path, temp_dir = download_audio(task_id, url, output_path, schedule_gui_update, app)

        if mp3_path: # If download succeeded (mp3_path is the final Path object)
            # schedule_gui_update(app, task_id, "Status", "Processing thumbnail...")
            # Call reverted crop_thumbnail
            crop_result = crop_thumbnail(task_id, mp3_path, schedule_gui_update, app)
            if crop_result:
                # Crop succeeded or was skipped (no thumbnail)
                schedule_gui_update(app, task_id, "Status", "Completed")
            else:
                # Crop failed, but download was okay
                schedule_gui_update(app, task_id, "Status", "Error: Crop failed")
        # else: Download failed, status already set by download_audio

        print(f"Worker {task_id}: Task finished for {url}")

    except Exception as e:
        print(f"Error in worker thread for task {task_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            # Attempt to update GUI with unexpected error status
            schedule_gui_update(app, task_id, "Status", "Error: Unexpected Worker")
        except Exception as gui_e:
            print(f"Error updating GUI from worker exception handler: {gui_e}")
    finally:
        # Clean up the temporary *download* directory if it exists
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up download temp directory: {temp_dir}")
            except Exception as cleanup_error:
                print(f"Error cleaning up download temp directory {temp_dir}: {cleanup_error}")

        app.active_workers -= 1
        print(f"Worker {task_id}: Worker finished. Active workers: {app.active_workers}")

# --- Main Application Class --- (UI setup remains the same)
class EasyMP3App:
    def __init__(self, root):
        self.root = root
        self.root.title("EasyMP3")
        # self.root.geometry("600x500") # Let ttk determine size

        # Set window icon using the correctly determined ICON_PATH
        try:
            if ICON_PATH.is_file():
                self.root.iconbitmap(default=ICON_PATH)
                print(f"Attempting to load icon from: {ICON_PATH}")
            else:
                 print(f"Warning: Icon file not found at {ICON_PATH}")
        except tk.TclError as e:
            print(f"Warning: Could not set window icon ({ICON_PATH}): {e}")
        except Exception as e:
            print(f"Warning: An unexpected error occurred setting icon: {e}")

        # Apply the theme
        sv_ttk.set_theme("dark") # Options: "light", "dark"

        # --- Variables ---
        self.output_dir = tk.StringVar(value=str(get_base_path()))
        self.task_queue = queue.Queue()
        self.task_list = {}  # Stores task details {task_id: {url, status, filename}}
        self.active_workers = 0
        self.worker_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

        # --- GUI Setup ---
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid weights for responsiveness
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1) # Give weight to the row with Treeview

        # --- Top Controls Frame ---
        self.controls_frame = ttk.Frame(self.main_frame)
        self.controls_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.controls_frame.columnconfigure(1, weight=1) # Allow output path label/entry to expand

        # Output Folder Selection
        ttk.Label(self.controls_frame, text="Output Folder:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.output_dir_var = tk.StringVar(value=str(Path.cwd())) # Store as string
        # Change Entry to Label
        self.output_dir_label = ttk.Label(self.controls_frame, textvariable=self.output_dir_var, relief="sunken", padding=(5, 2))
        self.output_dir_label.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        browse_button = ttk.Button(self.controls_frame, text="Browse...", command=self.browse_output_dir)
        browse_button.grid(row=0, column=2, sticky="e")

        # --- Task List (Treeview) ---
        self.tree_frame = ttk.Frame(self.main_frame)
        self.tree_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        self.tree_frame.rowconfigure(0, weight=1)
        self.tree_frame.columnconfigure(0, weight=1)

        self.task_tree = ttk.Treeview(self.tree_frame, columns=("URL", "Filename", "Status"), show="headings")
        self.task_tree.heading("URL", text="URL")
        self.task_tree.heading("Filename", text="Filename")
        self.task_tree.heading("Status", text="Status")

        # Set column widths (adjust as needed)
        self.task_tree.column("URL", width=300, stretch=tk.YES)
        self.task_tree.column("Filename", width=150, anchor="w")
        self.task_tree.column("Status", width=100, anchor="center")

        # Scrollbar for Treeview
        self.scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=self.scrollbar.set)

        self.task_tree.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # --- Bottom Buttons Frame ---
        self.buttons_frame = ttk.Frame(self.main_frame)
        self.buttons_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.buttons_frame.columnconfigure(0, weight=1) # Push buttons to sides
        self.buttons_frame.columnconfigure(1, weight=1)

        # Download from Clipboard Button
        self.clipboard_button = ttk.Button(self.buttons_frame, text="Download from Clipboard", command=self.download_from_clipboard)
        self.clipboard_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        # Clear Completed Button
        self.clear_button = ttk.Button(self.buttons_frame, text="Clear Completed", command=self.clear_completed_tasks)
        self.clear_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        # --- Start Task Manager Thread ---
        self.manager_thread = threading.Thread(target=self.task_manager, daemon=True)
        self.manager_thread.start()

        # --- Handle Window Closing ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def browse_output_dir(self):
        directory = filedialog.askdirectory()
        if directory: # If a directory was selected
            self.output_dir_var.set(directory) # Update the label's variable
            print(f"Output directory set to: {directory}")

    def is_valid_youtube_url(self, url):
        # Simple regex for YouTube URLs (can be improved)
        youtube_regex = r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})"
        return re.match(youtube_regex, url)

    def download_from_clipboard(self):
        """Fetches URL from clipboard, validates, and adds task."""
        try:
            clipboard_content = pyperclip.paste()
            if self.is_valid_youtube_url(clipboard_content):
                self.add_task(clipboard_content)
            else:
                messagebox.showerror("Invalid URL", "The content in your clipboard is not a valid YouTube URL.")
        except Exception as e:
            # Might happen if clipboard access is restricted or content is unusual
            messagebox.showerror("Clipboard Error", f"Could not read or validate clipboard content: {e}")

    def add_task(self, url):
        output_path = self.output_dir_var.get()
        if not output_path:
            messagebox.showerror("Error", "Please select an output folder first.")
            return

        task_id = str(uuid.uuid4()) # Unique ID for the task
        # Add placeholder to Treeview
        item_id = self.task_tree.insert("", tk.END, values=(url, "-", "Queued"))
        self.task_list[item_id] = {"url": url, "status": "Queued", "filename": "-", "real_task_id": task_id}
        self.task_queue.put((item_id, url, output_path)) # Put Treeview item ID in queue
        # print(f"Task added to queue: {item_id} - {url[:30]}...")

    def update_task_display(self, item_id, column, value):
        """Safely update the Treeview from any thread."""
        try:
            if self.task_tree.exists(item_id):
                current_values = list(self.task_tree.item(item_id, 'values'))
                # Use .get() for safer column index lookup
                col_map = {"URL": 0, "Filename": 1, "Status": 2}
                col_index = col_map.get(column)

                if col_index is not None: # Check if column name was valid
                    current_values[col_index] = value
                    self.task_tree.item(item_id, values=tuple(current_values))

                    # Update internal task list as well
                    if item_id in self.task_list:
                        internal_col_name = column.lower() # Map Treeview column name to internal dict key
                        self.task_list[item_id][internal_col_name] = value

                    # Decrement active workers ONLY if task status update indicates finished/errored
                    # AND the update was successfully applied (i.e., no exception occurred before this)
                    if column == "Status" and value in ["Completed", "Error: Download failed", "Error: Crop failed", "Error: Embed failed", "Error: Unexpected", "Error: File Missing", "Error: Extract failed", "Error: Embed File Missing", "Error: Crop File Missing", "Error: Unexpected Worker"]:
                        with self.worker_lock:
                            # Ensure worker count doesn't go below zero
                            if self.active_workers > 0:
                                self.active_workers -= 1
                                # print(f"Worker finished/errored ({value}). Active workers: {self.active_workers}")
                else:
                    print(f"!!! Warning: Invalid column name '{column}' passed to update_task_display for item {item_id}")

        except tk.TclError as e:
            # This specifically catches errors if the item ID doesn't exist anymore when tk tries to access it
            print(f"!!! TclError updating Treeview for {item_id} (likely item removed): {e}")
        except Exception as e:
            print(f"!!! Error updating Treeview for {item_id}, column '{column}': {e}")
            import traceback
            traceback.print_exc() # Print full traceback for unexpected errors

    def clear_completed_tasks(self):
        """Removes tasks marked as 'Completed' or 'Error' from the Treeview."""
        items_to_delete = []
        for item_id in self.task_tree.get_children():
            if item_id in self.task_list:
                status = self.task_list[item_id].get("status", "")
                if status in ["Completed", "Error"]:
                    items_to_delete.append(item_id)

        if not items_to_delete:
            messagebox.showinfo("Clear Completed", "No completed or errored tasks to clear.")
            return

        for item_id in items_to_delete:
            if self.task_tree.exists(item_id):
                self.task_tree.delete(item_id)
            if item_id in self.task_list:
                del self.task_list[item_id]

        messagebox.showinfo("Clear Completed", f"Removed {len(items_to_delete)} finished tasks.")

    def task_manager(self):
        """Monitors the queue and assigns tasks to worker threads."""
        print("Task manager thread started.")
        while True:
            try:  # Add try-except for robustness
                # Check if we can start a new worker
                can_start_new = False
                with self.worker_lock:
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
                    with self.worker_lock:
                        self.active_workers += 1

                    item_id, url, output_path = task_info

                    print(f"Manager: Submitting task {item_id} ({url}). Active: {self.active_workers}/{MAX_WORKERS}")
                    # Update Treeview status to "Processing..." using Capitalized "Status"
                    schedule_gui_update(self, item_id, "Status", "Processing...") # Fixed capitalization

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
        close_app = True
        if self.active_workers > 0:
            # Ask for confirmation only if tasks are running
            if not messagebox.askyesno("Confirm Exit", f"{self.active_workers} tasks are still running. Exit anyway? (Ongoing tasks will complete in background)"):
                close_app = False # Don't close yet

        if close_app:
            print("Proceeding with shutdown.")
            # Disable buttons to prevent adding more tasks during shutdown
            try:
                self.clipboard_button.config(state="disabled")
                self.clear_button.config(state="disabled")
            except tk.TclError: # Window might already be closing
                pass

            # No blocking info message here
            self.executor.shutdown(wait=True)  # Wait for existing tasks to complete
            print("Executor shutdown complete.")
            self.root.destroy()
        else:
            print("Shutdown cancelled by user.")

if __name__ == "__main__":
    # Dependencies checked by check_dependencies() called earlier if needed
    # Recommend installing dependencies if running directly:
    # pip install pyperclip sv_ttk

    if not check_dependencies():
        sys.exit(1)  # Exit if yt-dlp/ffmpeg dependencies are missing

    root = tk.Tk()
    app = EasyMP3App(root)
    root.mainloop()
