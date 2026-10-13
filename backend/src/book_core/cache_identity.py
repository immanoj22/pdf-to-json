"""Producer hashing algorithm, separate from the stage registry."""

import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_DIGESTS = ContextVar("run_producer_digests", default=None)


@contextmanager
def producer_session():
    token = _DIGESTS.set({})
    try:
        yield
    finally:
        _DIGESTS.reset(token)


def files_for(entries, root):
    root = Path(root)
    files = set()
    for entry in entries:
        path = root / entry
        if path.is_dir():
            files.update(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
        elif path.is_file():
            files.add(path)
    return sorted(p.relative_to(root).as_posix() for p in files)


def producer_digest(name, files, root):
    memo = _DIGESTS.get()
    key = (str(Path(root).resolve()), name)
    stamps = []
    if memo is not None:
        for relative in files:
            stat = (Path(root) / relative).stat()
            stamps.append((relative, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        prior = memo.get(key)
        if prior is not None and prior[0] == stamps:
            return prior[1]
    digest = hashlib.sha256(name.encode("utf8"))
    for relative in files:
        data = (Path(root) / relative).read_bytes().replace(b"\r\n", b"\n")
        digest.update(b"\0" + relative.encode("utf8") + b"\0")
        digest.update(hashlib.sha256(data).digest())
    value = digest.hexdigest()
    if memo is not None:
        memo[key] = (stamps, value)
    return value
