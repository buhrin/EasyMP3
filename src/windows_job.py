"""Tie all helper descendants to its lifetime (Windows 8 or later)."""

import ctypes
from ctypes import wintypes


class WindowsJob:
    """Keep this object alive until process exit. Never inherit its handle."""

    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        size_t = ctypes.c_size_t

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                ("Flags", wintypes.DWORD), ("MinWorkingSet", size_t),
                ("MaxWorkingSet", size_t), ("ActiveProcesses", wintypes.DWORD),
                ("Affinity", size_t), ("Priority", wintypes.DWORD),
                ("Scheduling", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes"
            )]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("Basic", BasicLimits), ("Io", IoCounters),
                        ("ProcessMemory", size_t), ("JobMemory", size_t),
                        ("PeakProcessMemory", size_t), ("PeakJobMemory", size_t)]

        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                   ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits),
                                               ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            kernel.CloseHandle(self.handle)
            raise error
        if not kernel.AssignProcessToJobObject(self.handle, kernel.GetCurrentProcess()):
            error = ctypes.WinError(ctypes.get_last_error())
            kernel.CloseHandle(self.handle)
            raise error
        # The OS closes this non-inherited handle on exit, including forced exit.
        self.kernel = kernel
