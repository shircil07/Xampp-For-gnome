"""Small, safe file helpers."""

import os
import shutil
import tempfile
from pathlib import Path


def atomic_write(path, text: str, mode: int | None = None) -> None:
    """Replace `path` with `text` atomically (temp file + rename in the same dir).

    Keeps the existing file's permission bits unless `mode` is given.
    """
    path = Path(path)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o7777
        except FileNotFoundError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def backup_once(path) -> Path:
    """Copy `path` to `<path>.xampp-panel.bak` unless that backup already exists."""
    path = Path(path)
    bak = path.with_name(path.name + ".xampp-panel.bak")
    if path.exists() and not bak.exists():
        shutil.copy2(path, bak)
    return bak


def _tail_bytes(fh, max_bytes: int = 65536) -> str:
    """Read at most the last `max_bytes` of a binary file object, starting at a line boundary."""
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    fh.seek(max(0, size - max_bytes))
    data = fh.read()
    text = data.decode("utf-8", errors="replace")
    if size > max_bytes:
        text = text.partition("\n")[2]
    return text


def tail(path, max_bytes: int = 65536) -> str:
    """Return at most the last `max_bytes` of a text file, starting at a line boundary."""
    with open(path, "rb") as fh:
        return _tail_bytes(fh, max_bytes)
