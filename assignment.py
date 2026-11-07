"""
assignment.py — Completer-Balanced 2×2 Between-Subjects Assignment.

Approach: Dynamic Minimization on Completers with In-Flight Reservation.

Why pure permuted blocks fail for completers:
  Fixed permuted block allocation (e.g. shuffled blocks of 4) guarantees balance
  among participants who START the study. However, in online experiments, participants
  frequently abandon midway (close their browser, phone lock, etc.). If dropouts
  occur at different rates across cells (e.g., higher friction in the manipulative
  arm), pure permuted blocks lead to unbalanced cells among COMPLETERS, degrading
  statistical power.

How our Completer-Balanced algorithm works:
  1. We track confirmed completers per cell:
     C(cell) = number of participants who reached and finished Debrief.
  2. To prevent concurrent arrivals from all clumping into the same cell before
     any of them finishes, we maintain an in-flight reservation table:
     A(cell) = participants currently between Assignment and Debrief.
     Effective count: E(cell) = C(cell) + A(cell).
  3. When a new participant reaches Assignment, we pick the cell with
     min(E(cell)). Ties are broken uniformly at random.
  4. If a participant drops out, their in-flight reservation expires after
     IN_FLIGHT_TIMEOUT_SECS (default 30 min; this single-sitting study takes ~3-5 min).
     The cell's effective count drops, automatically routing subsequent participants
     to backfill the uncompleted slot.
  5. When a participant completes Debrief, C(cell) is incremented and their
     in-flight reservation is released.

Concurrency safety:
  All state mutations are protected by an OS-level exclusive file lock
  (msvcrt on Windows, fcntl on POSIX) around ASSIGNMENT_STATE_PATH.
  This is thread-safe and process-safe for single-server deployments.

Tradeoffs:
  - Tradeoff 1 (Completer Parity vs. Differential Attrition Exposure):
    Guaranteeing equal completers across cells means that if one cell has higher
    dropout (e.g. manipulative UI pressure causes more dropouts), more total
    participants will be exposed to that cell to achieve the target completer count.
    Researchers must report both started (assigned) and completed counts per cell
    to check for selective attrition bias.
  - Tradeoff 2 (In-Flight Timeout Window):
    A 30-minute timeout is generous for a 3-5 minute study. During that window,
    an abandoned participant still temporarily reserves a slot. If a participant
    resumes after 25 minutes, their slot is preserved. If they abandon, the slot
    re-opens after 30 minutes.
  - Tradeoff 3 (Multi-Server Deployment):
    The OS file lock works across processes on a single host. If scaled across
    multiple container instances/machines, replace the JSON lock with a Redis
    counter or PostgreSQL row-level lock (e.g. SELECT FOR UPDATE).
"""
import json
import os
import random
import sys
import time

# Windows vs POSIX file locking
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

from config import ASSIGNMENT_STATE_PATH

CELLS = [
    ("neutral",       "0pct"),
    ("neutral",       "35pct"),
    ("manipulative",  "0pct"),
    ("manipulative",  "35pct"),
]

CELL_KEYS = [f"{ui}_{rew}" for ui, rew in CELLS]

# Single-sitting study takes 3-5 minutes; 30 minutes timeout for in-flight abandonment
IN_FLIGHT_TIMEOUT_SECS = 1800


def _default_state():
    return {
        "completers": {k: 0 for k in CELL_KEYS},
        "in_flight": {},  # participant_code -> {"cell": [ui, rew], "assigned_at": ts}
    }


def _load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all keys exist
                if "completers" not in data:
                    data["completers"] = {k: 0 for k in CELL_KEYS}
                for k in CELL_KEYS:
                    data["completers"].setdefault(k, 0)
                if "in_flight" not in data:
                    data["in_flight"] = {}
                return data
        except Exception:
            return _default_state()
    return _default_state()


def _save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _prune_expired_in_flight(state, now):
    """Remove in-flight participants who exceeded the timeout."""
    in_flight = state.get("in_flight", {})
    expired = [
        code for code, info in in_flight.items()
        if (now - info.get("assigned_at", 0)) > IN_FLIGHT_TIMEOUT_SECS
    ]
    for code in expired:
        del in_flight[code]


