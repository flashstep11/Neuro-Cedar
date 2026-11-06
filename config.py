"""
config.py — Single source of truth for all study parameters.
Import this module everywhere; never hardcode these values in pages or templates.

PILOT, NOT FROZEN: pool and all tunable parameters are marked for review
before participant deployment.
"""
import os
from fractions import Fraction as Fr
from logic.growth_pool import CANDIDATES

# ---------------------------------------------------------------------------
# Fee and reinvestment cap
# ---------------------------------------------------------------------------
F = 200                          # withdrawal fee in rupees (tunable)

# From ledger: cap = ENDOWMENT - COMMIT - F = 1000 - 100 - 200 = 700
# r_options(F) gives the full dropdown list; never hardcode the cap here.

STEP = 50                        # reinvestment dropdown step (Rs)

# ---------------------------------------------------------------------------
# Active pool — PILOT, NOT FROZEN
# Swappable: change ACTIVE_POOL_KEY to any key in CANDIDATES.
# ---------------------------------------------------------------------------
ACTIVE_POOL_KEY = "B_EV5"        # candidate B: -30% (p=0.5) / +40% (p=0.5)
ACTIVE_POOL = CANDIDATES[ACTIVE_POOL_KEY]

# Derived range for instructions — pulled from pool, never hardcoded
POOL_MIN_RETURN_PCT = int(min(r for r, _ in ACTIVE_POOL) * 100)   # -30
POOL_MAX_RETURN_PCT = int(max(r for r, _ in ACTIVE_POOL) * 100)   # +40

# ---------------------------------------------------------------------------
# Study parameters
# ---------------------------------------------------------------------------
PLATFORM_NAME = "Cedarline"      # fictional platform name
TIMER_SECS    = 60               # urgency-banner countdown (non-binding)
CONTACT_EMAIL = "flashstep11@gmail.com"

# Reward conditions (guarantee amounts)
REWARD_0  = Fr(0)                # 0% apparent return
REWARD_35 = Fr(35, 100)          # 35% apparent return

# Prize info
PRIZE_COUNT    = 4               # number of unique vouchers
PRIZE_VALUE    = 250             # Rs per voucher
LOTTERY_WEIGHT_DIVISOR = 10      # entries = final_balance / 10

# ---------------------------------------------------------------------------
# Lottery opt-out flag (undecided — keep False until confirmed)
# TODO: confirm opt-out lottery treatment with research team before deployment
# ---------------------------------------------------------------------------
LOTTERY_OPT_OUT = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Separate SQLite for lottery contact data (never in oTree export)
LOTTERY_DB_PATH = os.path.join(BASE_DIR, "lottery_contacts.sqlite3")

# Assignment state file (block-shuffle allocation)
ASSIGNMENT_STATE_PATH = os.path.join(BASE_DIR, "assignment_state.json")

# ---------------------------------------------------------------------------
# Pool sequence seed file (pre-generated per-condition outcomes)
# ---------------------------------------------------------------------------
POOL_SEQ_PATH = os.path.join(BASE_DIR, "pool_sequences.json")

