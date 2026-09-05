"""Real subprocess checks; no network, registry writes, or user settings edits."""
import ctypes
from ctypes import wintypes
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from native_host import MessageWriter, read_message

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "Windows process lifetime")
class WindowsLifecycleTests(unittest.TestCase):
    def test_native_disconnect_during_download_stops_child(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        code = """
import sys, subprocess
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import native_host
def runner(task_id, url, folder, update):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    Path(sys.argv[2]).write_text(str(child.pid))
    child.wait()
    raise RuntimeError('Child should be stopped with host')
base = native_host.NativeHost
class TestHost(base):
    def __init__(self, send, settings):
        super().__init__(send, settings, runner=runner)
native_host.NativeHost = TestHost
native_host.main()
"""
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "pid.txt"
            environment = dict(os.environ, LOCALAPPDATA=directory)
            process = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "src"), str(pid_file)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, env=environment)
            handle = None
            try:
                MessageWriter(process.stdin)({"id": "job", "type": "download",
                                              "url": "https://youtu.be/abcdefghijk"})
                deadline = time.monotonic() + 10
                while not pid_file.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pid_file.exists())
                handle = kernel.OpenProcess(0x00100000, False, int(pid_file.read_text()))
                self.assertTrue(handle)
                process.stdin.close()
                process.stdin = None
                output, errors = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, errors.decode())
                self.assertTrue(read_message(io.BytesIO(output))["ok"])
                self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
                if handle:
                    kernel.CloseHandle(handle)

    def test_native_host_hello_and_eof(self):
        stream = io.BytesIO()
        MessageWriter(stream)({"id": "hello", "type": "hello"})
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, LOCALAPPDATA=directory)
            result = subprocess.run([sys.executable, str(ROOT / "src/native_host.py")],
                                    input=stream.getvalue(), capture_output=True, timeout=15, env=environment)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        reply = read_message(io.BytesIO(result.stdout))
        self.assertEqual(reply["id"], "hello")
        self.assertTrue(reply["ok"])

    def test_parent_exit_or_crash_kills_descendants(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        for crash in [False, True]:
            with self.subTest(crash=crash), tempfile.TemporaryDirectory() as directory:
                pid_file = Path(directory) / "pid.txt"
                code = (
                    "import sys, subprocess, os; from pathlib import Path; "
                    "sys.path.insert(0, sys.argv[1]); from windows_job import WindowsJob; "
                    "guard=WindowsJob(); "
                    "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                    "Path(sys.argv[2]).write_text(str(child.pid)); sys.stdin.buffer.read(1); os._exit(0)"
                )
                process = subprocess.Popen([sys.executable, "-c", code, str(ROOT / "src"), str(pid_file)],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                handle = None
                try:
                    deadline = time.monotonic() + 10
                    while not pid_file.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(pid_file.exists(), "Job-guard process did not start")
                    pid = int(pid_file.read_text())
                    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                    self.assertTrue(handle)
                    if crash:
                        process.kill()
                    else:
                        process.stdin.write(b"x")
                        process.stdin.flush()
                    process.communicate(timeout=10)
                    self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0,
                                     "Descendant remained alive after parent exit")
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=10)
                    if handle:
                        kernel.CloseHandle(handle)


if __name__ == "__main__":
    unittest.main()