def assign_participant(participant_code: str = None) -> tuple:
    """
    Assign participant to the cell with the minimum effective load:
      effective = completers + active_in_flight
    Ties broken uniformly at random.
    Returns (ui_condition, reward_condition).
    """
    lock_path = ASSIGNMENT_STATE_PATH + ".lock"
    now = time.time()

    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            state = _load_state(ASSIGNMENT_STATE_PATH)
            _prune_expired_in_flight(state, now)

            # If participant already has an in-flight assignment, return it (idempotent)
            if participant_code and participant_code in state.get("in_flight", {}):
                stored_cell = state["in_flight"][participant_code]["cell"]
                return tuple(stored_cell)

            # Count active in-flight per cell
            active_counts = {k: 0 for k in CELL_KEYS}
            for info in state.get("in_flight", {}).values():
                cell_tuple = tuple(info.get("cell", []))
                if len(cell_tuple) == 2:
                    k = f"{cell_tuple[0]}_{cell_tuple[1]}"
                    active_counts[k] = active_counts.get(k, 0) + 1

            # Effective count = completed + in_flight
            completers = state.get("completers", {})
            effective_counts = {
                k: completers.get(k, 0) + active_counts.get(k, 0)
                for k in CELL_KEYS
            }

            # Find cell(s) with minimum effective count
            min_count = min(effective_counts.values())
            candidate_keys = [k for k, v in effective_counts.items() if v == min_count]

            # Break ties uniformly at random
            chosen_key = random.choice(candidate_keys)
            ui, rew = chosen_key.split("_", 1)
            chosen_cell = (ui, rew)

            # Record in-flight
            if participant_code:
                state["in_flight"][participant_code] = {
                    "cell": [ui, rew],
                    "assigned_at": now,
                }

            _save_state(ASSIGNMENT_STATE_PATH, state)
        finally:
            _unlock(lf)

    return chosen_cell


def record_completion(participant_code: str, ui_condition: str, reward_condition: str):
    """
    Record that a participant successfully completed the study.
    Increments completers count and releases their in-flight reservation.
    """
    lock_path = ASSIGNMENT_STATE_PATH + ".lock"
    cell_key = f"{ui_condition}_{reward_condition}"
    if cell_key not in CELL_KEYS:
        return

    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            state = _load_state(ASSIGNMENT_STATE_PATH)
            state["completers"][cell_key] = state["completers"].get(cell_key, 0) + 1
            if participant_code and participant_code in state.get("in_flight", {}):
                del state["in_flight"][participant_code]
            _save_state(ASSIGNMENT_STATE_PATH, state)
        finally:
            _unlock(lf)


def record_abandonment(participant_code: str):
    """
    Explicitly release in-flight slot if participant exits early (e.g. content warning, quiz fail).
    """
    if not participant_code:
        return
    lock_path = ASSIGNMENT_STATE_PATH + ".lock"
    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            state = _load_state(ASSIGNMENT_STATE_PATH)
            if participant_code in state.get("in_flight", {}):
                del state["in_flight"][participant_code]
                _save_state(ASSIGNMENT_STATE_PATH, state)
        finally:
            _unlock(lf)


def get_assignment_summary() -> dict:
    """Return snapshot of completers and in-flight counts for reporting."""
    lock_path = ASSIGNMENT_STATE_PATH + ".lock"
    now = time.time()
    with open(lock_path, "w") as lf:
        _lock(lf)
        try:
            state = _load_state(ASSIGNMENT_STATE_PATH)
            _prune_expired_in_flight(state, now)
            completers = dict(state.get("completers", {}))
            in_flight = dict(state.get("in_flight", {}))
            _save_state(ASSIGNMENT_STATE_PATH, state)
        finally:
            _unlock(lf)

    active_counts = {k: 0 for k in CELL_KEYS}
    for info in in_flight.values():
        c = tuple(info.get("cell", []))
        if len(c) == 2:
            k = f"{c[0]}_{c[1]}"
            active_counts[k] = active_counts.get(k, 0) + 1

    return {
        "completers": completers,
        "active_in_flight": active_counts,
        "effective": {k: completers.get(k, 0) + active_counts.get(k, 0) for k in CELL_KEYS},
        "total_completed": sum(completers.values()),
        "total_in_flight": len(in_flight),
    }
