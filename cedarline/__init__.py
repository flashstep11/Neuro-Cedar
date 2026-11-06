"""
cedarline/__init__.py
oTree v5 single-file app for the Cedarline study.

Money math: ALL monetary computations go through logic.ledger (exact Fractions).
Amounts stored in oTree fields are converted to int/float ONLY at the boundary
(field assignment). Templates receive pre-converted integers; no arithmetic
is done in templates or pages.
"""
import os
import sys
import json
import time
from fractions import Fraction as Fr
from datetime import datetime, timezone

import otree.api as o

# Ensure project root is on sys.path (settings.py also does this, but be safe)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from logic import ledger
from config import (
    F, STEP, PLATFORM_NAME, TIMER_SECS, CONTACT_EMAIL,
    POOL_MIN_RETURN_PCT, POOL_MAX_RETURN_PCT,
    REWARD_0, REWARD_35,
    PRIZE_COUNT, PRIZE_VALUE, LOTTERY_WEIGHT_DIVISOR,
    LOTTERY_OPT_OUT,
)
from assignment import (
    assign_participant,
    record_completion,
    record_abandonment,
    get_assignment_summary,
)
from pool_sequence import draw_pool_return
import lottery_db

# ---------------------------------------------------------------------------
# Initialise lottery DB at import time (safe to call multiple times)
# ---------------------------------------------------------------------------
lottery_db.init_db()

# ---------------------------------------------------------------------------
# oTree author
# ---------------------------------------------------------------------------
doc = """
Cedarline — Behavioral Sequences in App-Based Investment Frauds
2×2 between-subjects: (Neutral | Manipulative) × (0% | 35% apparent return)
"""

# ===========================================================================
# MODELS
# ===========================================================================

class C(o.BaseConstants):
    NAME_IN_URL   = "cedarline"
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS    = 1

    # Study flow constants (from config, re-exposed for template use)
    PLATFORM_NAME = PLATFORM_NAME
    TIMER_SECS    = TIMER_SECS
    CONTACT_EMAIL = CONTACT_EMAIL
    PRIZE_COUNT   = PRIZE_COUNT
    PRIZE_VALUE   = PRIZE_VALUE
    F             = F
    ENDOWMENT     = int(ledger.ENDOWMENT)
    COMMIT        = int(ledger.COMMIT)
    CAP           = int(ledger.cap(F))
    STEP          = STEP
    POOL_MIN_PCT  = POOL_MIN_RETURN_PCT   # -30
    POOL_MAX_PCT  = POOL_MAX_RETURN_PCT   # +40
    LOTTERY_WEIGHT_DIVISOR = LOTTERY_WEIGHT_DIVISOR

    # Reinvestment options as list of ints (for dropdown)
    R_OPTIONS = [int(r) for r in ledger.r_options(F)]

    # Quiz answers (fixed correct answers)
    QUIZ_CORRECT = {
        "q_initial":  "100",
        "q_max_r":    str(int(ledger.cap(F))),
        "q_can_fall": "yes",
        "q_lottery":  "balance",
    }


class Subsession(o.BaseSubsession):
    def vars_for_admin_report(self):
        return vars_for_admin_report(self)


class Group(o.BaseGroup):
    pass


_m = o.models   # shorthand for model field definitions

