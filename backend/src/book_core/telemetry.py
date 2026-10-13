"""Standard-library wall/CPU/RSS measurements (bytes, seconds; no runtime dependency)."""

import ctypes
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

COUNTERS = ContextVar("book_run_counters", default=None)


def count(name, amount=1):
    counters = COUNTERS.get()
    if counters is not None:
        counters[name] = counters.get(name, 0) + amount


def memory():
    if os.name == "nt":

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

        value = Counters()
        value.cb = ctypes.sizeof(value)
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.c_void_p(kernel.GetCurrentProcess()), ctypes.byref(value), value.cb
        ):
            raise ctypes.WinError()
        return value.rss, value.peak
    from pathlib import Path

    values = {
        line.split(":")[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith(("VmRSS:", "VmHWM:"))
    }
    return values["VmRSS"], values["VmHWM"]


def available_memory():
    if os.name == "nt":

        class Status(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                *[
                    (name, ctypes.c_ulonglong)
                    for name in (
                        "total",
                        "available",
                        "total_page",
                        "available_page",
                        "total_virtual",
                        "available_virtual",
                        "extended",
                    )
                ],
            ]

        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError()
        return status.available
    from pathlib import Path

    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("Available memory cannot be determined")


@contextmanager
def measure(target, name):
    counters = {}
    token = COUNTERS.set(counters)
    stop = threading.Event()
    peak = [memory()[0]]

    def sample():
        while not stop.wait(0.02):
            peak[0] = max(peak[0], memory()[0])

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    wall, cpu = time.perf_counter(), time.process_time()
    try:
        yield counters
    finally:
        elapsed, consumed = time.perf_counter() - wall, time.process_time() - cpu
        stop.set()
        sampler.join()
        peak[0] = max(peak[0], memory()[0])
        target[name] = {
            "wall_seconds": elapsed,
            "cpu_seconds": consumed,
            "peak_rss_bytes": peak[0],
            **counters,
        }
        COUNTERS.reset(token)
