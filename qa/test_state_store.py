"""
qa/test_state_store.py — verifies the database-backed study state.

Run against the local SQLite fallback (default, uses a temp folder):
    python qa/test_state_store.py

Run against Postgres (any provider). The script DROPS its own two tables
(cl_state, lottery_entries) first, so point it at a scratch database:
    set STATE_DATABASE_URL=postgresql://user:pass@host/dbname
    set CL_TEST_RESET=1
    python qa/test_state_store.py

Checks, under concurrent load:
  * assignment is atomic: 200 simultaneous arrivals fill the four cells exactly evenly
  * assignment is idempotent per participant; completion is counted once per participant
  * pool outcomes: no two participants get the same position; 80 consecutive draws
    contain exactly 20 / 40 / 20 of the balanced block (-30% / +20% / +50%)
  * an exhausted queue raises instead of recycling or replenishing
  * a sequence-version mismatch refuses to mix designs
  * a dropped connection is retried instead of failing the participant
  * lottery contacts are stored and retrievable by claim token only
"""
import os
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if not (os.environ.get("STATE_DATABASE_URL") or os.environ.get("DATABASE_URL", "")).startswith("postgres"):
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cl_state_test_")

import state_store                       # noqa: E402
import assignment                        # noqa: E402
import pool_sequence as ps               # noqa: E402
import lottery_db                        # noqa: E402

kind, _ = state_store.resolve("state")
print(f"backend: {state_store.describe('state')}")

if kind == "pg":
    if os.environ.get("CL_TEST_RESET") != "1":
        sys.exit("Refusing to touch a Postgres database without CL_TEST_RESET=1 (this test drops cl_state).")
    state_store.run(lambda tx: tx.execute("DROP TABLE IF EXISTS cl_state"))
    state_store.run(lambda tx: tx.execute("DROP TABLE IF EXISTS lottery_entries"), db="lottery")
    state_store._init_done.clear()

failures = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --- assignment ------------------------------------------------------------
print("\nassignment")
with ThreadPoolExecutor(16) as pool:
    cells = list(pool.map(lambda i: assignment.assign_participant(f"P{i:04d}"), range(200)))
counts = Counter(f"{u}_{r}" for u, r in cells)
check("200 concurrent arrivals fill all four cells exactly evenly",
      sorted(counts.values()) == [50, 50, 50, 50], str(dict(counts)))
check("same participant code returns the same cell",
      all(assignment.assign_participant(f"P{i:04d}") == cells[i] for i in range(0, 200, 17)))

ui, rew = cells[0]
before = assignment.get_assignment_summary()["completers"][f"{ui}_{rew}"]
for _ in range(3):                                   # page refresh must not double count
    assignment.record_completion("P0000", ui, rew)
after = assignment.get_assignment_summary()
check("completion counted once however often the debrief loads",
      after["completers"][f"{ui}_{rew}"] == before + 1)
check("completion releases the in-flight slot", after["total_in_flight"] == 199, str(after["total_in_flight"]))
assignment.record_abandonment("P0001")
check("abandonment releases the in-flight slot", assignment.get_assignment_summary()["total_in_flight"] == 198)

# --- pool sequence ---------------------------------------------------------
print("\npool sequence")
ps.ensure_generated()
ps.ensure_generated()                                # idempotent: must not regenerate
usage = ps.usage_summary()
check("8 queues (4 cells x 2 rounds) of the configured length",
      len(usage) == 8 and all(n == ps.POOL_SEQ_LENGTH for _, n in usage.values()), str(usage))
with ThreadPoolExecutor(16) as pool:
    draws = list(pool.map(lambda _: ps.draw_pool_return("neutral_0pct", 1), range(80)))
idx = sorted(i for _, i, _ in draws)
check("80 concurrent draws get 80 distinct consecutive positions", idx == list(range(80)))
outcomes = Counter(r for r, _, _ in draws)
from fractions import Fraction as Fr             # noqa: E402
check("80 draws = 20 blocks: exactly 20 x -30%, 40 x +20%, 20 x +50%",
      outcomes == Counter({Fr(-3, 10): 20, Fr(1, 5): 40, Fr(1, 2): 20}), str(outcomes))
check("each draw returns the sequence version", all(v == ps.POOL_SEQ_VERSION for _, _, v in draws))

for _ in range(ps.POOL_SEQ_LENGTH):
    ps.draw_pool_return("neutral_35pct", 2)
try:
    ps.draw_pool_return("neutral_35pct", 2)
    check("exhausted queue raises (no recycling / replenishing)", False)
except ps.PoolSequenceExhausted:
    check("exhausted queue raises (no recycling / replenishing)", True)

state_store.run(lambda tx: tx.put(ps.STATE_KEY, {**tx.lock_get(ps.STATE_KEY, None), "version": "OLD"}))
try:
    ps.draw_pool_return("neutral_0pct", 1)
    check("version mismatch refuses to mix sequences", False)
except ps.PoolSequenceMismatch:
    check("version mismatch refuses to mix sequences", True)
state_store.run(lambda tx: tx.put(ps.STATE_KEY, {**tx.lock_get(ps.STATE_KEY, None), "version": ps.POOL_SEQ_VERSION}))

# --- dropped connection ----------------------------------------------------
print("\nresilience")
real_connect, calls = state_store._connect, {"n": 0}


def flaky(kind_, target):
    calls["n"] += 1
    if calls["n"] == 1:
        if kind_ == "pg":
            import psycopg2
            raise psycopg2.OperationalError("server closed the connection unexpectedly")
        import sqlite3
        raise sqlite3.OperationalError("simulated transient failure")
    return real_connect(kind_, target)


state_store._connect = flaky
try:
    r = ps.draw_pool_return("manipulative_0pct", 1)
    check("a dropped connection is retried and the draw succeeds", r[1] == 0 and calls["n"] >= 2)
finally:
    state_store._connect = real_connect
check("the retried draw consumed exactly one position",
      ps.usage_summary()["manipulative_0pct|r1"][0] == 1, str(ps.usage_summary()["manipulative_0pct|r1"]))

# --- lottery ---------------------------------------------------------------
print("\nlottery contacts")
lottery_db.init_db()
tokens = [lottery_db.create_entry() for _ in range(5)]
check("claim tokens are unique", len(set(tokens)) == 5)
lottery_db.update_contact(tokens[2], "Asha", "asha@example.com", "+911234567890")


def read(tx):
    return tx.execute("SELECT name, email, phone FROM lottery_entries WHERE claim_token = ?", (tokens[2],)).fetchone()


check("contact stored against the claim token only",
      tuple(state_store.run(read, db="lottery")) == ("Asha", "asha@example.com", "+911234567890"))
state_store.run(lambda tx: None, db="lottery")

print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED: {failures}"))
sys.exit(1 if failures else 0)