class Player(o.BasePlayer):
    # --- Assignment ---
    ui_condition     = _m.StringField(initial="")     # "neutral" | "manipulative"
    reward_condition = _m.StringField(initial="")     # "0pct" | "35pct"
    assigned         = _m.BooleanField(initial=False) # set once, never changed

    # --- Exit codes ---
    exit_code = _m.StringField(blank=True, initial="")
    # Possible values:
    #   "left_at_content_warning"
    #   "quiz_failed_twice"
    #   "" (completed normally)

    # --- Quiz ---
    quiz_attempts = _m.IntegerField(initial=0)

    # --- Investment stages ---
    reinvest_amount  = _m.IntegerField(blank=True)   # R in Rs (S4 choice)
    pool_return_num  = _m.IntegerField(blank=True)   # numerator of pool Fraction
    pool_return_den  = _m.IntegerField(initial=1)    # denominator

    # Computed at S8
    platform_balance_decision = _m.IntegerField(blank=True)  # P at decision point
    final_balance_int         = _m.IntegerField(blank=True)  # final balance Rs
    pay_decision              = _m.BooleanField(blank=True)  # True=pay, False=abandon
    # pay_decision_str is the form submission vehicle ("pay" or "abandon");
    # converted to pay_decision in S8.before_next_page. Keeps BooleanField off forms.
    pay_decision_str          = _m.StringField(blank=True)
    outcome_flag              = _m.StringField(blank=True)   # ledger.classify() result
    lottery_weight            = _m.FloatField(blank=True)    # final_balance / 10

    # --- Timestamps ---
    timer_deadline_ts     = _m.FloatField(blank=True)  # unix ts, set once at S4 render
    s4_first_render_ts    = _m.FloatField(blank=True)
    s6_withdraw_click_ts  = _m.FloatField(blank=True)

    # S4 interaction log: JSON list of {event, amount, ts}
    s4_event_log = _m.LongStringField(blank=True, initial="[]")

    # --- Questionnaire ---
    q_trust        = _m.IntegerField(blank=True, min=1, max=7)
    q_legitimacy   = _m.IntegerField(blank=True, min=1, max=7)
    q_risk         = _m.IntegerField(blank=True, min=1, max=7)
    q_confidence   = _m.IntegerField(blank=True, min=1, max=7)
    q_reward_noticed = _m.StringField(blank=True)   # "yes"/"no"
    q_ui_noticed     = _m.StringField(blank=True)   # "yes"/"no"
    q_attention      = _m.IntegerField(blank=True, min=1, max=7)  # fixed answer check
    q_suspicion      = _m.LongStringField(blank=True)   # free text

    # --- Lottery ---
    claim_token = _m.StringField(blank=True)   # UUID linking to lottery_contacts.sqlite3
    # NOTE: No PII fields here — contact data lives in lottery_db only.

    # --- Completion & Incomplete Session Tracking ---
    is_completed      = _m.BooleanField(initial=False)
    stage_reached     = _m.StringField(initial="ContentWarning")
    stage_reached_ts  = _m.FloatField(blank=True)
    completion_ts     = _m.FloatField(blank=True)


# ===========================================================================
# HELPERS (used by multiple pages)
# ===========================================================================

def _now_ts():
    """Current UTC unix timestamp as float."""
    return time.time()


def _mark_stage(player, stage_name: str):
    """Record progression stage and timestamp for incomplete session auditing."""
    player.stage_reached = stage_name
    player.stage_reached_ts = _now_ts()


def _reward_fraction(player) -> Fr:
    """Return the reward Fraction (g) for this player's condition."""
    return REWARD_35 if player.reward_condition == "35pct" else REWARD_0


def _pool_return_fraction(player) -> Fr:
    """Return the pool return Fraction (r) stored for this player."""
    num = player.field_maybe_none('pool_return_num')
    den = player.field_maybe_none('pool_return_den') or 1
    if num is None:
        return Fr(0)
    return Fr(num, den)


def _r_options_display():
    """List of int reinvestment options for template dropdowns."""
    return C.R_OPTIONS


def _ensure_assigned(player):
    """
    Assign the participant to a cell exactly once (idempotent).
    Checks session.config for forced cell (dev-only configs).
    Passes participant code to support completers-based balancing.
    """
    if player.assigned:
        return
    cfg = player.session.config
    force_ui     = cfg.get("force_ui")
    force_reward = cfg.get("force_reward")

    if force_ui and force_reward:
        # DEV-ONLY forced cell; real assignment logic is untouched
        ui, reward = force_ui, force_reward
    else:
        ui, reward = assign_participant(player.participant.code)

    player.ui_condition     = ui
    player.reward_condition = reward
    player.assigned         = True


