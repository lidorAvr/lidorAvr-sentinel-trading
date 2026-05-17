"""
Atomic, lock-coordinated JSON state I/O.

`risk_monitor_state.json` is written by two containers that share the /app
volume: `risk-monitor` (full rewrite every ~60s cycle) and `telegram-bot`
(inline runner-decision read-modify-write on a user callback). Without
coordination this produced two failure modes (SYSTEM_AUDIT §5.7 / Issue N3):

  1. Torn read → silent reset. A reader hitting the file mid-write got a
     JSONDecodeError; the bot's `except` then reset state to ``{}`` and the
     next save flushed an empty file — wiping every position's alert state.
  2. Lost update. The two writers' rewrites interleaved.

This module is the single safe path:

  - ``atomic_write_json``: write to a temp file in the same dir, then
    ``os.replace`` (atomic on POSIX). A reader always sees a complete
    old-or-new file, never a partial one.
  - ``file_lock``: advisory ``fcntl.flock`` so the bot's RMW and
    risk-monitor's rewrite never interleave (shared /app volume → same
    inode, so the lock coordinates across containers).
  - ``read_json``: defensive read with a default.

Residual (documented, out of scope for N3): risk-monitor holds an in-memory
copy for its whole cycle, so a ``runner_decision`` the bot writes mid-cycle
can still be overshadowed by risk-monitor's end-of-cycle save. Full
resolution is Hyperscaler Phase B (state → DB). flock + atomic write removes
the catastrophic torn-state / empty-reset modes, which were the actual
cause of the unexplained duplicate alerts and vanishing checkpoints.
"""
import json
import os
import tempfile
from contextlib import contextmanager

try:
    import fcntl
    _HAVE_FCNTL = True
except ImportError:  # non-POSIX; not used in production, keeps imports safe
    _HAVE_FCNTL = False

# Sprint 14 (RC-2/RC-3): single shared path for the anti-spam state file.
# It lives on the EXISTING `sentinel_state:/app/state` named volume (same
# directory the heartbeat already uses) so it survives `git pull` deploys
# AND container `--force-recreate`. Both writers — risk_monitor.save_state
# and bot_helpers._write_runner_decision — import THIS constant so the path
# can never drift onto two inodes (a split-brain would defeat the fcntl
# lock and the dedup memory). No risk/NAV/campaign/stop math is touched;
# this only relocates a runtime JSON file.
RM_STATE_DIR = "/app/state"
RM_STATE_FILE = os.path.join(RM_STATE_DIR, "risk_monitor_state.json")


def lock_path_for(path: str) -> str:
    return f"{path}.lock"


@contextmanager
def file_lock(path: str):
    """Exclusive advisory lock keyed on ``<path>.lock``.

    Cross-container safe because every service mounts the repo at the same
    /app inode. Becomes a no-op when fcntl is unavailable.
    """
    if not _HAVE_FCNTL:
        yield
        return
    fd = open(lock_path_for(path), "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            fd.close()


def atomic_write_json(path: str, data) -> None:
    """Serialize ``data`` to ``path`` atomically (temp file + os.replace)."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".tmp_state_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: str, default):
    """Read JSON from ``path``; return ``default`` on any failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
