import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from download_engine import DownloadResult
from native_host import MessageWriter, NativeHost, Settings, canonical_video_url, read_message


class ProtocolTests(unittest.TestCase):
    def test_multiple_utf8_frames_and_clean_eof(self):
        stream = io.BytesIO()
        writer = MessageWriter(stream)
        for message in [{"id": "1", "title": "日本語 🎵"}, {"id": "2", "ok": True}]:
            writer(message)
        stream.seek(0)
        self.assertEqual(read_message(stream)["title"], "日本語 🎵")
        self.assertTrue(read_message(stream)["ok"])
        self.assertIsNone(read_message(stream))

    def test_invalid_frames(self):
        for data in [b"\x01", struct.pack("<I", 65537), struct.pack("<I", 3) + b"{}",
                     struct.pack("<I", 2) + b"[]", struct.pack("<I", 1) + b"\xff"]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                read_message(io.BytesIO(data))

    def test_single_video_normalized_and_invalid_urls_rejected(self):
        self.assertEqual(canonical_video_url("https://www.youtube.com/watch?v=abcdefghijk&list=PLfoo"),
                         "https://www.youtube.com/watch?v=abcdefghijk")
        self.assertEqual(canonical_video_url("https://www.youtube.com/shorts/abcdefghijk"),
                         "https://www.youtube.com/watch?v=abcdefghijk")
        for url in [None, "https://youtube.com.evil.test/watch?v=abcdefghijk",
                    "https://www.youtube.com/playlist?list=PLfoo", "file://youtube.com/watch?v=abcdefghijk",
                    "https://a@youtube.com/watch?v=abcdefghijk", "https://youtube.com/watch?v=--exec"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_video_url(url)

    def test_settings_save_cancel_and_bad_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(path)
            settings.save_folder(directory)
            self.assertEqual(Settings(path).output_folder, directory)
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(Settings(path).output_folder, str(Path.home() / "Music"))


class QueueTests(unittest.TestCase):
    def test_ten_workers_queue_duplicates_folder_snapshot_and_idle(self):
        messages = []
        started = []
        lock = threading.Lock()
        ten_started = threading.Event()
        release = threading.Event()

        def runner(task, url, folder, update):
            with lock:
                started.append((url, folder))
                if len(started) == 10:
                    ten_started.set()
            update(task, "Status", "Downloading...")
            release.wait(10)
            return DownloadResult(True, Path(folder) / "track.mp3", None)

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            settings.save_folder(directory)
            host = NativeHost(messages.append, settings, runner=runner)
            try:
                for index in range(12):
                    host.handle({"id": str(index), "type": "download",
                                 "url": f"https://youtube.com/watch?v={index:011d}"})
                self.assertTrue(ten_started.wait(5))
                self.assertEqual(len(started), 10)
                host.handle({"id": "duplicate", "type": "download",
                             "url": "https://youtube.com/watch?v=00000000000"})
                ids = {m["id"]: m.get("jobId") for m in messages if "id" in m}
                self.assertEqual(ids["0"], ids["duplicate"])
                settings.output_folder = "different-folder"
            finally:
                release.set()
                host.shutdown()
            self.assertEqual(len(started), 12)
            self.assertTrue(all(folder == directory for _, folder in started))
            self.assertEqual(sum(m.get("type") == "idle" for m in messages), 1)
            self.assertEqual(sum(m.get("job", {}).get("status") == "Completed" for m in messages), 12)
            self.assertEqual(host.active, {})

    def test_failures_are_terminal_and_do_not_block_queue(self):
        messages = []
        def runner(*args):
            raise RuntimeError("test failure")
        with tempfile.TemporaryDirectory() as directory:
            host = NativeHost(messages.append, Settings(Path(directory) / "settings.json"), runner=runner)
            host.handle({"id": "1", "type": "download", "url": "https://youtu.be/abcdefghijk"})
            host.shutdown()
        terminal = [m["job"] for m in messages if m.get("job", {}).get("status") == "Error"]
        self.assertEqual(terminal[0]["error"], "test failure")
        self.assertEqual(messages[-1], {"type": "idle"})

    def test_missing_tools_unknown_request_and_picker_cancel(self):
        messages = []
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory) / "settings.json")
            host = NativeHost(messages.append, settings, picker=lambda initial: "")
            try:
                host.handle({"id": "hello", "type": "hello"})
                self.assertEqual(messages[-1]["protocolVersion"], 1)
                host.handle({"id": "folder", "type": "choose_folder"})
                self.assertEqual(messages[-1]["outputFolder"], settings.output_folder)
                self.assertFalse(settings.path.exists())
                with patch("native_host.YTDLP_PATH", Path(directory) / "absent.exe"):
                    host.handle({"id": "download", "type": "download", "url": "https://youtu.be/abcdefghijk"})
                self.assertFalse(messages[-1]["ok"])
                host.handle({"id": "unknown", "type": "execute"})
                self.assertFalse(messages[-1]["ok"])
            finally:
                host.shutdown()


if __name__ == "__main__":
    unittest.main()
