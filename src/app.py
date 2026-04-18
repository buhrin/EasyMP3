import queue
import threading
import time
import tkinter as tk
import uuid
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox, ttk

import pyperclip
import sv_ttk

from config import DEFAULT_OUTPUT_DIR, ICON_PATH, MAX_WORKERS, TERMINAL_TASK_STATUSES
from task_processing import process_task, schedule_gui_update
from utils import is_valid_youtube_url


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
        self.worker_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

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
            if is_valid_youtube_url(clipboard_content):
                self.add_task(clipboard_content)
            else:
                messagebox.showerror("Invalid URL", "The content in your clipboard is not a valid YouTube URL.")
        except Exception as error:
            messagebox.showerror("Clipboard Error", f"Could not read or validate clipboard content: {error}")

    def add_task(self, url):
        output_path = self.output_dir_var.get()
        if not output_path:
            messagebox.showerror("Error", "Please select an output folder first.")
            return

        task_id = str(uuid.uuid4())
        item_id = self.task_tree.insert("", tk.END, values=(url, "-", "Queued"))
        self.task_list[item_id] = {"url": url, "status": "Queued", "filename": "-", "real_task_id": task_id}
        self.task_queue.put((item_id, url, output_path))

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
            messagebox.showinfo("Clear Completed", "No completed or errored tasks to clear.")
            return

        for item_id in items_to_delete:
            if self.task_tree.exists(item_id):
                self.task_tree.delete(item_id)
            if item_id in self.task_list:
                del self.task_list[item_id]

        messagebox.showinfo("Clear Completed", f"Removed {len(items_to_delete)} finished tasks.")

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
        if self.active_workers > 0:
            if not messagebox.askyesno(
                "Confirm Exit",
                f"{self.active_workers} tasks are still running. Exit anyway? (Ongoing tasks will complete in background)",
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