def _compute_and_store_final(player, pay: bool):
    """
    Compute final balance and flags using ledger; store in Player fields.
    Call once at S8; idempotent (re-calling with same pay won't change stored values).
    """
    if player.field_maybe_none('final_balance_int') is not None:
        return  # already computed

    g = _reward_fraction(player)
    R = player.field_maybe_none('reinvest_amount') or 0
    r = _pool_return_fraction(player)

    P   = ledger.platform_balance(g, R, r)
    fb  = ledger.final_balance(g, R, r, F, pay)
    flg = ledger.classify(g, R, r, F, pay)
    wt  = float(fb) / LOTTERY_WEIGHT_DIVISOR

    player.platform_balance_decision = int(P)
    player.final_balance_int         = int(fb)
    player.pay_decision              = pay
    player.outcome_flag              = flg
    player.lottery_weight            = max(0.0, wt)   # clamp to 0 if negative


# ===========================================================================
# PAGES — Pre-assignment (Neutral styling for everyone)
# ===========================================================================

class ContentWarning(o.Page):
    """
    Step 1: Content warning page.
    Records 'left_at_content_warning' exit code if participant opts out.
    exit_code is set via a hidden form field — blank if they continue,
    'left_at_content_warning' if they exit.
    """
    form_model  = "player"
    form_fields = ["exit_code"]

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "ContentWarning")
        return {
            "platform_name": C.PLATFORM_NAME,
        }

    @staticmethod
    def before_next_page(player, timeout_happened):
        if player.exit_code == "left_at_content_warning":
            player.stage_reached = "ExitContentWarning"
            player.stage_reached_ts = _now_ts()
            record_abandonment(player.participant.code)


class Instructions(o.Page):
    """
    Step 2: Study instructions and lottery explanation.
    Min/max pool returns pulled from config (never hardcoded).
    """
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "Instructions")
        return {
            "platform_name":  C.PLATFORM_NAME,
            "initial_invest": C.COMMIT,
            "max_reinvest":   C.CAP,
            "pool_min_pct":   C.POOL_MIN_PCT,   # -30
            "pool_max_pct":   C.POOL_MAX_PCT,   # +40
            "prize_count":    C.PRIZE_COUNT,
            "prize_value":    C.PRIZE_VALUE,
            "lottery_div":    C.LOTTERY_WEIGHT_DIVISOR,
        }


class Consent(o.Page):
    """
    Step 3: Informed consent.
    Participant answers two Yes/No questions (18+; agree to participate).
    """
    form_model  = "player"
    form_fields = []   # No player fields; consent is tracked via page advance

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "Consent")
        return {
            "platform_name": C.PLATFORM_NAME,
            "contact_email": C.CONTACT_EMAIL,
        }


class ComprehensionQuiz(o.Page):
    """
    Step 4: Comprehension quiz (4 items, 2 attempts).
    If the participant fails twice, exit_code is set and they are
    forwarded to QuizFailed page before assignment.
    """
    form_model  = "player"
    form_fields = []   # Quiz handled via live_method

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "ComprehensionQuiz")
        return {
            "platform_name": C.PLATFORM_NAME,
            "max_reinvest":  C.CAP,
            "pool_min_pct":  C.POOL_MIN_PCT,
            "pool_max_pct":  C.POOL_MAX_PCT,
            "quiz_attempts": player.quiz_attempts,
        }

    @staticmethod
    def live_method(player, data):
        """
        Handle quiz submission via live websocket.
        data = {"q_initial": "...", "q_max_r": "...", "q_can_fall": "...", "q_lottery": "..."}
        Returns feedback dict.
        """
        if data.get("action") != "submit_quiz":
            return

        player.quiz_attempts += 1
        correct = C.QUIZ_CORRECT
        results = {}
        all_correct = True

        for key, expected in correct.items():
            given = str(data.get(key, "")).strip()
            is_ok = (given == expected)
            results[key] = is_ok
            if not is_ok:
                all_correct = False

        if all_correct:
            return {player.id_in_group: {"status": "pass"}}

        if player.quiz_attempts >= 2:
            player.exit_code = "quiz_failed_twice"
            player.stage_reached = "QuizFailedTwice"
            player.stage_reached_ts = _now_ts()
            record_abandonment(player.participant.code)
            return {player.id_in_group: {"status": "fail_final", "results": results}}

        return {player.id_in_group: {"status": "fail_retry", "results": results}}

    @staticmethod
    def is_displayed(player):
        # Skip if already failed (shouldn't happen, but guard)
        return player.exit_code != "quiz_failed_twice"


