"""
state_store.py — durable runtime state in a real database (no files, no disk).

Holds what used to live in JSON/SQLite files next to the code:
  * assignment counts (completer-balanced allocation)
  * the pre-generated pool outcome sequence
  * lottery contact entries (kept in their OWN table, never read by oTree's export)

Backends
  Postgres  chosen when the URL starts with postgres:// or postgresql://
            (use any provider: Render, Neon, Supabase, a college server...)
  SQLite    local-development fallback, a file inside DATA_DIR

Which URL is used
  STATE_DATABASE_URL    for assignment + pool sequence   (default: DATABASE_URL if it is Postgres)
  LOTTERY_DATABASE_URL  for lottery contacts             (default: same as the state database)
  Set LOTTERY_DATABASE_URL to a second database for *physical* separation of contact data.

Atomicity
  Every read-modify-write runs in one transaction that locks the row
  (Postgres: SELECT ... FOR UPDATE; SQLite: BEGIN IMMEDIATE). Concurrent
  participants therefore cannot overwrite each other or draw the same outcome.

Resilience
  Each transaction opens its own connection, and a dropped connection (e.g. a
  free-tier database waking from sleep) is retried once. Errors are never
  swallowed: a failure raises instead of silently resetting study state.
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from config import DATA_DIR

_RETRIES = 3
_init_done = set()
_init_lock = threading.Lock()


def _is_pg(url):
    return bool(url) and url.split(":", 1)[0] in ("postgres", "postgresql")


def _norm_pg(url):
    # SQLAlchemy 2 and psycopg2 both want postgresql://, some hosts hand out postgres://
    return "postgresql://" + url.split("://", 1)[1] if url.startswith("postgres://") else url


def resolve(db="state"):
    """Return ('pg', url) or ('sqlite', path) for the 'state' or 'lottery' store."""
    state_url = os.environ.get("STATE_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if db == "lottery":
        url = os.environ.get("LOTTERY_DATABASE_URL") or state_url
        if _is_pg(url):
            return "pg", _norm_pg(url)
        return "sqlite", os.path.join(DATA_DIR, "lottery_contacts.sqlite3")
    if _is_pg(state_url):
        return "pg", _norm_pg(state_url)
    return "sqlite", os.path.join(DATA_DIR, "cl_state.sqlite3")


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cl_state (
           key   TEXT PRIMARY KEY,
           value TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS lottery_entries (
           id          {serial},
           claim_token TEXT UNIQUE NOT NULL,
           name        TEXT,
           email       TEXT,
           phone       TEXT,
           created_at  TEXT NOT NULL)""",
]


class Tx:
    """One open transaction. SQL uses ? placeholders on both backends."""

    def __init__(self, kind, conn):
        self.kind, self.conn = kind, conn
        self.cur = conn.cursor()

    def execute(self, sql, params=()):
        if self.kind == "pg":
            sql = sql.replace("?", "%s")
        self.cur.execute(sql, params)
        return self.cur

    def lock_get(self, key, default):
        """Return the JSON value for `key` with its row locked until commit.
        Creates the row from `default` if it does not exist yet."""
        ins = ("INSERT INTO cl_state (key, value) VALUES (?, ?) ON CONFLICT (key) DO NOTHING"
               if self.kind == "pg" else
               "INSERT OR IGNORE INTO cl_state (key, value) VALUES (?, ?)")
        self.execute(ins, (key, json.dumps(default)))
        sel = "SELECT value FROM cl_state WHERE key = ?" + (" FOR UPDATE" if self.kind == "pg" else "")
        return json.loads(self.execute(sel, (key,)).fetchone()[0])

    def put(self, key, value):
        self.execute("UPDATE cl_state SET value = ? WHERE key = ?", (json.dumps(value), key))


def _connect(kind, target):
    if kind == "pg":
        import psycopg2
        conn = psycopg2.connect(target, connect_timeout=15)
        conn.autocommit = False
        return conn
    conn = sqlite3.connect(target, timeout=30, isolation_level=None)   # we manage transactions
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(kind, target):
    if (kind, target) in _init_done:
        return
    with _init_lock:
        if (kind, target) in _init_done:
            return
        serial = "SERIAL PRIMARY KEY" if kind == "pg" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        conn = _connect(kind, target)
        try:
            cur = conn.cursor()
            for ddl in SCHEMA:
                cur.execute(ddl.format(serial=serial))
            if kind == "pg":
                conn.commit()
        finally:
            conn.close()
        _init_done.add((kind, target))


def _is_transient(kind, exc):
    if kind == "pg":
        import psycopg2
        return isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError))
    return isinstance(exc, sqlite3.OperationalError)


@contextmanager
def _one_transaction(kind, target):
    conn = _connect(kind, target)
    try:
        if kind == "sqlite":
            conn.execute("BEGIN IMMEDIATE")
        tx = Tx(kind, conn)
        yield tx
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run(fn, db="state"):
    """
    Run fn(tx) in one transaction and return its result. Retries the WHOLE
    function on a dropped connection (so fn must be safe to re-run: it only
    touches the database through tx).
    """
    kind, target = resolve(db)
    last = None
    for attempt in range(_RETRIES):
        try:
            _ensure_schema(kind, target)
            with _one_transaction(kind, target) as tx:
                return fn(tx)
        except Exception as exc:
            if not _is_transient(kind, exc):
                raise
            last = exc
            time.sleep(0.4 * (attempt + 1))        # database waking up / brief outage
    raise last


def describe(db="state"):
    """Human-readable, secret-free description of the backend in use."""
    kind, target = resolve(db)
    if kind == "pg":
        host = target.split("@", 1)[-1].split("/", 1)[0]
        return f"postgres ({host})"
    return f"sqlite ({os.path.basename(target)})"
