"""
assignment.py — Balanced 2×2 between-subjects assignment.

Design: pre-generated shuffled blocks of 4 (one per cell), allocated under
a file-level lock so concurrent requests don't duplicate assignments.

Cells:
  (ui_condition, reward_condition)
  ui_condition  : "neutral" | "manipulative"
  reward_condition: "0pct" | "35pct"

Concurrency approach:
  We use a JSON file + OS-level exclusive file lock (msvcrt on Windows,
  fcntl on POSIX). The lock is held only for the brief read-modify-write
  cycle (~microseconds). This is safe for a single-process dev server and
  for a single-worker production Uvicorn process.

  Trade-off: If you run multiple Uvicorn workers (e.g. gunicorn -w 4),
  use a Postgres sequence or Redis counter instead — the file lock works
  cross-process on a single machine but NOT across machines/containers.
  Document this in ops notes and enforce single-worker in production.
"""
import json
import os
import random
import sys

# Windows vs POSIX file locking
if sys.platform == "win32":
    import msvcrt
    def _lock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    def _unlock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    def _lock(f):
        fcntl.flock(f, fcntl.LOCK_EX)
    def _unlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)

from config import ASSIGNMENT_STATE_PATH

CELLS = [
    ("neutral",       "0pct"),
    ("neutral",       "35pct"),
    ("manipulative",  "0pct"),
    ("manipulative",  "35pct"),
]

BLOCK_SIZE = len(CELLS)   # 4


def _fresh_block():
    """Return one shuffled block of 4 cell assignments."""
    block = list(CELLS)
    random.shuffle(block)
    return block


def _load_state(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {"queue": []}


def _save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f)


def assign_participant():
    """
    Pop the next cell assignment from the queue.
    If queue is empty, generate a new shuffled block first.
    Returns (ui_condition: str, reward_condition: str).
    """
    lock_path = ASSIGNMENT_STATE_PATH + ".lock"
    # Open (create if needed) a separate lock file
    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            state = _load_state(ASSIGNMENT_STATE_PATH)
            if not state["queue"]:
                state["queue"] = [list(c) for c in _fresh_block()]
            cell = state["queue"].pop(0)
            _save_state(ASSIGNMENT_STATE_PATH, state)
        finally:
            _unlock(lf)
    return tuple(cell)   # (ui_condition, reward_condition)

