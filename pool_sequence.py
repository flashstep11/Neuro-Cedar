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

Storage: one JSON document in the database (state_store, key "pool_sequences"),
so it survives restarts and redeploys on any host. Layout:
  {"version", "pool_key", "created_utc", "block": [[num, den], ...],
   "queues": {"<cell>|r<round>": [[num, den], ...]},
   "next":   {"<cell>|r<round>": <next unused index>}}

Concurrency: every draw is one transaction with the document row locked
(SELECT ... FOR UPDATE on Postgres), so two participants can never receive the
same outcome position.
"""
import json
import math
import random
from datetime import datetime, timezone
from fractions import Fraction as Fr
from functools import reduce

import state_store
from config import ACTIVE_POOL, ACTIVE_POOL_KEY, POOL_SEQ_VERSION, POOL_SEQ_LENGTH

STATE_KEY = "pool_sequences"

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


def _check(data):
    if data.get("version") != POOL_SEQ_VERSION or data.get("pool_key") != ACTIVE_POOL_KEY:
        raise PoolSequenceMismatch(
            f"The stored pool sequence is version {data.get('version')!r} / pool {data.get('pool_key')!r}, "
            f"config expects {POOL_SEQ_VERSION!r} / {ACTIVE_POOL_KEY!r}. Use a fresh database (or archive "
            "the old state) and start a new data collection (protocol change) rather than mixing sequences.")


def _load_locked(tx):
    """Return the sequence document (row locked), generating it exactly once."""
    data = tx.lock_get(STATE_KEY, None)
    if data is None:
        data = _generate()
        tx.put(STATE_KEY, data)
    else:
        _check(data)
    return data


def ensure_generated():
    """Create the sequence now (call at startup, before recruitment). Idempotent."""
    state_store.run(lambda tx: _load_locked(tx) and None)


def draw_pool_return(condition_key: str, round_no: int):
    """
    Assign the next unused outcome for (cell, round).
    Returns (Fraction r, index_used, version). Callers must store the result and
    never call this twice for the same participant and round.
    """
    key = f"{condition_key}|r{int(round_no)}"

    def txn(tx):
        data = _load_locked(tx)
        if key not in data["queues"]:
            raise KeyError(f"unknown pool queue {key!r}")
        i = data["next"][key]
        if i >= len(data["queues"][key]):
            raise PoolSequenceExhausted(f"pool sequence {key} used up ({i} outcomes)")
        num, den = data["queues"][key][i]
        data["next"][key] = i + 1
        tx.put(STATE_KEY, data)
        return num, den, i, data["version"]

    num, den, i, version = state_store.run(txn)
    return Fr(num, den), i, version


def usage_summary():
    """{queue: (used, length)} for the admin report."""
    def txn(tx):
        row = tx.execute("SELECT value FROM cl_state WHERE key = ?", (STATE_KEY,)).fetchone()
        return json.loads(row[0]) if row else None

    data = state_store.run(txn)
    if not data:
        return {}
    return {k: (data["next"][k], len(v)) for k, v in data["queues"].items()}
