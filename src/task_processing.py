import logging

from download_engine import run_download
from utils import truncate_display_value

LOGGER = logging.getLogger(__name__)


def schedule_gui_update(app, item_id, column, value):
    display_value = value
    if column in {"URL", "Filename"}:
        display_value = truncate_display_value(value)
    app.root.after_idle(app.update_task_display, item_id, column, display_value)


def process_task(task_id, url, output_path, app):
    """Run download and thumbnail processing for a single task."""
    try:
        result = run_download(task_id, url, output_path, app.schedule_task_update)
        if not result.success:
            LOGGER.error("Worker %s failed: %s", task_id, result.error)
    finally:
        app.release_worker_slot()
