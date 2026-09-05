"""Chrome Native Messaging entry point. This is not a command-line interface."""

import json
import logging
import os
from pathlib import Path
import re
import struct
import sys
import threading
import tkinter as tk
from tkinter import filedialog
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import uuid

from config import MAX_WORKERS, FFMPEG_PATH, YTDLP_PATH
from download_engine import run_download
from utils import parse_youtube_url, prepare_external_subprocesses

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024
LOG = logging.getLogger(__name__)


def read_exact(stream, length):
    chunks = bytearray()
    while len(chunks) < length:
        data = stream.read(length - len(chunks))
        if not data:
            raise ValueError("Truncated native message")
        chunks.extend(data)
    return bytes(chunks)


def read_message(stream):
    first = stream.read(1)
    if not first:
        return None
    length = struct.unpack("<I", first + read_exact(stream, 3))[0]
    if not 0 < length <= MAX_MESSAGE_BYTES:
        raise ValueError("Invalid native message size")
    message = json.loads(read_exact(stream, length).decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("Expected a JSON object")
    return message


class MessageWriter:
    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def __call__(self, message):
        payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.stream.write(struct.pack("<I", len(payload)) + payload)
            self.stream.flush()


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ["LOCALAPPDATA"]) / "EasyMP3" / "settings.json"
        self.output_folder = str(Path.home() / "Music")
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            folder = saved.get("outputFolder")
            if isinstance(folder, str) and folder and Path(folder).is_absolute():
                self.output_folder = folder
        except (OSError, ValueError, AttributeError):
            pass

    def save_folder(self, folder):
        path = Path(folder)
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Choose an existing folder")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"settings-{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({"outputFolder": str(path)}), encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.output_folder = str(path)


def choose_folder(initial):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, initialdir=initial,
                                       title="EasyMP3 output folder", mustexist=True)
    finally:
        root.destroy()


def canonical_video_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Expected a YouTube video URL")
    split = urlsplit(value)
    if split.scheme not in {"https", "http"} or split.username or split.password or split.port:
        raise ValueError("Expected a YouTube video URL")
    parsed = parse_youtube_url(value)
    if not parsed or not parsed.video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", parsed.video_id):
        raise ValueError("Expected a single YouTube video URL")
    return parsed.video_url


class NativeHost:
    def __init__(self, send, settings, runner=run_download, picker=choose_folder):
        self.send = send
        self.settings = settings
        self.runner = runner
        self.picker = picker
        self.lock = threading.RLock()
        self.active = {}
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def handle(self, message):
        request_id = message.get("id")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise ValueError("Expected a request id")
        try:
            kind = message.get("type")
            if kind == "hello":
                self.send({"id": request_id, "ok": True, "protocolVersion": PROTOCOL_VERSION,
                           "outputFolder": self.settings.output_folder})
            elif kind == "choose_folder":
                folder = self.picker(self.settings.output_folder)
                if folder:
                    self.settings.save_folder(folder)
                self.send({"id": request_id, "ok": True, "outputFolder": self.settings.output_folder})
            elif kind == "download":
                url = canonical_video_url(message.get("url"))
                if not YTDLP_PATH.is_file() or not FFMPEG_PATH.is_file():
                    raise ValueError("Helper package is missing yt-dlp.exe or ffmpeg.exe. Reinstall the helper.")
                with self.lock:
                    if url in self.active:
                        self.send({"id": request_id, "ok": True, "jobId": self.active[url]["id"]})
                        return
                    job = {"id": uuid.uuid4().hex, "url": url, "status": "Queued"}
                    self.active[url] = job
                    self.send({"id": request_id, "ok": True, "jobId": job["id"]})
                    self.send({"type": "job", "job": dict(job)})
                    self.executor.submit(self._run, job, self.settings.output_folder)
            else:
                raise ValueError("Unknown request type")
        except Exception as error:
            LOG.warning("Request %s failed: %s", request_id, error)
            self.send({"id": request_id, "ok": False, "error": str(error)})

    def _run(self, job, folder):
        def update(_task_id, column, value):
            with self.lock:
                if column == "Filename":
                    job["filename"] = value
                elif column == "Status":
                    # Only the final result is terminal, after all file work finishes.
                    if value.startswith("Error") or value == "Completed":
                        return
                    job["status"] = value
                self.send({"type": "job", "job": dict(job)})

        try:
            result = self.runner(job["id"], job["url"], folder, update)
            job["status"] = "Completed" if result.success else "Error"
            if result.output_path:
                job["outputPath"] = str(result.output_path)
            if result.error:
                job["error"] = result.error
        except Exception as error:
            LOG.exception("Download failed")
            job.update(status="Error", error=str(error))
        finally:
            with self.lock:
                self.active.pop(job["url"], None)
                self.send({"type": "job", "job": dict(job)})
                if not self.active:
                    self.send({"type": "idle"})

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait, cancel_futures=not wait)


def main():
    import msvcrt
    from windows_job import WindowsJob
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    writer = MessageWriter(sys.stdout.buffer)
    # Any accidental prints from dependencies must never corrupt the protocol.
    sys.stdout = sys.stderr
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    job_guard = WindowsJob()
    prepare_external_subprocesses()
    host = NativeHost(writer, Settings())
    try:
        while (message := read_message(sys.stdin.buffer)) is not None:
            host.handle(message)
    except (ValueError, OSError):
        LOG.exception("Native connection closed or invalid")
    finally:
        host.shutdown(wait=False)
        # Do not wait for executor threads after Chrome disconnects. Exiting closes
        # the job handle and kills yt-dlp, ffmpeg, and any nested child processes.
        os._exit(0)


if __name__ == "__main__":
    main()
