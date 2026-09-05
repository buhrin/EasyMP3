import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import download_engine
import ffmpeg_wrapper
import task_processing
import ytdlp_wrapper


class DownloadEngineTests(unittest.TestCase):
    def test_success_processes_in_staging_and_publishes_atomically(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)

            def fake_download(task_id, url, output_dir, ytdlp_path, update_task, ffmpeg_path):
                self.assertEqual(ffmpeg_path, download_engine.FFMPEG_PATH)
                staged_file = Path(output_dir) / "Artist - Track.mp3"
                staged_file.write_bytes(b"downloaded")
                update_task(task_id, "Filename", staged_file.name)
                return staged_file, Path(output_dir) / "inner-temp"

            def fake_crop(task_id, mp3_path, ffmpeg_path, update_task):
                self.assertTrue(mp3_path.parent.name.startswith(".easymp3-job-"))
                mp3_path.write_bytes(b"processed")
                return True

            with (
                patch.object(download_engine, "download_audio", side_effect=fake_download),
                patch.object(download_engine, "crop_thumbnail", side_effect=fake_crop),
                patch.object(download_engine.os, "replace", wraps=os.replace) as replace,
            ):
                result = download_engine.run_download(
                    "job", "https://youtu.be/video", destination, lambda *update: updates.append(update)
                )

            self.assertTrue(result.success)
            self.assertEqual(result.output_path, destination / "Artist - Track.mp3")
            self.assertEqual(result.output_path.read_bytes(), b"processed")
            self.assertEqual(replace.call_count, 1)
            self.assertFalse(list(destination.glob(".easymp3-*")))

    def test_crop_failure_does_not_publish_partial_file(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)

            def fake_download(*args, **kwargs):
                staged_file = Path(args[2]) / "Track.mp3"
                staged_file.write_bytes(b"partial")
                return staged_file, Path(args[2]) / "inner-temp"

            with (
                patch.object(download_engine, "download_audio", side_effect=fake_download),
                patch.object(download_engine, "crop_thumbnail", return_value=False),
            ):
                result = download_engine.run_download(
                    "job", "https://youtu.be/video", destination, lambda *update: updates.append(update)
                )

            self.assertFalse(result.success)
            self.assertEqual(result.error, "Thumbnail processing failed")
            self.assertFalse((destination / "Track.mp3").exists())
            self.assertFalse(list(destination.glob(".easymp3-*")))

    def test_existing_staging_folders_are_not_touched(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            existing = destination / ".easymp3-another-live-process"
            existing.mkdir()
            marker = existing / "active"
            marker.write_text("keep")

            with patch.object(download_engine, "download_audio", side_effect=RuntimeError("broken")):
                download_engine.run_download("job", "https://youtu.be/video", destination, lambda *args: None)

            self.assertEqual(marker.read_text(), "keep")

    def test_unexpected_failure_is_returned_and_staging_is_cleaned(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            with patch.object(download_engine, "download_audio", side_effect=RuntimeError("broken")):
                result = download_engine.run_download(
                    "job", "https://youtu.be/video", destination, lambda *update: updates.append(update)
                )

            self.assertFalse(result.success)
            self.assertEqual(result.error, "broken")
            self.assertFalse(list(destination.glob(".easymp3-*")))

    def test_matching_filenames_are_serialized_and_locks_are_released(self):
        active_replaces = 0
        max_active_replaces = 0
        counter_lock = threading.Lock()
        original_replace = os.replace

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)

            def fake_download(task_id, url, output_dir, *args, **kwargs):
                staged = Path(output_dir) / "Same.mp3"
                staged.write_text(task_id)
                return staged, Path(output_dir) / "inner"

            def observed_replace(source, target):
                nonlocal active_replaces, max_active_replaces
                with counter_lock:
                    active_replaces += 1
                    max_active_replaces = max(max_active_replaces, active_replaces)
                try:
                    threading.Event().wait(0.02)
                    original_replace(source, target)
                finally:
                    with counter_lock:
                        active_replaces -= 1

            with (
                patch.object(download_engine, "download_audio", side_effect=fake_download),
                patch.object(download_engine, "crop_thumbnail", return_value=True),
                patch.object(download_engine.os, "replace", side_effect=observed_replace),
            ):
                threads = [
                    threading.Thread(
                        target=download_engine.run_download,
                        args=(f"job-{index}", "https://youtu.be/video", destination, lambda *args: None),
                    )
                    for index in range(2)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            self.assertEqual(max_active_replaces, 1)
            self.assertEqual(download_engine._target_locks, {})
            self.assertIn((destination / "Same.mp3").read_text(), {"job-0", "job-1"})


class YtDlpWrapperTests(unittest.TestCase):
    def test_download_passes_bundled_ffmpeg_directory(self):
        updates = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            ytdlp = output / "bin" / "yt-dlp.exe"
            ffmpeg = output / "bin" / "ffmpeg.exe"

            def fake_run(command, **kwargs):
                template = Path(command[command.index("--output") + 1])
                template.parent.mkdir(parents=True, exist_ok=True)
                (template.parent / "Artist - Track.mp3").write_bytes(b"mp3")
                return type("Result", (), {"stderr": ""})()

            with patch.object(ytdlp_wrapper.subprocess, "run", side_effect=fake_run) as run:
                result, _ = ytdlp_wrapper.download_audio(
                    "job",
                    "https://youtu.be/video",
                    output,
                    ytdlp,
                    lambda *update: updates.append(update),
                    ffmpeg_path=ffmpeg,
                )

            command = run.call_args.args[0]
            self.assertEqual(command[command.index("--ffmpeg-location") + 1], str(ffmpeg.parent))
            self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(result.name, "Artist - Track.mp3")

    def test_playlist_inspection_does_not_inherit_stdin(self):
        payload = '{"title":"List","id":"PL1","entries":[]}'
        completed = type("Result", (), {"stdout": payload})()
        with patch.object(ytdlp_wrapper.subprocess, "run", return_value=completed) as run:
            ytdlp_wrapper.inspect_playlist_metadata("https://youtube.com/playlist?list=PL1", Path("yt-dlp.exe"))

        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)


class FfmpegWrapperTests(unittest.TestCase):
    def test_all_thumbnail_commands_do_not_inherit_stdin(self):
        completed = type("Result", (), {"returncode": 0, "stderr": ""})()
        with tempfile.TemporaryDirectory() as directory:
            track = Path(directory) / "track.mp3"
            track.write_bytes(b"mp3")

            def fake_run(command, **kwargs):
                output = Path(command[-2] if command[-1] == "-y" else command[-1])
                output.write_bytes(b"result")
                return completed

            with patch.object(ffmpeg_wrapper.subprocess, "run", side_effect=fake_run) as run:
                result = ffmpeg_wrapper.crop_thumbnail("job", track, Path("ffmpeg.exe"), lambda *args: None)

        self.assertTrue(result)
        self.assertEqual(run.call_count, 3)
        for invocation in run.call_args_list:
            self.assertIs(invocation.kwargs["stdin"], subprocess.DEVNULL)


class BundledFfmpegTests(unittest.TestCase):
    @unittest.skipUnless(download_engine.FFMPEG_PATH.is_file(), "Bundled ffmpeg.exe is unavailable")
    def test_crop_preserves_metadata_and_embeds_square_cover(self):
        ffmpeg = str(download_engine.FFMPEG_PATH)
        quiet = {"check": True, "capture_output": True, "creationflags": 0}
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            audio = work / "audio.mp3"
            cover = work / "wide.jpg"
            track = work / "fixture.mp3"
            extracted = work / "result.jpg"

            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", "-q:a", "9", str(audio)],
                **quiet,
            )
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=400x200", "-frames:v", "1", str(cover)],
                **quiet,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(audio),
                    "-i",
                    str(cover),
                    "-map",
                    "0:a",
                    "-map",
                    "1:v",
                    "-c:a",
                    "copy",
                    "-c:v",
                    "mjpeg",
                    "-id3v2_version",
                    "3",
                    "-metadata",
                    "title=EngineFixture",
                    "-metadata:s:v",
                    "comment=Cover (front)",
                    str(track),
                ],
                **quiet,
            )

            updates = []
            self.assertTrue(
                ffmpeg_wrapper.crop_thumbnail("job", track, Path(ffmpeg), lambda *update: updates.append(update))
            )
            metadata = subprocess.run(
                [ffmpeg, "-i", str(track), "-f", "ffmetadata", "-"], text=True, encoding="utf-8", **quiet
            )
            subprocess.run([ffmpeg, "-y", "-i", str(track), str(extracted)], **quiet)
            image_info = subprocess.run(
                [ffmpeg, "-i", str(extracted), "-f", "null", "-"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                creationflags=0,
            )

            self.assertIn("title=EngineFixture", metadata.stdout)
            self.assertTrue(extracted.is_file())
            self.assertIn("200x200", image_info.stderr)


class DesktopAdapterTests(unittest.TestCase):
    def test_worker_slot_is_released_when_engine_raises(self):
        class App:
            def __init__(self):
                self.released = 0

            def schedule_task_update(self, *args):
                pass

            def release_worker_slot(self):
                self.released += 1

        app = App()
        with patch.object(task_processing, "run_download", side_effect=RuntimeError("broken")):
            with self.assertRaisesRegex(RuntimeError, "broken"):
                task_processing.process_task("job", "https://youtu.be/video", "output", app)

        self.assertEqual(app.released, 1)


if __name__ == "__main__":
    unittest.main()
