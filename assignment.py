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
  State lives in the database (state_store.py). Every read-modify-write is one
  transaction with the state row locked (SELECT ... FOR UPDATE on Postgres,
  BEGIN IMMEDIATE on SQLite), so concurrent arrivals cannot overwrite each other
  and the state survives restarts, redeploys and ephemeral hosts.

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
    Row locking in the shared database is safe across processes and machines.
"""
import random
import time

import state_store

CELLS = [
    ("neutral",       "0pct"),
    ("neutral",       "35pct"),
    ("manipulative",  "0pct"),
    ("manipulative",  "35pct"),
]

CELL_KEYS = [f"{ui}_{rew}" for ui, rew in CELLS]

STATE_KEY = "assignment"

# Single-sitting study takes ~10 minutes; 30 minutes timeout for in-flight abandonment
IN_FLIGHT_TIMEOUT_SECS = 1800


def _default_state():
    return {
        "completers": {k: 0 for k in CELL_KEYS},
        "in_flight": {},  # participant_code -> {"cell": [ui, rew], "assigned_at": ts}
    }


def _normalize(state):
    """Make sure every expected key exists (never replaces a corrupt state silently)."""
    state.setdefault("completers", {})
    for k in CELL_KEYS:
        state["completers"].setdefault(k, 0)
    state.setdefault("in_flight", {})
    return state


def _load_locked(tx):
    return _normalize(tx.lock_get(STATE_KEY, _default_state()))


def _prune_expired_in_flight(state, now):
    """Remove in-flight participants who exceeded the timeout."""
    in_flight = state.get("in_flight", {})
    expired = [
        code for code, info in in_flight.items()
        if (now - info.get("assigned_at", 0)) > IN_FLIGHT_TIMEOUT_SECS
    ]
    for code in expired:
        del in_flight[code]


def _active_counts(state):
    counts = {k: 0 for k in CELL_KEYS}
    for info in state.get("in_flight", {}).values():
        cell = tuple(info.get("cell", []))
        if len(cell) == 2:
            k = f"{cell[0]}_{cell[1]}"
            counts[k] = counts.get(k, 0) + 1
    return counts


def assign_participant(participant_code: str = None) -> tuple:
    """
    Assign participant to the cell with the minimum effective load:
      effective = completers + active_in_flight
    Ties broken uniformly at random.
    Returns (ui_condition, reward_condition). Idempotent per participant code.
    """
    now = time.time()

    def txn(tx):
        state = _load_locked(tx)
        _prune_expired_in_flight(state, now)

        # Already has an in-flight assignment -> return it (idempotent)
        if participant_code and participant_code in state["in_flight"]:
            tx.put(STATE_KEY, state)
            return tuple(state["in_flight"][participant_code]["cell"])

        active = _active_counts(state)
        completers = state["completers"]
        effective = {k: completers.get(k, 0) + active.get(k, 0) for k in CELL_KEYS}

        min_count = min(effective.values())
        chosen_key = random.choice([k for k, v in effective.items() if v == min_count])
        ui, rew = chosen_key.split("_", 1)

        if participant_code:
            state["in_flight"][participant_code] = {"cell": [ui, rew], "assigned_at": now}
        tx.put(STATE_KEY, state)
        return (ui, rew)

    return state_store.run(txn)


def record_completion(participant_code: str, ui_condition: str, reward_condition: str):
    """
    Record that a participant successfully completed the study.
    Increments completers count and releases their in-flight reservation.
    Idempotent per participant: a participant is only counted once.
    """
    cell_key = f"{ui_condition}_{reward_condition}"
    if cell_key not in CELL_KEYS:
        return

    def txn(tx):
        state = _load_locked(tx)
        counted = state.setdefault("counted", [])
        if participant_code and participant_code in counted:
            return                                  # refresh of the debrief page
        state["completers"][cell_key] = state["completers"].get(cell_key, 0) + 1
        if participant_code:
            counted.append(participant_code)
            state["in_flight"].pop(participant_code, None)
        tx.put(STATE_KEY, state)

    state_store.run(txn)


def record_abandonment(participant_code: str):
    """Release the in-flight slot if a participant exits early (content warning, quiz fail)."""
    if not participant_code:
        return

    def txn(tx):
        state = _load_locked(tx)
        if participant_code in state["in_flight"]:
            del state["in_flight"][participant_code]
            tx.put(STATE_KEY, state)

    state_store.run(txn)


def get_assignment_summary() -> dict:
    """Return snapshot of completers and in-flight counts for reporting."""
    now = time.time()

    def txn(tx):
        state = _load_locked(tx)
        _prune_expired_in_flight(state, now)
        tx.put(STATE_KEY, state)
        return state

    state = state_store.run(txn)
    completers = dict(state["completers"])
    active = _active_counts(state)
    return {
        "completers": completers,
        "active_in_flight": active,
        "effective": {k: completers.get(k, 0) + active.get(k, 0) for k in CELL_KEYS},
        "total_completed": sum(completers.values()),
        "total_in_flight": len(state["in_flight"]),
    }
