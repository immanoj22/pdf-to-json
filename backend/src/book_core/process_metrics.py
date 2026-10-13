"""Sample aggregate RSS for explicitly announced workers using only the standard library."""

import ctypes
import os
import threading
from pathlib import Path

from book_core.telemetry import memory


def rss(pid):
    if pid == os.getpid():
        return memory()[0]
    if os.name != "nt":
        try:
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
        except (FileNotFoundError, PermissionError):
            return 0
        return 0

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("faults", ctypes.c_ulong),
            *[
                (name, ctypes.c_size_t)
                for name in (
                    "peak",
                    "rss",
                    "peak_pool",
                    "pool",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ],
        ]

    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)
    if not handle:
        return 0
    try:
        value = Counters()
        value.cb = ctypes.sizeof(value)
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(handle), ctypes.byref(value), value.cb
        ):
            return value.rss
        return 0
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


class ProcessMonitor:
    def __init__(self):
        self.pids = {os.getpid()}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.peak = rss(os.getpid())

    def add(self, pid):
        with self.lock:
            self.pids.add(pid)

    def sample(self):
        with self.lock:
            pids = tuple(self.pids)
        self.peak = max(self.peak, sum(rss(pid) for pid in pids))

    def _loop(self):
        while not self.stop.wait(0.02):
            self.sample()

    def __enter__(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join()
        self.sample()