class QuizFailed(o.Page):
    """Shown to participants who failed the quiz twice. End of study for them."""
    @staticmethod
    def is_displayed(player):
        return player.exit_code == "quiz_failed_twice"

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "QuizFailed")
        return {
            "platform_name": C.PLATFORM_NAME,
            "contact_email": C.CONTACT_EMAIL,
        }


class Assignment(o.Page):
    """
    Step 5: Concealed assignment page (shows a brief loading/redirect message).
    Assignment is idempotent — refreshing never re-assigns.
    """
    @staticmethod
    def before_next_page(player, timeout_happened):
        _ensure_assigned(player)

    @staticmethod
    def is_displayed(player):
        # Skip if exited at content warning or quiz failed
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "Assignment")
        return {"platform_name": C.PLATFORM_NAME}
        return {"platform_name": C.PLATFORM_NAME}


# ===========================================================================
# PAGES — Investment stages (Neutral or Manipulative based on ui_condition)
# ===========================================================================

class _InvestBase(o.Page):
    """Base for investment stage pages — shared helper for cue rendering."""
    @staticmethod
    def _base_vars(player, stage_name: str = None):
        if stage_name:
            _mark_stage(player, stage_name)

        g = _reward_fraction(player)
        R = player.field_maybe_none('reinvest_amount')
        # Compute platform balance for display (uses reward only, not pool)
        # At stages before S5 (pool not yet drawn), show COMMIT * (1+g)
        platform_at_commit = int(ledger.COMMIT * (1 + g))
        cash_now = int(ledger.cash(R)) if R is not None else int(ledger.ENDOWMENT - ledger.COMMIT)

        # Timer: initialise deadline once (for manipulative arm banner).
        # Every render computes remaining from the stored deadline, so
        # refresh never resets the timer.
        now = _now_ts()
        deadline = player.field_maybe_none('timer_deadline_ts')
        if player.ui_condition == "manipulative" and not deadline:
            player.timer_deadline_ts  = now + C.TIMER_SECS
            player.s4_first_render_ts = now
            deadline = player.timer_deadline_ts
        deadline = deadline or (now + C.TIMER_SECS)
        remaining = max(0, int(deadline - now))

        return {
            "platform_name":     C.PLATFORM_NAME,
            "is_manipulative":   player.ui_condition == "manipulative",
            "reward_condition":  player.reward_condition,
            "cash_balance":      cash_now,
            "platform_balance":  platform_at_commit,
            "timer_secs":        C.TIMER_SECS,
            "timer_remaining_secs": remaining,
            "timer_deadline_ts": deadline,
            "endowment":         C.ENDOWMENT,
            "commit":            C.COMMIT,
            "fee":               C.F,
            "cap":               C.CAP,
            "pool_min_pct":      C.POOL_MIN_PCT,
            "pool_max_pct":      C.POOL_MAX_PCT,
        }


class S1Endowment(_InvestBase):
    """S1: Show initial endowment of Rs 1000."""
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S1Endowment")
        v["stage"] = 1
        v["stage_label"] = "Welcome"
        return v


class S2Commitment(_InvestBase):
    """S2: Fixed commitment of Rs 100 to the platform."""
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S2Commitment")
        v["stage"] = 2
        v["stage_label"] = "Initial Investment"
        # After commit: cash = 900 - R (R=0 so far), platform = 100*(1+g)
        g = _reward_fraction(player)
        v["platform_balance"] = int(ledger.COMMIT * (1 + g))
        v["cash_balance"]     = int(ledger.ENDOWMENT - ledger.COMMIT)
        return v

    @staticmethod
    def before_next_page(player, timeout_happened):
        pass


