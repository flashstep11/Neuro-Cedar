"""
pool_sequence.py — Pre-generated, balanced Growth Pool outcome sequences (v2).

Follows the implementation guide, section 3:
  * Generated ONCE, before the first participant needs it, separately for every
    cell (ui x reward) AND every round (1, 2).
  * Built from balanced blocks matching the pool's probabilities (pool C:
    one -30%, two +20%, one +50% per block of 4), each block shuffled with a
    cryptographically secure RNG (random.SystemRandom).
  * Outcomes are assigned in order, only after the reinvestment is submitted.
    The position used is returned so it can be stored with the participant.
  * NEVER replenished or recycled. If a queue runs out, draw raises
    PoolSequenceExhausted: extending it is a protocol change, not a code path.
  * The file records its version; if config.POOL_SEQ_VERSION changes, the app
    refuses to mix sequences and raises PoolSequenceMismatch.

File layout (JSON, kept on the persistent disk via DATA_DIR):
  {"version", "pool_key", "created_utc", "block": [[num, den], ...],
   "queues": {"<cell>|r<round>": [[num, den], ...]},
   "next":   {"<cell>|r<round>": <next unused index>}}

Concurrency: OS file lock around every read-modify-write (single server).
"""
import json
import math
import os
import random
import sys
from datetime import datetime, timezone
from fractions import Fraction as Fr
from functools import reduce

from config import POOL_SEQ_PATH, ACTIVE_POOL, ACTIVE_POOL_KEY, POOL_SEQ_VERSION, POOL_SEQ_LENGTH

if sys.platform == "win32":
    import msvcrt

    def _lock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(f):
        fcntl.flock(f, fcntl.LOCK_EX)

    def _unlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)


CELLS = ["neutral_0pct", "neutral_35pct", "manipulative_0pct", "manipulative_35pct"]
ROUNDS = [1, 2]
_RNG = random.SystemRandom()


class PoolSequenceExhausted(RuntimeError):
    pass


class PoolSequenceMismatch(RuntimeError):
    pass


def balanced_block(pool=ACTIVE_POOL):
    """Smallest block whose outcome counts match the probabilities exactly."""
    size = reduce(lambda a, b: a * b // math.gcd(a, b), (p.denominator for _, p in pool))
    block = []
    for r, p in pool:
        block += [r] * int(p * size)
    assert len(block) == size
    return block


def _generate():
    block = balanced_block()
    if POOL_SEQ_LENGTH % len(block):
        raise ValueError(f"POOL_SEQ_LENGTH must be a multiple of the block size {len(block)}")
    queues = {}
    for cell in CELLS:
        for rnd in ROUNDS:
            seq = []
            for _ in range(POOL_SEQ_LENGTH // len(block)):
                b = list(block)
                _RNG.shuffle(b)
                seq += b
            queues[f"{cell}|r{rnd}"] = [[r.numerator, r.denominator] for r in seq]
    return {
        "version": POOL_SEQ_VERSION,
        "pool_key": ACTIVE_POOL_KEY,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "block": [[r.numerator, r.denominator] for r in block],
        "queues": queues,
        "next": {k: 0 for k in queues},
    }


def _load_or_create():
    if os.path.exists(POOL_SEQ_PATH):
        with open(POOL_SEQ_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != POOL_SEQ_VERSION or data.get("pool_key") != ACTIVE_POOL_KEY:
            raise PoolSequenceMismatch(
                f"{POOL_SEQ_PATH} holds version {data.get('version')!r} / pool {data.get('pool_key')!r}, "
                f"config expects {POOL_SEQ_VERSION!r} / {ACTIVE_POOL_KEY!r}. Archive the old file "
                "and start a new data collection (protocol change) rather than mixing sequences.")
        return data, False
    return _generate(), True


def _save(data):
    tmp = POOL_SEQ_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, POOL_SEQ_PATH)          # atomic: never a half-written file


def ensure_generated():
    """Create the sequence file now (call at startup, before recruitment)."""
    with open(POOL_SEQ_PATH + ".lock", "w") as lf:
        _lock(lf)
        try:
            data, created = _load_or_create()
            if created:
                _save(data)
        finally:
            _unlock(lf)


def draw_pool_return(condition_key: str, round_no: int):
    """
    Assign the next unused outcome for (cell, round).
    Returns (Fraction r, index_used, version). Callers must store the result and
    never call this twice for the same participant and round.
    """
    key = f"{condition_key}|r{int(round_no)}"
    with open(POOL_SEQ_PATH + ".lock", "w") as lf:
        _lock(lf)
        try:
            data, _ = _load_or_create()
            if key not in data["queues"]:
                raise KeyError(f"unknown pool queue {key!r}")
            i = data["next"][key]
            if i >= len(data["queues"][key]):
                raise PoolSequenceExhausted(f"pool sequence {key} used up ({i} outcomes)")
            num, den = data["queues"][key][i]
            data["next"][key] = i + 1
            _save(data)
        finally:
            _unlock(lf)
    return Fr(num, den), i, data["version"]


def usage_summary():
    """{queue: (used, length)} for the admin report."""
    if not os.path.exists(POOL_SEQ_PATH):
        return {}
    with open(POOL_SEQ_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {k: (data["next"][k], len(v)) for k, v in data["queues"].items()}
