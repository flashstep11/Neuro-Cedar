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

DEMO_PAGE_INTRO_HTML = ""

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
