import queue
import threading
import time
import tkinter as tk
import uuid
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, ttk

import pyperclip
import sv_ttk

from config import DEFAULT_OUTPUT_DIR, ICON_PATH, MAX_WORKERS, TERMINAL_TASK_STATUSES, YTDLP_PATH
from task_processing import process_task, schedule_gui_update
from utils import parse_youtube_url
from ytdlp_wrapper import inspect_playlist_metadata


def show_choice_dialog(parent, title, message, choices):
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)

    selection = {"value": None}

    def choose(value):
        selection["value"] = value
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    container = ttk.Frame(dialog, padding=16)
    container.pack(fill=tk.BOTH, expand=True)

    ttk.Label(container, text=message, justify=tk.LEFT, wraplength=360).pack(fill=tk.X)

    button_frame = ttk.Frame(container)
    button_frame.pack(fill=tk.X, pady=(16, 0))

    for index, (label, value) in enumerate(choices):
        button = ttk.Button(button_frame, text=label, command=lambda current=value: choose(current))
        button.grid(row=0, column=index, padx=(0 if index == 0 else 8, 0), sticky="ew")
        button_frame.columnconfigure(index, weight=1)
        if index == 0:
            button.focus_set()

    dialog.update_idletasks()
    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    dialog_width = dialog.winfo_width()
    dialog_height = dialog.winfo_height()
    position_x = parent_x + max((parent_width - dialog_width) // 2, 0)
    position_y = parent_y + max((parent_height - dialog_height) // 2, 0)
    dialog.geometry(f"+{position_x}+{position_y}")

    dialog.grab_set()
    parent.wait_window(dialog)
    return selection["value"]


class EasyMP3App:
    def __init__(self, root):
        self.root = root
        self.root.title("EasyMP3")

        try:
            if ICON_PATH.is_file():
                self.root.iconbitmap(default=ICON_PATH)
                print(f"Attempting to load icon from: {ICON_PATH}")
            else:
                print(f"Warning: Icon file not found at {ICON_PATH}")
        except tk.TclError as error:
            print(f"Warning: Could not set window icon ({ICON_PATH}): {error}")
        except Exception as error:
            print(f"Warning: An unexpected error occurred setting icon: {error}")

        sv_ttk.set_theme("dark")

        self.task_queue = queue.Queue()
        self.task_list = {}
        self.active_workers = 0
        self.playlist_inspection_active = False
        self.worker_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.default_clipboard_button_text = "Download from Clipboard"

        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        self.controls_frame = ttk.Frame(self.main_frame)
        self.controls_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.controls_frame.columnconfigure(1, weight=1)

        ttk.Label(self.controls_frame, text="Output Folder:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.output_dir_label = ttk.Label(
            self.controls_frame,
            textvariable=self.output_dir_var,
            relief="sunken",
            padding=(5, 2),
        )
        self.output_dir_label.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        browse_button = ttk.Button(self.controls_frame, text="Browse...", command=self.browse_output_dir)
        browse_button.grid(row=0, column=2, sticky="e")

        self.tree_frame = ttk.Frame(self.main_frame)
        self.tree_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(0, 10))
        self.tree_frame.rowconfigure(0, weight=1)
        self.tree_frame.columnconfigure(0, weight=1)

        self.task_tree = ttk.Treeview(self.tree_frame, columns=("URL", "Filename", "Status"), show="headings")
        self.task_tree.heading("URL", text="URL")
        self.task_tree.heading("Filename", text="Filename")
        self.task_tree.heading("Status", text="Status")
        self.task_tree.column("URL", width=300, stretch=tk.YES)
        self.task_tree.column("Filename", width=150, anchor="w")
        self.task_tree.column("Status", width=100, anchor="center")

        self.scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=self.scrollbar.set)

        self.task_tree.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.buttons_frame = ttk.Frame(self.main_frame)
        self.buttons_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.buttons_frame.columnconfigure(0, weight=1)
        self.buttons_frame.columnconfigure(1, weight=1)

        self.clipboard_button = ttk.Button(
            self.buttons_frame,
            text="Download from Clipboard",
            command=self.download_from_clipboard,
        )
        self.clipboard_button.grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.clear_button = ttk.Button(self.buttons_frame, text="Clear Completed", command=self.clear_completed_tasks)
        self.clear_button.grid(row=0, column=1, padx=5, pady=5, sticky="e")

        self.manager_thread = threading.Thread(target=self.task_manager, daemon=True)
        self.manager_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def browse_output_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_dir_var.set(directory)
            print(f"Output directory set to: {directory}")

    def download_from_clipboard(self):
        """Fetch URL from the clipboard, validate it, and enqueue a task."""
        try:
            clipboard_content = pyperclip.paste()
            parsed_url = parse_youtube_url(clipboard_content)
            if not parsed_url:
                self._show_error_dialog("Invalid URL", "The content in your clipboard is not a valid YouTube URL.")
                return

            if parsed_url.kind == "video":
                self.add_task(parsed_url.video_url, video_id=parsed_url.video_id)
                return

            if parsed_url.kind == "video_in_playlist":
                self._handle_video_in_playlist_url(parsed_url)
                return

            self.start_playlist_inspection(parsed_url.playlist_url)
        except Exception as error:
            self._show_error_dialog("Clipboard Error", f"Could not read or validate clipboard content: {error}")

    def add_task(self, url, video_id=None, title=None, output_path=None):
        resolved_output_path = output_path or self.get_output_path()
        if not resolved_output_path:
            return None

        return self._enqueue_task(url, resolved_output_path, video_id=video_id, title=title)

    def add_tasks(self, tasks, output_path, on_complete=None, batch_size=25):
        if not tasks:
            if on_complete:
                on_complete()
            return

        def add_batch(start_index):
            end_index = min(start_index + batch_size, len(tasks))
            for task in tasks[start_index:end_index]:
                self._enqueue_task(
                    task["url"],
                    output_path,
                    video_id=task.get("video_id"),
                    title=task.get("title"),
                )

            if end_index < len(tasks):
                self.root.after_idle(add_batch, end_index)
                return

            if on_complete:
                on_complete()

        add_batch(0)

    def get_output_path(self):
        output_path = self.output_dir_var.get().strip()
        if not output_path:
            self._show_error_dialog("Error", "Please select an output folder first.")
            return None
        return output_path

    def start_playlist_inspection(self, playlist_url):
        if self.playlist_inspection_active:
            self._show_info_dialog(
                "Playlist Inspection In Progress",
                "Please wait for the current playlist inspection to finish before starting another one.",
            )
            return

        output_path = self.get_output_path()
        if not output_path:
            return

        self.set_playlist_inspection_state(True)
        worker = threading.Thread(
            target=self._inspect_playlist_worker,
            args=(playlist_url, output_path),
            daemon=True,
        )
        worker.start()

    def set_playlist_inspection_state(self, is_active):
        self.playlist_inspection_active = is_active
        button_state = "disabled" if is_active else "normal"
        button_text = "Inspecting Playlist..." if is_active else self.default_clipboard_button_text

        try:
            self.clipboard_button.config(state=button_state, text=button_text)
        except tk.TclError:
            pass

    def _inspect_playlist_worker(self, playlist_url, output_path):
        try:
            inspection_result = inspect_playlist_metadata(playlist_url, YTDLP_PATH)
            self.root.after(
                0,
                self._handle_playlist_inspection_success,
                inspection_result,
                output_path,
            )
        except Exception as error:
            self.root.after(0, self._handle_playlist_inspection_error, str(error))

    def _handle_playlist_inspection_success(self, inspection_result, output_path):
        self.set_playlist_inspection_state(False)

        existing_video_ids = self.get_known_video_ids()
        queued_tasks = []
        skipped_duplicates = 0
        seen_in_batch = set()

        for entry in inspection_result.entries:
            if entry.video_id in existing_video_ids or entry.video_id in seen_in_batch:
                skipped_duplicates += 1
                continue

            seen_in_batch.add(entry.video_id)
            queued_tasks.append({"url": entry.url, "video_id": entry.video_id, "title": entry.title})

        if not queued_tasks:
            self._show_info_dialog(
                "Nothing To Queue",
                self._build_playlist_empty_message(inspection_result, skipped_duplicates),
            )
            return

        choice = self._show_choice_dialog(
            "Queue Playlist",
            self._build_playlist_confirmation_message(inspection_result, len(queued_tasks), skipped_duplicates),
            [
                ("Yes", "playlist"),
                ("No", None),
            ],
        )
        if choice != "playlist":
            return

        self.add_tasks(queued_tasks, output_path)

    def _handle_playlist_inspection_error(self, error_message):
        self.set_playlist_inspection_state(False)
        self._show_error_dialog("Playlist Error", f"Could not inspect the playlist:\n\n{error_message}")

    def _handle_video_in_playlist_url(self, parsed_url):
        choice = self._show_choice_dialog(
            "Playlist URL Detected",
            "Playlist URL detected, what do you want to download?",
            [
                ("All songs in playlist", "playlist"),
                ("Just this song", "song"),
            ],
        )

        if choice == "song":
            self.add_task(parsed_url.video_url, video_id=parsed_url.video_id)
            return

        if choice == "playlist":
            self.start_playlist_inspection(parsed_url.playlist_url)

    def get_known_video_ids(self):
        known_video_ids = set()
        for item_id in self.task_tree.get_children():
            task = self.task_list.get(item_id)
            if not task:
                continue

            video_id = task.get("video_id")
            if not video_id:
                continue

            known_video_ids.add(video_id)

        return known_video_ids

    def _enqueue_task(self, url, output_path, video_id=None, title=None):
        task_id = str(uuid.uuid4())
        filename = title or "-"
        item_id = self.task_tree.insert("", tk.END, values=(url, filename, "Queued"))
        self.task_list[item_id] = {
            "url": url,
            "status": "Queued",
            "filename": filename,
            "real_task_id": task_id,
            "video_id": video_id,
            "title": title,
        }
        self.task_queue.put((item_id, url, output_path))
        return item_id

    def _build_playlist_confirmation_message(self, inspection_result, queued_count, skipped_duplicates):
        total_count = len(inspection_result.entries) + inspection_result.unavailable_count
        total_label = self._pluralize_song(total_count)
        queued_label = self._pluralize_song(queued_count)
        return (
            f"Playlist name: {inspection_result.title}\n\n"
            f"Found {total_count} {total_label} in playlist\n"
            f"Unavailable or private: {inspection_result.unavailable_count}\n"
            f"Skipping duplicates: {skipped_duplicates}\n"
            f"Download {queued_count} {queued_label}?"
        )

    def _build_playlist_empty_message(self, inspection_result, skipped_duplicates):
        total_count = len(inspection_result.entries) + inspection_result.unavailable_count
        total_label = self._pluralize_song(total_count)
        return (
            f"Playlist name: {inspection_result.title}\n\n"
            f"Found {total_count} {total_label} in playlist\n"
            f"Unavailable or private: {inspection_result.unavailable_count}\n"
            f"Skipping duplicates: {skipped_duplicates}\n"
            "No new downloadable tracks were found.\n"
        )

    def _pluralize_song(self, count):
        return "song" if count == 1 else "songs"

    def _show_info_dialog(self, title, message):
        self._show_choice_dialog(title, message, [("OK", True)])

    def _show_error_dialog(self, title, message):
        self._show_choice_dialog(title, message, [("OK", True)])

    def _show_confirm_dialog(self, title, message, confirm_label="Yes", cancel_label="No"):
        choice = self._show_choice_dialog(
            title,
            message,
            [
                (confirm_label, True),
                (cancel_label, False),
            ],
        )
        return bool(choice)

    def _show_choice_dialog(self, title, message, choices):
        return show_choice_dialog(self.root, title, message, choices)

    def schedule_task_update(self, item_id, column, value):
        schedule_gui_update(self, item_id, column, value)

    def update_task_display(self, item_id, column, value):
        """Safely update the Treeview from any thread."""
        try:
            if not self.task_tree.exists(item_id):
                return

            current_values = list(self.task_tree.item(item_id, "values"))
            col_map = {"URL": 0, "Filename": 1, "Status": 2}
            col_index = col_map.get(column)

            if col_index is None:
                print(f"!!! Warning: Invalid column name '{column}' passed to update_task_display for item {item_id}")
                return

            current_values[col_index] = value
            self.task_tree.item(item_id, values=tuple(current_values))

            if item_id in self.task_list:
                self.task_list[item_id][column.lower()] = value

        except tk.TclError as error:
            print(f"!!! TclError updating Treeview for {item_id} (likely item removed): {error}")
        except Exception as error:
            print(f"!!! Error updating Treeview for {item_id}, column '{column}': {error}")
            import traceback

            traceback.print_exc()

    def clear_completed_tasks(self):
        """Remove finished tasks from the Treeview."""
        items_to_delete = []
        for item_id in self.task_tree.get_children():
            if item_id not in self.task_list:
                continue

            status = self.task_list[item_id].get("status", "")
            if status in TERMINAL_TASK_STATUSES:
                items_to_delete.append(item_id)

        if not items_to_delete:
            self._show_info_dialog("Clear Completed", "No completed or errored tasks to clear.")
            return

        for item_id in items_to_delete:
            if self.task_tree.exists(item_id):
                self.task_tree.delete(item_id)
            if item_id in self.task_list:
                del self.task_list[item_id]

    def task_manager(self):
        """Monitor the queue and assign tasks to worker threads."""
        print("Task manager thread started.")
        while True:
            try:
                if not self.can_start_worker():
                    time.sleep(0.5)
                    continue

                try:
                    item_id, url, output_path = self.task_queue.get_nowait()
                except queue.Empty:
                    time.sleep(0.5)
                    continue

                self.reserve_worker_slot()
                print(f"Manager: Submitting task {item_id} ({url}). Active: {self.active_workers}/{MAX_WORKERS}")
                self.schedule_task_update(item_id, "Status", "Processing...")
                self.executor.submit(process_task, item_id, url, output_path, self)

            except Exception as error:
                print(f"!!! Error in Task Manager loop: {error}")
                import traceback

                traceback.print_exc()
                time.sleep(5)

    def can_start_worker(self):
        with self.worker_lock:
            return self.active_workers < MAX_WORKERS

    def reserve_worker_slot(self):
        with self.worker_lock:
            self.active_workers += 1

    def release_worker_slot(self):
        with self.worker_lock:
            if self.active_workers > 0:
                self.active_workers -= 1

    def on_closing(self):
        """Handle window closing: shutdown executor and exit."""
        print("Shutdown initiated.")
        close_app = True
        pending_operations = []
        if self.playlist_inspection_active:
            pending_operations.append("a playlist inspection")
        if self.active_workers > 0:
            pending_operations.append(f"{self.active_workers} tasks")

        if pending_operations:
            if not self._show_confirm_dialog(
                "Confirm Exit",
                " and ".join(pending_operations)
                + " are still in progress. Exit anyway? (Ongoing downloads will complete in background)",
                confirm_label="Exit",
                cancel_label="Stay",
            ):
                close_app = False

        if close_app:
            print("Proceeding with shutdown.")
            try:
                self.clipboard_button.config(state="disabled")
                self.clear_button.config(state="disabled")
            except tk.TclError:
                pass

            self.executor.shutdown(wait=True)
            print("Executor shutdown complete.")
            self.root.destroy()
        else:
            print("Shutdown cancelled by user.")
