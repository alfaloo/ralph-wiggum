"""Atomic, cross-process-safe JSON file I/O for Ralph Wiggum.

Uses `filelock.FileLock` for exclusive advisory locking and an atomic
temp-file + os.replace() pattern to prevent partial writes and corruption
when multiple Claude Code agents access shared files concurrently.
"""

import json
import os
import tempfile
from contextlib import contextmanager

from filelock import FileLock

# Stale-lock timeout in seconds: if a lock file is older than this, it is
# considered stale and may be broken.
_LOCK_TIMEOUT = 30


@contextmanager
def locked_json_rw(path: str):
    """Context manager for atomic read-modify-write of a JSON file.

    Acquires an exclusive advisory lock on ``path + ".lock"`` before reading,
    yields the parsed Python object to the caller for in-place modification,
    and on exit writes the (possibly modified) data back atomically using a
    temporary file and ``os.replace()``.

    Usage::

        with locked_json_rw("tasks.json") as data:
            data["tasks"][0]["status"] = "completed"

    The lock is held for the entire duration of the ``with`` block.  Only one
    process (or thread) can hold the lock at a time; others wait up to
    ``_LOCK_TIMEOUT`` seconds before raising a ``filelock.Timeout``.
    """
    lock_path = path + ".lock"
    lock = FileLock(lock_path, timeout=_LOCK_TIMEOUT)

    with lock:
        # Re-read inside the lock to pick up any changes made by a concurrent
        # writer that completed between our last read and acquiring the lock.
        with open(path) as fh:
            data = json.load(fh)

        yield data

        # Atomic write: write to a temp file in the same directory so that the
        # rename is guaranteed to be atomic on POSIX systems (same filesystem).
        dir_name = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            # Clean up the temp file if something goes wrong to avoid leaving
            # stale .tmp files on disk.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def read_json(path: str):
    """Read and parse a JSON file without acquiring a lock.

    Suitable for read-only accesses where the caller does not need to write
    back the data.  For read-modify-write operations use ``locked_json_rw``
    instead.
    """
    with open(path) as fh:
        return json.load(fh)


def write_json(path: str, data) -> None:
    """Atomically write *data* as JSON to *path*.

    Acquires an exclusive advisory lock on ``path + ".lock"``, writes to a
    temporary file in the same directory, then renames the temp file over
    *path* so the update is atomic.
    """
    lock_path = path + ".lock"
    lock = FileLock(lock_path, timeout=_LOCK_TIMEOUT)

    with lock:
        dir_name = os.path.dirname(os.path.abspath(path))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
