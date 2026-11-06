"""
lottery_db.py — Separate SQLite database for lottery contact data.

This file is intentionally DECOUPLED from oTree's database:
- No Player/Participant/Session fields reference contact data.
- The lottery SQLite file is excluded from oTree's data exports.
- Participants are linked only by a random claim_token (UUID4), not by
  oTree's participant.code or any internal ID.

Schema:
  lottery_entries(
    id           INTEGER PRIMARY KEY,
    claim_token  TEXT UNIQUE NOT NULL,   -- random UUID4, shown to participant
    name         TEXT,
    email        TEXT,
    phone        TEXT,
    created_at   TEXT                    -- ISO-8601 UTC timestamp
  )

Usage:
  token = lottery_db.create_entry()          # call once, store token in Player
  lottery_db.update_contact(token, name, email, phone)  # call on form submit
"""
import sqlite3
import uuid
from datetime import datetime, timezone

from config import LOTTERY_DB_PATH


def _conn():
    """Return a connection to the lottery SQLite database."""
    conn = sqlite3.connect(LOTTERY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the table if it doesn't exist. Call once at app startup."""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lottery_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_token TEXT UNIQUE NOT NULL,
                name        TEXT,
                email       TEXT,
                phone       TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()


def create_entry() -> str:
    """
    Create a new lottery entry with a fresh random token.
    Returns the claim_token string.
    """
    token = str(uuid.uuid4())
    now   = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO lottery_entries (claim_token, created_at) VALUES (?, ?)",
            (token, now)
        )
        conn.commit()
    return token


def update_contact(claim_token: str, name: str, email: str, phone: str):
    """
    Store contact details for the given claim_token.
    Safe to call multiple times (idempotent update).
    """
    with _conn() as conn:
        conn.execute(
            """UPDATE lottery_entries
               SET name=?, email=?, phone=?
               WHERE claim_token=?""",
            (name, email, phone, claim_token)
        )
        conn.commit()

