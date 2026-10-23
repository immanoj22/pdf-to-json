"""Monitor an explicitly verified, owned Windows validation PID; stop below reserve.

No enumeration or cleanup. The caller verifies the PID's command before invoking this.
The open process handle identifies that process lifetime, even if Windows reuses its PID.
"""
import argparse
import ctypes
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path


def watch(pid, record):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x1, False, pid)  # query + terminate owned task
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    root = Path(__file__).resolve().parents[1]
    result = {"pid": pid, "started": datetime.now(timezone.utc).isoformat(),
              "reserve_bytes": 5_000_000_000, "sample_interval_seconds": .5,
              "minimum_free_bytes": shutil.disk_usage(root).free,
              "stopped_below_reserve": False}
    try:
        while True:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            free = shutil.disk_usage(root).free
            result["minimum_free_bytes"] = min(result["minimum_free_bytes"], free)
            if code.value != 259:  # STILL_ACTIVE
                result["exit_code"] = code.value
                break
            if free < result["reserve_bytes"]:
                result["stopped_below_reserve"] = True
                if not kernel.TerminateProcess(handle, 42):
                    raise ctypes.WinError(ctypes.get_last_error())
                break
            time.sleep(.5)
    finally:
        kernel.CloseHandle(handle)
        result["finished"] = datetime.now(timezone.utc).isoformat()
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(result, indent=1) + "\n", "utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    assert not args.record.exists(), "Preserve earlier monitor records"
    watch(args.pid, args.record)