class S3ReturnReveal(_InvestBase):
    """S3: Reveal the return (0% or 35%) on the committed Rs 100."""
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S3ReturnReveal")
        g = _reward_fraction(player)
        platform_val = int(ledger.COMMIT * (1 + g))
        v["stage"]            = 3
        v["stage_label"]      = "Return on Investment"
        v["platform_balance"] = platform_val
        v["cash_balance"]     = int(ledger.ENDOWMENT - ledger.COMMIT)
        v["reward_pct"]       = 35 if player.reward_condition == "35pct" else 0
        return v


class S4Reinvestment(_InvestBase):
    """
    S4: Participant chooses reinvestment amount R.
    Dropdown: blank required, 0 to CAP in steps of STEP.
    Logs: first render, every change, final choice — with server timestamps.
    Timer deadline set once here, server-side.
    """
    form_model  = "player"
    form_fields = ["reinvest_amount"]

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S4Reinvestment")
        g = _reward_fraction(player)
        v["stage"]        = 4
        v["stage_label"]  = "Reinvestment Decision"
        v["r_options"]    = C.R_OPTIONS
        v["platform_balance"] = int(ledger.COMMIT * (1 + g))
        v["cash_balance"]     = int(ledger.ENDOWMENT - ledger.COMMIT)
        return v

    @staticmethod
    def live_method(player, data):
        """Log S4 interactions (dropdown changes) with server timestamp."""
        action = data.get("action")
        if action in ("change", "first_render", "final_submit"):
            log = json.loads(player.s4_event_log or "[]")
            log.append({
                "event":  action,
                "amount": data.get("amount"),
                "ts":     _now_ts(),
            })
            player.s4_event_log = json.dumps(log)
        return {}

    @staticmethod
    def error_message(player, values):
        if values.get("reinvest_amount") is None:
            return "Please select a reinvestment amount."
        r = values["reinvest_amount"]
        if r not in C.R_OPTIONS:
            return "Please select a valid amount from the list."
        # Invariant: cash >= F at every allowed R
        if int(ledger.cash(r)) < F:
            return "Invalid amount: insufficient cash to cover the withdrawal fee."
        return None

    @staticmethod
    def before_next_page(player, timeout_happened):
        # Draw pool return AFTER R is submitted, exactly once (idempotent).
        # This runs when leaving S4 so S5 can display the outcome.
        if player.field_maybe_none('pool_return_num') is None:
            condition_key = f"{player.ui_condition}_{player.reward_condition}"
            r = draw_pool_return(condition_key)
            player.pool_return_num = r.numerator
            player.pool_return_den = r.denominator


class S5PoolOutcome(_InvestBase):
    """
    S5: Draw pool outcome AFTER R is submitted.
    Idempotent: outcome drawn once and stored; never re-rolled on refresh.
    """
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S5PoolOutcome")
        g = _reward_fraction(player)
        R = player.field_maybe_none('reinvest_amount') or 0

        # Show platform balance including pool outcome if already drawn,
        # else show just the committed amount (shouldn't happen but guard)
        pool_num = player.field_maybe_none('pool_return_num')
        pool_den = player.field_maybe_none('pool_return_den') or 1
        if pool_num is not None:
            r = Fr(pool_num, pool_den)
            P = ledger.platform_balance(g, R, r)
            pct = int(r * 100)
            v["platform_balance"]     = int(P)
            v["pool_return_pct"]      = pct
            v["pool_return_str"]      = f"+{pct}%" if pct >= 0 else f"{pct}%"
        else:
            v["pool_return_pct"]      = 0
            v["pool_return_str"]      = "0%"

        v["stage"]           = 5
        v["stage_label"]     = "Platform Update"
        v["reinvest_amount"] = R
        v["cash_balance"]    = int(ledger.cash(R))
        return v


class S6Withdraw(_InvestBase):
    """S6: Explicit 'Withdraw' click. Logs timestamp."""
    form_model  = "player"
    form_fields = []

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.s6_withdraw_click_ts = _now_ts()

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S6Withdraw")
        g = _reward_fraction(player)
        R = player.field_maybe_none('reinvest_amount') or 0
        r = _pool_return_fraction(player)
        P = ledger.platform_balance(g, R, r)
        v["stage"]            = 6
        v["stage_label"]      = "Withdraw Funds"
        v["platform_balance"] = int(P)
        v["cash_balance"]     = int(ledger.cash(R))
        v["reinvest_amount"]  = R
        return v


