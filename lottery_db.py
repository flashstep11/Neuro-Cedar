"""
lottery_db.py — lottery contact data, kept apart from the study data.

Contact details live in their own table (lottery_entries) that oTree never
reads, so they can never appear in an oTree data export. Participants are
linked only by a random claim_token (UUID4), not by oTree's participant code
or any internal id. For physical separation set LOTTERY_DATABASE_URL to a
second database (see state_store.py).

  lottery_entries(id, claim_token UNIQUE, name, email, phone, created_at)

Usage:
  token = lottery_db.create_entry()                    # once, store token in Player
  lottery_db.update_contact(token, name, email, phone) # on form submit
"""
import uuid
from datetime import datetime, timezone

import state_store

_DB = "lottery"


def init_db():
    """Create the table if needed. Safe to call repeatedly (and at startup)."""
    state_store.run(lambda tx: None, db=_DB)


def create_entry() -> str:
    """Create a new lottery entry with a fresh random token and return it."""
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    def txn(tx):
        tx.execute("INSERT INTO lottery_entries (claim_token, created_at) VALUES (?, ?)", (token, now))

    state_store.run(txn, db=_DB)
    return token


def update_contact(claim_token: str, name: str, email: str, phone: str):
    """Store contact details for the claim token (idempotent update)."""
    def txn(tx):
        tx.execute("UPDATE lottery_entries SET name = ?, email = ?, phone = ? WHERE claim_token = ?",
                   (name, email, phone, claim_token))

    state_store.run(txn, db=_DB)
