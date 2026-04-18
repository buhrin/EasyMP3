import os
import shutil
import subprocess

from utils import get_subprocess_creationflags


def crop_thumbnail(task_id, mp3_file, ffmpeg_path, update_task):
    """Extract, crop, and re-embed the MP3 thumbnail."""
    update_task(task_id, "Status", "Processing...")
    temp_dir = mp3_file.parent / f"_thumb_proc_{mp3_file.stem}_{os.urandom(4).hex()}"
    temp_dir.mkdir(exist_ok=True)

    temp_image_name = temp_dir / "original_thumb.jpg"
    cropped_image_name = temp_dir / "cropped_thumb.jpg"
    final_track_name = temp_dir / mp3_file.name

    try:
        result_extract = subprocess.run(
            [
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3_file),
                str(temp_image_name),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=get_subprocess_creationflags(),
        )

        if result_extract.returncode != 0:
            if _is_missing_cover_art_error(result_extract.stderr):
                update_task(task_id, "Status", "No thumbnail found")
                print(f"No thumbnail found in {mp3_file.name}. Skipping crop.")
                return True
            update_task(task_id, "Status", "Error: Extract failed")
            print(f"ffmpeg error extracting thumbnail from {mp3_file.name}:\n{result_extract.stderr}")
            return False

        if not temp_image_name.exists():
            update_task(task_id, "Status", "No thumbnail found")
            print(f"Thumbnail file {temp_image_name} not found after extraction attempt for {mp3_file.name}.")
            return True

        subprocess.run(
            [
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(temp_image_name),
                "-vf",
                "crop=ih:ih",
                str(cropped_image_name),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=get_subprocess_creationflags(),
        )

        if not cropped_image_name.exists():
            raise FileNotFoundError("Cropped image file not found after ffmpeg crop operation.")

        subprocess.run(
            [
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(mp3_file),
                "-i",
                str(cropped_image_name),
                "-map_metadata",
                "0",
                "-map_metadata:s:1",
                "0:s:1",
                "-map",
                "0:a",
                "-map",
                "1",
                "-acodec",
                "copy",
                str(final_track_name),
                "-y",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=get_subprocess_creationflags(),
        )

        if not final_track_name.exists():
            raise FileNotFoundError("Final MP3 with re-embedded thumbnail not found.")

        os.replace(str(final_track_name), str(mp3_file))
        print(f"Successfully processed thumbnail for: {mp3_file.name}")
        return True

    except subprocess.CalledProcessError as error:
        update_task(task_id, "Status", "Error: Crop failed")
        print(f"ffmpeg error (Code: {error.returncode}) processing {mp3_file.name}.\nFull stderr:\n{error.stderr}")
        return False
    except FileNotFoundError as error:
        update_task(task_id, "Status", "Error: Crop File Missing")
        print(f"File not found during thumbnail processing: {error}")
        return False
    except Exception as error:
        update_task(task_id, "Status", "Error: Crop failed")
        print(f"Unexpected error processing {mp3_file.name}: {error}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        except Exception as cleanup_error:
            print(f"Error cleaning up temp directory {temp_dir}: {cleanup_error}")


def _is_missing_cover_art_error(stderr):
    error_text = stderr.lower()
    return "error retrieving cover art" in error_text or "attached picture extraction failed" in error_text