class S7FeeDisplay(_InvestBase):
    """S7: Show the withdrawal processing fee (Rs F)."""
    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S7FeeDisplay")
        g = _reward_fraction(player)
        R = player.field_maybe_none('reinvest_amount') or 0
        r = _pool_return_fraction(player)
        P = ledger.platform_balance(g, R, r)
        v["stage"]            = 7
        v["stage_label"]      = "Processing Fee"
        v["platform_balance"] = int(P)
        v["cash_balance"]     = int(ledger.cash(R))
        v["reinvest_amount"]  = R
        v["fee"]              = C.F
        return v


class S8PayAbandon(_InvestBase):
    """
    S8: Pay fee and receive funds, or abandon.
    Computes and stores final balance via ledger. Idempotent.
    Also creates a lottery entry (claim token stored in Player).
    """
    form_model  = "player"
    form_fields = ["pay_decision_str"]

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S8PayAbandon")
        g = _reward_fraction(player)
        R = player.field_maybe_none('reinvest_amount') or 0
        r = _pool_return_fraction(player)
        P = ledger.platform_balance(g, R, r)
        # If pay: final = cash - F + P; If abandon: final = cash
        final_if_pay     = int(ledger.final_balance(g, R, r, F, True))
        final_if_abandon = int(ledger.final_balance(g, R, r, F, False))
        v["stage"]             = 8
        v["stage_label"]       = "Complete Withdrawal"
        v["platform_balance"]  = int(P)
        v["cash_balance"]      = int(ledger.cash(R))
        v["reinvest_amount"]   = R
        v["fee"]               = C.F
        v["final_if_pay"]      = final_if_pay
        v["final_if_abandon"]  = final_if_abandon
        return v

    @staticmethod
    def before_next_page(player, timeout_happened):
        # Convert pay_decision_str ("pay" vs "abandon") to boolean
        pay = (player.pay_decision_str == "pay")
        player.pay_decision = pay
        # Compute final balance using ledger; idempotent
        _compute_and_store_final(player, pay)
        # Create lottery entry if not already done
        if not player.field_maybe_none('claim_token'):
            player.claim_token = lottery_db.create_entry()


# ===========================================================================
# PAGES — Post-task
# ===========================================================================

class PostTask(o.Page):
    """
    Step 7: Post-task questionnaire.
    Trust, legitimacy, risk, confidence (1-7); reward/UI noticed; attention;
    suspicion; financial literacy and DOSPERT placeholders.
    """
    form_model  = "player"
    form_fields = [
        "q_trust", "q_legitimacy", "q_risk", "q_confidence",
        "q_reward_noticed", "q_ui_noticed",
        "q_attention", "q_suspicion",
    ]

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "PostTask")
        perceptions = [
            ("q_trust",      "I trusted the information shown on the platform."),
            ("q_legitimacy", "The platform appeared to be legitimate."),
            ("q_risk",       "I felt the investment was risky."),
            ("q_confidence", "I felt confident in my decisions."),
        ]
        return {
            "platform_name":   C.PLATFORM_NAME,
            "is_manipulative": player.ui_condition == "manipulative",
            "perceptions":     perceptions,
        }


class LotteryContact(o.Page):
    """
    Step 8: Lottery contact form.
    Contact data written directly to lottery_contacts.sqlite3 via lottery_db.
    No PII stored in oTree Player fields.
    """
    @staticmethod
    def is_displayed(player):
        return player.exit_code == "" and not LOTTERY_OPT_OUT
        # TODO: if LOTTERY_OPT_OUT is True, skip this page entirely

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "LotteryContact")
        return {
            "platform_name": C.PLATFORM_NAME,
            "claim_token":   player.field_maybe_none('claim_token') or "",
            "prize_count":   C.PRIZE_COUNT,
            "prize_value":   C.PRIZE_VALUE,
        }

    @staticmethod
    def live_method(player, data):
        """Receive contact form submission and write to lottery_db."""
        if data.get("action") == "submit_contact":
            name  = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip()
            phone = str(data.get("phone", "")).strip()
            token = player.field_maybe_none('claim_token')
            if token:
                lottery_db.update_contact(token, name, email, phone)
            return {player.id_in_group: {"status": "saved"}}
        return {}


