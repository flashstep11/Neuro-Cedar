"""
settings.py — oTree v5 project settings for the Cedarline study.

Production notes:
  - Set OTREE_PRODUCTION=1 in the environment.
  - Set OTREE_ADMIN_PASSWORD and OTREE_AUTH_LEVEL.
  - Set DATABASE_URL=postgresql://... (Postgres required on ephemeral hosts).
  - The lottery SQLite file (lottery_contacts.sqlite3) needs a persistent
    volume; it is NOT managed by this DATABASE_URL.
  - Run with a SINGLE Uvicorn worker; the file-lock assignment strategy
    is not safe across multiple machines. See assignment.py for details.
"""
import os
import sys

# Make logic/ and simulator/ importable from anywhere in the project
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Session configs
# ---------------------------------------------------------------------------
SESSION_CONFIGS = [
    # --- MAIN study session (real, balanced assignment) ---
    {
        "name":         "cedarline_main",
        "display_name": "Cedarline Study (balanced assignment)",
        "app_sequence": ["cedarline"],
        "num_demo_participants": 4,
    },
]

# ---------------------------------------------------------------------------
# DEV-ONLY forced-cell configs
# These are appended ONLY when OTREE_PRODUCTION is not set, so they never
# appear in production. Each forces a specific (ui, reward) cell for QA.
# ---------------------------------------------------------------------------
if os.environ.get("OTREE_PRODUCTION") != "1":
    SESSION_CONFIGS += [
        {
            "name":         "dev_neutral_0pct",
            "display_name": "[DEV] Neutral UI / 0% reward",
            "app_sequence": ["cedarline"],
            "num_demo_participants": 1,
            # Passed through to the app as session.config
            "force_ui":     "neutral",
            "force_reward": "0pct",
        },
        {
            "name":         "dev_neutral_35pct",
            "display_name": "[DEV] Neutral UI / 35% reward",
            "app_sequence": ["cedarline"],
            "num_demo_participants": 1,
            "force_ui":     "neutral",
            "force_reward": "35pct",
        },
        {
            "name":         "dev_manip_0pct",
            "display_name": "[DEV] Manipulative UI / 0% reward",
            "app_sequence": ["cedarline"],
            "num_demo_participants": 1,
            "force_ui":     "manipulative",
            "force_reward": "0pct",
        },
        {
            "name":         "dev_manip_35pct",
            "display_name": "[DEV] Manipulative UI / 35% reward",
            "app_sequence": ["cedarline"],
            "num_demo_participants": 1,
            "force_ui":     "manipulative",
            "force_reward": "35pct",
        },
    ]

# ---------------------------------------------------------------------------
# oTree standard settings
# ---------------------------------------------------------------------------
SESSION_CONFIG_DEFAULTS = {
    "real_world_currency_per_point": 0,
    "participation_fee":             0,
    # No forced cell by default (balanced assignment is used)
    "force_ui":     None,
    "force_reward": None,
}

LANGUAGE_CODE = "en"
REAL_WORLD_CURRENCY_CODE = "INR"
USE_POINTS = False

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = os.environ.get("OTREE_ADMIN_PASSWORD", "changeme_before_deploy")

SECRET_KEY = os.environ.get("OTREE_SECRET_KEY", "dev-secret-key-change-in-production")

# Refuse to start a production server with placeholder credentials, or on a
# host that wipes its disk without a real database configured.
if os.environ.get("OTREE_PRODUCTION") == "1":
    _missing = [k for k in ("OTREE_ADMIN_PASSWORD", "OTREE_SECRET_KEY") if not os.environ.get(k)]
    if _missing:
        raise RuntimeError(f"Production start blocked; set these env vars: {', '.join(_missing)}")
    if os.environ.get("RENDER") and not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL (a Postgres URL) is required on Render: its disk is wiped on "
                           "every restart, so SQLite files would silently lose study data.")

# Free-tier Postgres hosts put idle databases to sleep (Neon after 5 minutes) and
# drop every open connection. oTree keeps ONE long-lived connection, so without
# this the first participant after a quiet period would get a server error.
# Documented SQLAlchemy "pessimistic" recipe: ping on checkout, and on failure
# discard the dead connection and reconnect transparently. Class-level, so it
# applies to every engine in every oTree process regardless of import order.
try:
    from sqlalchemy import event as _sa_event, exc as _sa_exc
    from sqlalchemy.pool import Pool as _SaPool

    @_sa_event.listens_for(_SaPool, "checkout")
    def _cl_ping_on_checkout(dbapi_con, con_record, con_proxy):
        if not type(dbapi_con).__module__.startswith("psycopg2"):
            return                                   # SQLite etc.: nothing to do
        cur = dbapi_con.cursor()
        try:
            cur.execute("SELECT 1")
        except dbapi_con.Error:
            raise _sa_exc.DisconnectionError()       # pool reconnects and retries the checkout
        finally:
            try:
                cur.close()
            except Exception:
                pass
except ImportError:                                  # SQLAlchemy not installed yet (e.g. a bare import)
    pass

# Some hosts hand out postgres://; SQLAlchemy 2 only accepts postgresql://.
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = "postgresql://" + _db_url.split("://", 1)[1]

# Database: Postgres in production via DATABASE_URL env var; SQLite in dev.
# oTree v5 picks this up automatically.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(PROJECT_ROOT, 'db.sqlite3')}"
)

# Static files served from _static/ at the project root
STATICFILES_DIRS = [
    os.path.join(PROJECT_ROOT, "_static"),
]
