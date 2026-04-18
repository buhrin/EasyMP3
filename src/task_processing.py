import shutil

from config import FFMPEG_PATH, YTDLP_PATH
from ffmpeg_wrapper import crop_thumbnail
from utils import truncate_display_value
from ytdlp_wrapper import download_audio


def schedule_gui_update(app, item_id, column, value):
    display_value = value
    if column in {"URL", "Filename"}:
        display_value = truncate_display_value(value)
    app.root.after_idle(app.update_task_display, item_id, column, display_value)


def process_task(task_id, url, output_path, app):
    """Run download and thumbnail processing for a single task."""
    print(f"Worker {task_id}: Starting processing for {url} -> {output_path}")
    mp3_path = None
    temp_dir = None

    try:
        mp3_path, temp_dir = download_audio(task_id, url, output_path, YTDLP_PATH, app.schedule_task_update)

        if mp3_path:
            crop_result = crop_thumbnail(task_id, mp3_path, FFMPEG_PATH, app.schedule_task_update)
            if crop_result:
                schedule_gui_update(app, task_id, "Status", "Completed")

        print(f"Worker {task_id}: Task finished for {url}")

    except Exception as error:
        print(f"Error in worker thread for task {task_id}: {error}")
        import traceback

        traceback.print_exc()
        try:
            schedule_gui_update(app, task_id, "Status", "Error: Unexpected Worker")
        except Exception as gui_error:
            print(f"Error updating GUI from worker exception handler: {gui_error}")
    finally:
        if temp_dir and temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up download temp directory: {temp_dir}")
            except Exception as cleanup_error:
                print(f"Error cleaning up download temp directory {temp_dir}: {cleanup_error}")

        app.release_worker_slot()
        print(f"Worker {task_id}: Worker finished. Active workers: {app.active_workers}")