class Debrief(o.Page):
    """Step 9: Full debrief."""
    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "Debrief")
        if player.exit_code == "":
            player.is_completed = True
            if not player.field_maybe_none('completion_ts'):
                player.completion_ts = _now_ts()
            record_completion(player.participant.code, player.ui_condition, player.reward_condition)
        else:
            record_abandonment(player.participant.code)

        return {
            "platform_name": C.PLATFORM_NAME,
            "exit_code":     player.exit_code,
            "pool_min_pct":  C.POOL_MIN_PCT,
            "pool_max_pct":  C.POOL_MAX_PCT,
            "contact_email": C.CONTACT_EMAIL,
        }


# ===========================================================================
# PAGE SEQUENCE
# ===========================================================================

page_sequence = [
    ContentWarning,
    Instructions,
    Consent,
    ComprehensionQuiz,
    QuizFailed,
    Assignment,
    # Investment stages
    S1Endowment,
    S2Commitment,
    S3ReturnReveal,
    S4Reinvestment,
    S5PoolOutcome,
    S6Withdraw,
    S7FeeDisplay,
    S8PayAbandon,
    # Post-task
    PostTask,
    LotteryContact,
    Debrief,
]


# ===========================================================================
# ADMIN & EXPORT REPORTS (Completers per cell & Incomplete Sessions)
# ===========================================================================

def vars_for_admin_report(subsession):
    """
    Data for oTree Admin Session -> Admin Report tab.
    Shows completers per cell, dropouts, and live completion rates.
    """
    CELLS = [
        ("neutral",       "0pct"),
        ("neutral",       "35pct"),
        ("manipulative",  "0pct"),
        ("manipulative",  "35pct"),
    ]
    players = subsession.get_players()
    cell_stats = []
    incompletes = []

    for u, r in CELLS:
        k = f"{u}_{r}"
        cell_players = [
            p for p in players
            if p.field_maybe_none('ui_condition') == u and p.field_maybe_none('reward_condition') == r
        ]
        comp = sum(1 for p in cell_players if p.field_maybe_none('is_completed'))
        incomp = sum(1 for p in cell_players if not p.field_maybe_none('is_completed'))
        tot = len(cell_players)
        pct = f"{(comp / tot * 100):.1f}%" if tot > 0 else "0%"
        cell_stats.append({
            "key": k,
            "ui": u,
            "reward": r,
            "completers": comp,
            "incompletes": incomp,
            "total": tot,
            "rate": pct,
        })

    for p in players:
        if not p.field_maybe_none('is_completed'):
            ts = p.field_maybe_none('stage_reached_ts')
            ts_str = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "—"
            incompletes.append({
                "code": p.participant.code,
                "ui": p.field_maybe_none('ui_condition') or "Unassigned",
                "reward": p.field_maybe_none('reward_condition') or "Unassigned",
                "stage": p.field_maybe_none('stage_reached') or "NotStarted",
                "ts": ts_str,
                "exit_code": p.field_maybe_none('exit_code') or "—",
            })

    total_comp = sum(c["completers"] for c in cell_stats)
    total_assigned = sum(c["total"] for c in cell_stats)

    return {
        "cell_stats": cell_stats,
        "incompletes": incompletes,
        "total_completers": total_comp,
        "total_assigned": total_assigned,
    }


