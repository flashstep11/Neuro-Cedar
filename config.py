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
# Withdrawal fee ladder and reinvestment cap  (v2 design, see PROTOCOL_CHANGES.md)
# ---------------------------------------------------------------------------
F1 = 200                         # step 1: withdrawal processing fee (Rs)
F2 = 150                         # step 2: account verification fee (Rs), only if F1 paid
# Chosen with simulator/payoff_simulator_v2.py (output_v2.txt). Retune after pilot.

# Total cap across BOTH reinvestment rounds = 900 - F1 - F2 = 550, so both fees
# are always affordable from cash. Derived in logic.ledger; never hardcode it.
STEP = 50                        # reinvestment dropdown step (Rs)

# Manipulative arm only: non-binding "account freeze" countdown on the step-2
# fee screen. This is a SECOND countdown (protocol change from "one timer");
# set False to remove it if ethics/instructor require a single timer.
FREEZE_TIMER_ENABLED = True
FREEZE_TIMER_SECS    = 60

# ---------------------------------------------------------------------------
# Active pool — PILOT, NOT FROZEN
# Candidate C is the guide's named pilot candidate (E[r] = +15%).
# ---------------------------------------------------------------------------
ACTIVE_POOL_KEY = "C_EV15"       # -30% (p=1/4) / +20% (p=1/2) / +50% (p=1/4)
ACTIVE_POOL = CANDIDATES[ACTIVE_POOL_KEY]

# Pre-generated outcome sequence: per cell AND per round, balanced blocks,
# securely shuffled, never replenished (guide section 3). Bump the version
# whenever the pool or length changes; a mismatch refuses to start.
POOL_SEQ_VERSION = "v2-C_EV15-L160"
POOL_SEQ_LENGTH  = 160           # outcomes per (cell, round); multiple of the block size

# Derived range for instructions — pulled from pool, never hardcoded
POOL_MIN_RETURN_PCT = int(min(r for r, _ in ACTIVE_POOL) * 100)   # -30
POOL_MAX_RETURN_PCT = int(max(r for r, _ in ACTIVE_POOL) * 100)   # +50

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
# Lottery opt-out flag (confirmed: True — opt-out treatment active)
# Participants are entered by default with claim token; may opt out.
# ---------------------------------------------------------------------------
LOTTERY_OPT_OUT = True

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Only used by the LOCAL development fallback (SQLite files). In production the
# study state lives in Postgres (see state_store.py), so no disk is needed.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
