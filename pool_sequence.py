"""
pool_sequence.py — Pre-generated per-condition pool outcome sequences.

Each participant (after submitting R) draws ONE outcome from their
condition's sequence. Outcomes are balanced: shuffled blocks of the
pool's outcomes (each outcome appears proportionally across participants).

For pool B_EV5 with outcomes [-30%, +40%] (p=0.5 each), blocks of 2
are shuffled. The sequence is generated lazily and extended as needed,
stored in POOL_SEQ_PATH as JSON.

Idempotency: once a participant's pool return is stored in Player.pool_return,
it is never re-drawn. The assignment function should check this before calling.

Concurrency: same file-lock approach as assignment.py.
"""
import json
import os
import random
import sys
from fractions import Fraction as Fr

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

from config import POOL_SEQ_PATH, ACTIVE_POOL

# Outcomes as (numerator, denominator) pairs for JSON serialisation
OUTCOMES = [(r.numerator, r.denominator) for r, _ in ACTIVE_POOL]
# Block size = number of distinct outcomes (2 for B_EV5)
BLOCK_SIZE = len(OUTCOMES)
# Pre-generate enough for a large study
MIN_LENGTH = 500


def _fresh_block():
    block = list(OUTCOMES)
    random.shuffle(block)
    return block


def _load(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"queues": {}}


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def draw_pool_return(condition_key: str) -> Fr:
    """
    Draw one pool return Fraction for the given condition key
    (e.g. "neutral_0pct"). Extends the queue with fresh shuffled
    blocks if needed. Thread/process-safe via file lock.
    """
    lock_path = POOL_SEQ_PATH + ".lock"
    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            data = _load(POOL_SEQ_PATH)
            q = data["queues"].setdefault(condition_key, [])
            # Replenish if empty
            while not q:
                q.extend(_fresh_block())
            outcome_pair = q.pop(0)
            data["queues"][condition_key] = q
            _save(POOL_SEQ_PATH, data)
        finally:
            _unlock(lf)
    return Fr(outcome_pair[0], outcome_pair[1])