def custom_export(players):
    """
    Export report of completers and incompletes per cell.
    Available via oTree Data Export -> Custom export (cedarline).
    """
    CELLS = [
        ("neutral",       "0pct"),
        ("neutral",       "35pct"),
        ("manipulative",  "0pct"),
        ("manipulative",  "35pct"),
    ]

    completers_by_cell = {f"{u}_{r}": 0 for u, r in CELLS}
    incompletes_by_cell = {f"{u}_{r}": 0 for u, r in CELLS}
    unassigned_count = 0

    for p in players:
        ui = p.field_maybe_none('ui_condition')
        rew = p.field_maybe_none('reward_condition')
        if ui and rew:
            k = f"{ui}_{rew}"
            if p.field_maybe_none('is_completed'):
                completers_by_cell[k] = completers_by_cell.get(k, 0) + 1
            else:
                incompletes_by_cell[k] = incompletes_by_cell.get(k, 0) + 1
        else:
            unassigned_count += 1

    rows = []
    rows.append(["=== CEDARLINE COMPLETERS REPORT BY CELL ==="])
    rows.append(["Cell Key", "UI Condition", "Reward Condition", "Completers", "Incompletes (Dropouts)", "Total Assigned", "Completion Rate"])
    for u, r in CELLS:
        k = f"{u}_{r}"
        comp = completers_by_cell.get(k, 0)
        incomp = incompletes_by_cell.get(k, 0)
        tot = comp + incomp
        rate = f"{(comp / tot * 100):.1f}%" if tot > 0 else "N/A"
        rows.append([k, u, r, comp, incomp, tot, rate])

    rows.append([])
    rows.append(["Pre-Assignment Dropouts / Exits", "", "", "", "", unassigned_count, ""])
    rows.append([])

    rows.append(["=== INCOMPLETE SESSIONS BREAKDOWN ==="])
    rows.append(["Participant Code", "UI Condition", "Reward Condition", "Stage Reached", "Stage Reached UTC", "Exit Code"])
    for p in players:
        if not p.field_maybe_none('is_completed'):
            code = p.participant.code
            ui = p.field_maybe_none('ui_condition') or "Unassigned"
            rew = p.field_maybe_none('reward_condition') or "Unassigned"
            stage = p.field_maybe_none('stage_reached') or "NotStarted"
            ts = p.field_maybe_none('stage_reached_ts')
            ts_str = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else ""
            exit_c = p.field_maybe_none('exit_code') or ""
            rows.append([code, ui, rew, stage, ts_str, exit_c])

    rows.append([])
    rows.append(["=== PARTICIPANT LEVEL DATA ==="])
    rows.append([
        "Participant Code", "UI Condition", "Reward Condition", "Is Completed",
        "Stage Reached", "Stage Reached TS", "Completion TS", "Exit Code",
        "Reinvest Amount (R)", "Pool Return Num", "Pool Return Den",
        "Platform Balance Decision", "Pay Decision", "Final Balance",
        "Outcome Flag", "Lottery Weight", "Claim Token"
    ])
    for p in players:
        rows.append([
            p.participant.code,
            p.field_maybe_none('ui_condition') or "",
            p.field_maybe_none('reward_condition') or "",
            1 if p.field_maybe_none('is_completed') else 0,
            p.field_maybe_none('stage_reached') or "",
            p.field_maybe_none('stage_reached_ts') or "",
            p.field_maybe_none('completion_ts') or "",
            p.field_maybe_none('exit_code') or "",
            p.field_maybe_none('reinvest_amount') if p.field_maybe_none('reinvest_amount') is not None else "",
            p.field_maybe_none('pool_return_num') if p.field_maybe_none('pool_return_num') is not None else "",
            p.field_maybe_none('pool_return_den') if p.field_maybe_none('pool_return_den') is not None else "",
            p.field_maybe_none('platform_balance_decision') if p.field_maybe_none('platform_balance_decision') is not None else "",
            1 if p.field_maybe_none('pay_decision') else (0 if p.field_maybe_none('pay_decision') is not None else ""),
            p.field_maybe_none('final_balance_int') if p.field_maybe_none('final_balance_int') is not None else "",
            p.field_maybe_none('outcome_flag') or "",
            p.field_maybe_none('lottery_weight') if p.field_maybe_none('lottery_weight') is not None else "",
            p.field_maybe_none('claim_token') or "",
        ])

    return rows
