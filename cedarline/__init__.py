"""
cedarline/__init__.py
oTree v5 single-file app for the Cedarline study (v2 design).

Sequence: endowment -> fixed Rs 100 -> apparent return (0% / 35%) -> reinvest R1
-> pool outcome 1 -> reinvest R2 -> pool outcome 2 -> withdrawal fee ladder
(F1, then F2 only if F1 paid) -> outcome -> hypothetical real-money question.

Money math: ALL monetary computations go through logic.ledger (exact Fractions).
Amounts stored in oTree fields are converted to int/float ONLY at the boundary
(field assignment). Templates receive pre-converted integers; no arithmetic
is done in templates.
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
    F1, F2, STEP, PLATFORM_NAME, TIMER_SECS, CONTACT_EMAIL,
    FREEZE_TIMER_ENABLED, FREEZE_TIMER_SECS,
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
from pool_sequence import draw_pool_return, ensure_generated, usage_summary
import lottery_db

# ---------------------------------------------------------------------------
# Initialise side stores at import time (both are idempotent)
# ---------------------------------------------------------------------------
lottery_db.init_db()
ensure_generated()      # pool outcome sequence exists before anyone needs it

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

    PLATFORM_NAME = PLATFORM_NAME
    TIMER_SECS    = TIMER_SECS
    FREEZE_SECS   = FREEZE_TIMER_SECS
    CONTACT_EMAIL = CONTACT_EMAIL
    PRIZE_COUNT   = PRIZE_COUNT
    PRIZE_VALUE   = PRIZE_VALUE
    F1            = F1
    F2            = F2
    ENDOWMENT     = int(ledger.ENDOWMENT)
    COMMIT        = int(ledger.COMMIT)
    START_CASH    = int(ledger.START_CASH)
    CAP           = int(ledger.total_cap(F1, F2))    # total across both rounds (550)
    STEP          = STEP
    POOL_MIN_PCT  = POOL_MIN_RETURN_PCT
    POOL_MAX_PCT  = POOL_MAX_RETURN_PCT
    LOTTERY_WEIGHT_DIVISOR = LOTTERY_WEIGHT_DIVISOR

    R1_OPTIONS = [int(r) for r in ledger.r1_options(F1, F2)]

    # Stage order for the progress bar (S7 and W3 are skipped for some people)
    STAGES = ["S1Endowment", "S2Commitment", "S3ReturnReveal", "S4Reinvestment",
              "S5PoolOutcome", "S6Reinvest2", "S7PoolOutcome2", "W1Withdraw",
              "W2Fee1", "W3Fee2", "W4Outcome"]

    QUIZ_CORRECT = {
        "q_initial":  "100",
        "q_max_r":    str(int(ledger.total_cap(F1, F2))),
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

    # --- Exit codes: "left_at_content_warning" | "quiz_failed_twice" | "" ---
    exit_code = _m.StringField(blank=True, initial="")

    # --- Quiz ---
    quiz_attempts = _m.IntegerField(initial=0)
    quiz_passed   = _m.BooleanField(initial=False)   # set only by server-side grading

    # --- Round 1 (primary outcome: reinvest_amount = R1) ---
    reinvest_amount  = _m.IntegerField(blank=True)   # R1 (Rs)
    pool_return_num  = _m.IntegerField(blank=True)   # r1 as a Fraction; None if R1 = 0
    pool_return_den  = _m.IntegerField(initial=1)
    pool1_seq_index  = _m.IntegerField(blank=True)   # position used in the pre-generated sequence

    # --- Round 2 ---
    reinvest2_amount = _m.IntegerField(blank=True)   # R2 (Rs)
    pool2_return_num = _m.IntegerField(blank=True)   # r2; None if R2 = 0
    pool2_return_den = _m.IntegerField(initial=1)
    pool2_seq_index  = _m.IntegerField(blank=True)
    pool_seq_version = _m.StringField(blank=True)

    # --- Process data: reinvestment pages ---
    timer_deadline_ts       = _m.FloatField(blank=True)   # S4 countdown deadline (manipulative)
    s4_first_render_ts      = _m.FloatField(blank=True)
    s4_submit_ts            = _m.FloatField(blank=True)
    s4_timer_left_at_submit = _m.FloatField(blank=True)   # seconds left (0 = expired)
    s4_event_log            = _m.LongStringField(blank=True, initial="[]")
    s6_first_render_ts      = _m.FloatField(blank=True)
    s6_submit_ts            = _m.FloatField(blank=True)
    s6_event_log            = _m.LongStringField(blank=True, initial="[]")
    w1_withdraw_click_ts    = _m.FloatField(blank=True)

    # --- Withdrawal fee ladder ---
    platform_balance_decision = _m.IntegerField(blank=True)  # P at the fee stage
    zone_at_fee               = _m.StringField(blank=True)   # ledger.zone(P, F1, F2)

    fee1_decision_str    = _m.StringField(blank=True)        # form vehicle: "pay" | "abandon"
    fee1_paid            = _m.BooleanField(blank=True)
    fee1_first_render_ts = _m.FloatField(blank=True)
    fee1_submit_ts       = _m.FloatField(blank=True)
    fee1_process_log     = _m.LongStringField(blank=True)    # pointer path, hovers, terms/support, tabs
    fee1_terms_opened    = _m.IntegerField(blank=True)
    fee1_support_clicks  = _m.IntegerField(blank=True)

    fee2_decision_str    = _m.StringField(blank=True)
    fee2_paid            = _m.BooleanField(blank=True)       # None = never reached step 2
    fee2_first_render_ts = _m.FloatField(blank=True)
    fee2_submit_ts       = _m.FloatField(blank=True)
    fee2_process_log     = _m.LongStringField(blank=True)
    fee2_terms_opened    = _m.IntegerField(blank=True)
    fee2_support_clicks  = _m.IntegerField(blank=True)
    fee2_deadline_ts     = _m.FloatField(blank=True)         # freeze countdown (manipulative)
    fee2_timer_left_at_submit = _m.FloatField(blank=True)

    fees_paid_total   = _m.IntegerField(blank=True)
    funds_released    = _m.BooleanField(blank=True)
    step1_flag_myopic = _m.StringField(blank=True)   # P vs F1 (what was visible)
    step1_flag_full   = _m.StringField(blank=True)   # P vs F1+F2 (hindsight)
    step2_flag        = _m.StringField(blank=True)   # P vs F2 (F1 sunk); blank if not reached
    final_balance_int = _m.IntegerField(blank=True)
    lottery_weight    = _m.FloatField(blank=True)    # final_balance / 10

    # --- Hypothetical real-money question (after the ladder) ---
    hyp_real_pay = _m.IntegerField(blank=True, min=1, max=5)       # 1=Definitely not .. 5=Definitely yes
    hyp_real_max = _m.IntegerField(blank=True, min=0, max=100000)  # most real Rs they would pay

    # --- Questionnaire ---
    q_trust        = _m.IntegerField(blank=True, min=1, max=7)
    q_legitimacy   = _m.IntegerField(blank=True, min=1, max=7)
    q_risk         = _m.IntegerField(blank=True, min=1, max=7)
    q_confidence   = _m.IntegerField(blank=True, min=1, max=7)
    q_reward_noticed = _m.StringField(blank=True)   # "yes"/"no"
    q_ui_noticed     = _m.StringField(blank=True)   # "yes"/"no"
    q_attention      = _m.IntegerField(blank=True, min=1, max=7)
    q_suspicion      = _m.LongStringField(blank=True)
    # Retrospective sureness that paying would release the balance (0-100, steps of 10)
    q_sure_fee1      = _m.IntegerField(blank=True, min=0, max=100)
    q_sure_fee2      = _m.IntegerField(blank=True, min=0, max=100)   # only if step 2 reached
    q_realworld      = _m.StringField(blank=True)   # comma list: pay,support,report,family,stop

    # Financial literacy (Lusardi & Mitchell Big Three)
    q_finlit_interest  = _m.StringField(blank=True)
    q_finlit_inflation = _m.StringField(blank=True)
    q_finlit_risk      = _m.StringField(blank=True)

    # DOSPERT financial items (Blais & Weber, 1-7)
    q_dospert_invest    = _m.IntegerField(blank=True, min=1, max=7)
    q_dospert_speculate = _m.IntegerField(blank=True, min=1, max=7)
    q_dospert_gamble    = _m.IntegerField(blank=True, min=1, max=7)

    # --- Lottery (no PII here; contacts live in lottery_db) ---
    claim_token         = _m.StringField(blank=True)
    lottery_opt_out     = _m.BooleanField(initial=False)
    lottery_opt_out_str = _m.StringField(blank=True)   # "1" = opt out (form vehicle)

    # --- Completion & incomplete-session tracking ---
    is_completed     = _m.BooleanField(initial=False)
    stage_reached    = _m.StringField(initial="ContentWarning")
    stage_reached_ts = _m.FloatField(blank=True)
    completion_ts    = _m.FloatField(blank=True)


# ===========================================================================
# HELPERS
# ===========================================================================

def _now_ts():
    return time.time()


def _mark_stage(player, stage_name: str):
    player.stage_reached = stage_name
    player.stage_reached_ts = _now_ts()


def _reward_fraction(player) -> Fr:
    return REWARD_35 if player.reward_condition == "35pct" else REWARD_0


def _frac(num, den):
    return Fr(0) if num is None else Fr(num, den or 1)


def _state(player):
    """All ledger quantities for this player, as exact Fractions."""
    g  = _reward_fraction(player)
    R1 = Fr(player.field_maybe_none('reinvest_amount') or 0)
    R2 = Fr(player.field_maybe_none('reinvest2_amount') or 0)
    r1 = _frac(player.field_maybe_none('pool_return_num'), player.field_maybe_none('pool_return_den'))
    r2 = _frac(player.field_maybe_none('pool2_return_num'), player.field_maybe_none('pool2_return_den'))
    return {
        "g": g, "R1": R1, "R2": R2, "r1": r1, "r2": r2,
        "C": ledger.cash(R1, R2),
        "P0": ledger.platform_after_reward(g),
        "P1": ledger.platform_after_r1(g, R1, r1),
        "P": ledger.platform_balance(g, R1, r1, R2, r2),
    }


def _pct_str(r: Fr) -> str:
    pct = int(r * 100)
    return f"+{pct}%" if pct >= 0 else f"{pct}%"


def _ensure_assigned(player):
    """Assign the participant to a cell exactly once (idempotent)."""
    if player.assigned:
        return
    cfg = player.session.config
    force_ui, force_reward = cfg.get("force_ui"), cfg.get("force_reward")
    if force_ui and force_reward:          # DEV-ONLY forced cell
        ui, reward = force_ui, force_reward
    else:
        ui, reward = assign_participant(player.participant.code)
    player.ui_condition     = ui
    player.reward_condition = reward
    player.assigned         = True


def _draw_pool(player, round_no):
    """Draw and store the pool outcome for a round, exactly once."""
    num_field = "pool_return_num" if round_no == 1 else "pool2_return_num"
    if player.field_maybe_none(num_field) is not None:
        return
    r, idx, version = draw_pool_return(f"{player.ui_condition}_{player.reward_condition}", round_no)
    if round_no == 1:
        player.pool_return_num, player.pool_return_den, player.pool1_seq_index = r.numerator, r.denominator, idx
    else:
        player.pool2_return_num, player.pool2_return_den, player.pool2_seq_index = r.numerator, r.denominator, idx
    player.pool_seq_version = version


def _log_event(player, field, data, allowed):
    """Append a client event to a JSON log field with a server timestamp."""
    action = data.get("action")
    if action not in allowed:
        return
    log = json.loads(player.field_maybe_none(field) or "[]")
    log.append({"event": action, "amount": data.get("amount"), "ts": _now_ts()})
    setattr(player, field, json.dumps(log))


_REINVEST_EVENTS = ("change", "first_render", "final_submit", "disclosure_visible",
                    "disclosure_hidden", "tab_hidden", "tab_visible", "timer_expired")


def _process_counts(raw):
    """(terms_opened, support_clicks) from a fee-page process log; robust to junk."""
    try:
        events = json.loads(raw or "{}").get("events", [])
        terms = sum(1 for e in events if isinstance(e, list) and len(e) > 1 and e[1] == "terms_open")
        support = sum(1 for e in events if isinstance(e, list) and len(e) > 1 and e[1] == "support_open")
        return terms, support
    except (ValueError, AttributeError, TypeError):
        return None, None


def _finalize(player):
    """
    Close the ledger once the withdrawal path is known (abandon at step 1, or
    step 2 answered). Idempotent. Also creates the lottery claim token.
    """
    if player.field_maybe_none('final_balance_int') is not None:
        return
    s = _state(player)
    paid1 = bool(player.field_maybe_none('fee1_paid'))
    paid2 = bool(player.field_maybe_none('fee2_paid'))
    P = s["P"]
    W = ledger.final_balance(s["g"], s["R1"], s["r1"], s["R2"], s["r2"], F1, F2, paid1, paid2)
    flags1 = ledger.classify_step1(P, F1, F2, paid1)

    player.platform_balance_decision = int(P)
    player.zone_at_fee       = ledger.zone(P, F1, F2)
    player.fees_paid_total   = int(ledger.fees_paid(F1, F2, paid1, paid2))
    player.funds_released    = ledger.released(paid1, paid2)
    player.step1_flag_myopic = flags1["myopic"]
    player.step1_flag_full   = flags1["full"]
    player.step2_flag        = ledger.classify_step2(P, F2, paid2) if paid1 else ""
    player.final_balance_int = int(W)
    player.lottery_weight    = max(0.0, float(W) / LOTTERY_WEIGHT_DIVISOR)
    if not player.field_maybe_none('claim_token'):
        player.claim_token = lottery_db.create_entry()


# ===========================================================================
# PAGES — Pre-assignment (neutral styling for everyone)
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
            player.quiz_passed = True
            return {player.id_in_group: {"status": "pass"}}

        if player.quiz_attempts >= 2:
            player.exit_code = "quiz_failed_twice"
            player.stage_reached = "QuizFailedTwice"
            player.stage_reached_ts = _now_ts()
            record_abandonment(player.participant.code)
            return {player.id_in_group: {"status": "fail_final", "results": results}}

        return {player.id_in_group: {"status": "fail_retry", "results": results}}

    @staticmethod
    def error_message(player, values):
        # The page can only be left after server-side grading: a pass, or the
        # second failed attempt (which routes to QuizFailed).
        if not player.quiz_passed and player.exit_code != "quiz_failed_twice":
            return "Please answer the quiz questions and press Check Answers."
        return None

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



# ===========================================================================
# PAGES — Investment stages (skin depends on ui_condition)
# ===========================================================================

# Manipulative-arm copy. Identical in both reward arms; never mentions
# returns, amounts, percentages or 35%.
ADVISOR = {
    "S4Reinvestment": "Namaste 🙏 I'm Neha, your account manager. Most members add funds at this stage.",
    "S6Reinvest2":    "Many members top up again before they withdraw. The Gold window won't stay open for long.",
    "W2Fee1":         "Processing fees are standard for every withdrawal. It only takes a moment.",
    "W3Fee2":         "This is a one-time verification. Please complete it so your funds are not held 🙏",
}


class _InvestBase(o.Page):
    """Shared context for S1–W4."""

    @staticmethod
    def _base_vars(player, stage_name):
        _mark_stage(player, stage_name)
        is_manip = player.ui_condition == "manipulative"
        now = _now_ts()

        # Guide §6: the reinvestment countdown starts on S4 and is shown only there.
        on_s4 = stage_name == "S4Reinvestment"
        if on_s4 and not player.field_maybe_none('s4_first_render_ts'):
            player.s4_first_render_ts = now
        deadline = player.field_maybe_none('timer_deadline_ts')
        if is_manip and on_s4 and not deadline:
            player.timer_deadline_ts = now + C.TIMER_SECS
            deadline = player.timer_deadline_ts
        deadline = deadline or (now + C.TIMER_SECS)

        idx = C.STAGES.index(stage_name)
        progress = ["done" if i < idx else ("active" if i == idx else "") for i in range(len(C.STAGES))]
        s = _state(player)
        return {
            "platform_name":   C.PLATFORM_NAME,
            "is_manipulative": is_manip,
            "show_timer":      is_manip and on_s4,
            "show_freeze":     False,
            "timer_secs":      C.TIMER_SECS,
            "timer_remaining_secs": max(0, int(deadline - now)),
            "timer_deadline_ts": deadline,
            "advisor_msg":     ADVISOR.get(stage_name) if is_manip else None,
            "no_toasts":       False,
            "stage_no":        idx + 1,
            "stage_total":     len(C.STAGES),
            "progress":        progress,
            "endowment":       C.ENDOWMENT,
            "commit":          C.COMMIT,
            "cap":             C.CAP,
            "f1":              C.F1,
            "f2":              C.F2,
            "pool_min_pct":    C.POOL_MIN_PCT,
            "pool_max_pct":    C.POOL_MAX_PCT,
            "cash_balance":    int(s["C"]),
            "platform_balance": int(s["P"]),
        }


def _shown(player):
    return player.exit_code == ""


class S1Endowment(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        return _InvestBase._base_vars(player, "S1Endowment")


class S2Commitment(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S2Commitment")
        # Ledger §2.1: after commitment C = 900, P = 100 (return not applied until S3)
        v["platform_balance"] = C.COMMIT
        v["cash_balance"]     = C.START_CASH
        return v


class S3ReturnReveal(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S3ReturnReveal")
        v["platform_balance"] = int(_state(player)["P0"])
        v["cash_balance"]     = C.START_CASH
        v["reward_pct"]       = 35 if player.reward_condition == "35pct" else 0
        return v


class S4Reinvestment(_InvestBase):
    """Round 1 (primary outcome). Countdown runs here in the manipulative arm."""
    form_model  = "player"
    form_fields = ["reinvest_amount"]
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S4Reinvestment")
        v["r_options"]        = C.R1_OPTIONS
        v["platform_balance"] = int(_state(player)["P0"])
        v["cash_balance"]     = C.START_CASH
        v["show_scarcity"]    = v["is_manipulative"]
        return v

    @staticmethod
    def live_method(player, data):
        _log_event(player, "s4_event_log", data, _REINVEST_EVENTS)
        return {}

    @staticmethod
    def error_message(player, values):
        r = values.get("reinvest_amount")
        if r is None:
            return "Please select a reinvestment amount."
        if r not in C.R1_OPTIONS:
            return "Please select a valid amount from the list."
        return None

    @staticmethod
    def before_next_page(player, timeout_happened):
        now = _now_ts()
        if not player.field_maybe_none('s4_submit_ts'):
            player.s4_submit_ts = now
            deadline = player.field_maybe_none('timer_deadline_ts')
            if player.ui_condition == "manipulative" and deadline:
                player.s4_timer_left_at_submit = max(0.0, round(deadline - now, 2))
            _log_event(player, "s4_event_log", {"action": "final_submit", "amount": player.reinvest_amount},
                       ("final_submit",))
        # Outcome assigned only after submission, and only if money was moved in.
        if player.reinvest_amount > 0:
            _draw_pool(player, 1)


class S5PoolOutcome(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S5PoolOutcome")
        s = _state(player)
        v["reinvest_amount"]  = int(s["R1"])
        v["platform_balance"] = int(s["P1"])
        v["platform_before"]  = int(s["P0"] + s["R1"])
        v["cash_balance"]     = int(ledger.cash(s["R1"]))
        v["pool_return_str"]  = _pct_str(s["r1"])
        v["pool_gain"]        = s["r1"] > 0
        v["show_testimonials"] = v["is_manipulative"]
        return v


class S6Reinvest2(_InvestBase):
    """Round 2: the 'add more before withdrawing?' decision, after outcome 1."""
    form_model  = "player"
    form_fields = ["reinvest2_amount"]
    is_displayed = staticmethod(_shown)

    @staticmethod
    def _options(player):
        return [int(r) for r in ledger.r2_options(player.reinvest_amount or 0, F1, F2)]

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S6Reinvest2")
        if not player.field_maybe_none('s6_first_render_ts'):
            player.s6_first_render_ts = _now_ts()
        s = _state(player)
        opts = S6Reinvest2._options(player)
        v["r_options"]        = opts
        v["r2_max"]           = opts[-1]
        v["platform_balance"] = int(s["P1"])
        v["cash_balance"]     = int(ledger.cash(s["R1"]))
        v["reinvest_amount"]  = int(s["R1"])
        v["show_scarcity"]    = v["is_manipulative"]
        return v

    @staticmethod
    def live_method(player, data):
        _log_event(player, "s6_event_log", data, _REINVEST_EVENTS)
        return {}

    @staticmethod
    def error_message(player, values):
        r = values.get("reinvest2_amount")
        if r is None:
            return "Please select an amount (choose Rs 0 to add nothing)."
        if r not in S6Reinvest2._options(player):
            return "Please select a valid amount from the list."
        return None

    @staticmethod
    def before_next_page(player, timeout_happened):
        if not player.field_maybe_none('s6_submit_ts'):
            player.s6_submit_ts = _now_ts()
            _log_event(player, "s6_event_log", {"action": "final_submit", "amount": player.reinvest2_amount},
                       ("final_submit",))
        if player.reinvest2_amount > 0:
            _draw_pool(player, 2)


class S7PoolOutcome2(_InvestBase):
    @staticmethod
    def is_displayed(player):
        return _shown(player) and (player.field_maybe_none('reinvest2_amount') or 0) > 0

    @staticmethod
    def vars_for_template(player):
        v = _InvestBase._base_vars(player, "S7PoolOutcome2")
        s = _state(player)
        v["reinvest2_amount"] = int(s["R2"])
        v["platform_before"]  = int(s["P1"] + s["R2"])
        v["pool_return_str"]  = _pct_str(s["r2"])
        return v


class W1Withdraw(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        return _InvestBase._base_vars(player, "W1Withdraw")

    @staticmethod
    def before_next_page(player, timeout_happened):
        if not player.field_maybe_none('w1_withdraw_click_ts'):
            player.w1_withdraw_click_ts = _now_ts()


def _fee_vars(player, step):
    stage = "W2Fee1" if step == 1 else "W3Fee2"
    v = _InvestBase._base_vars(player, stage)
    s = _state(player)
    cash_now = s["C"] - (F1 if step == 2 else 0)
    v.update({
        "step":            step,
        "fee":             F1 if step == 1 else F2,
        "fees_paid_so_far": F1 if step == 2 else 0,
        "cash_balance":    int(cash_now),
        "keep_if_abandon": int(cash_now),
        "decision_field":  "fee1_decision_str" if step == 1 else "fee2_decision_str",
        "log_field":       "fee1_process_log" if step == 1 else "fee2_process_log",
        "sunk_line":       v["is_manipulative"] and step == 2,
        # No pop-up toasts on fee screens: a toast over one option button could
        # bias the very choice being measured. The in-page activity card stays.
        "no_toasts":       True,
    })
    return v


def _fee_error(values, field):
    if values.get(field) not in ("pay", "abandon"):
        return "Please choose one of the two options."
    return None


class W2Fee1(_InvestBase):
    """Fee step 1: withdrawal processing fee (F1)."""
    template_name = "cedarline/FeeStep.html"
    form_model  = "player"
    form_fields = ["fee1_decision_str", "fee1_process_log"]
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        if not player.field_maybe_none('fee1_first_render_ts'):
            player.fee1_first_render_ts = _now_ts()
        # Freeze the decision-point balance and its zone once, on first render.
        if player.field_maybe_none('platform_balance_decision') is None:
            P = _state(player)["P"]
            player.platform_balance_decision = int(P)
            player.zone_at_fee = ledger.zone(P, F1, F2)
        return _fee_vars(player, 1)

    @staticmethod
    def error_message(player, values):
        return _fee_error(values, "fee1_decision_str")

    @staticmethod
    def before_next_page(player, timeout_happened):
        if player.field_maybe_none('fee1_paid') is None:
            player.fee1_paid = player.fee1_decision_str == "pay"
            player.fee1_submit_ts = _now_ts()
            player.fee1_terms_opened, player.fee1_support_clicks = _process_counts(player.fee1_process_log)
        if not player.fee1_paid:
            _finalize(player)


class W3Fee2(_InvestBase):
    """Fee step 2: verification fee (F2). Only after paying F1; F1 is now sunk."""
    template_name = "cedarline/FeeStep.html"
    form_model  = "player"
    form_fields = ["fee2_decision_str", "fee2_process_log"]

    @staticmethod
    def is_displayed(player):
        return _shown(player) and bool(player.field_maybe_none('fee1_paid'))

    @staticmethod
    def vars_for_template(player):
        now = _now_ts()
        if not player.field_maybe_none('fee2_first_render_ts'):
            player.fee2_first_render_ts = now
        v = _fee_vars(player, 2)
        if v["is_manipulative"] and FREEZE_TIMER_ENABLED:
            if not player.field_maybe_none('fee2_deadline_ts'):
                player.fee2_deadline_ts = now + C.FREEZE_SECS
            v["show_freeze"]   = True
            v["freeze_deadline_ts"] = player.fee2_deadline_ts
            v["freeze_secs"]   = C.FREEZE_SECS
            v["freeze_remaining_secs"] = max(0, int(player.fee2_deadline_ts - now))
        return v

    @staticmethod
    def error_message(player, values):
        return _fee_error(values, "fee2_decision_str")

    @staticmethod
    def before_next_page(player, timeout_happened):
        if player.field_maybe_none('fee2_paid') is None:
            now = _now_ts()
            player.fee2_paid = player.fee2_decision_str == "pay"
            player.fee2_submit_ts = now
            player.fee2_terms_opened, player.fee2_support_clicks = _process_counts(player.fee2_process_log)
            dl = player.field_maybe_none('fee2_deadline_ts')
            if dl:
                player.fee2_timer_left_at_submit = max(0.0, round(dl - now, 2))
        _finalize(player)


class W4Outcome(_InvestBase):
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        _finalize(player)       # guard: always closed before the outcome is shown
        v = _InvestBase._base_vars(player, "W4Outcome")
        v["released"]       = bool(player.funds_released)
        v["fees_paid"]      = player.fees_paid_total
        v["final_balance"]  = player.final_balance_int
        v["platform_balance"] = player.platform_balance_decision
        v["stopped_at"]     = 1 if not player.fee1_paid else (2 if not player.funds_released else None)
        return v


# ===========================================================================
# PAGES — Post-task
# ===========================================================================

class HypotheticalRealMoney(o.Page):
    """
    Secondary, exploratory: would the participant pay REAL money to release
    the platform balance? Researcher's voice, neutral styling, all cells.
    Comes after the whole fee ladder, so it cannot alter those choices.
    """
    form_model  = "player"
    form_fields = ["hyp_real_pay", "hyp_real_max"]
    is_displayed = staticmethod(_shown)

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "HypotheticalRealMoney")
        if player.funds_released:
            path = "released"
        elif player.fee1_paid:
            path = "abandoned_fee2"
        else:
            path = "abandoned_fee1"
        return {
            "platform_name":    C.PLATFORM_NAME,
            "platform_balance": player.platform_balance_decision or 0,
            "path":             path,
            "pay_scale": [(1, "Definitely not"), (2, "Probably not"), (3, "Not sure"),
                          (4, "Probably yes"), (5, "Definitely yes")],
        }

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
        "q_finlit_interest", "q_finlit_inflation", "q_finlit_risk",
        "q_dospert_invest", "q_dospert_speculate", "q_dospert_gamble",
    ]

    @staticmethod
    def get_form_fields(player):
        # Withdrawal reflections first; the step-2 item only if step 2 was reached.
        extra = ["q_sure_fee1", "q_realworld"]
        if player.field_maybe_none('fee1_paid'):
            extra.insert(1, "q_sure_fee2")
        return extra + PostTask.form_fields

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
        dospert_items = [
            ("q_dospert_invest",    "Investing 10% of your annual income in a moderate-growth diversified fund."),
            ("q_dospert_speculate", "Investing 5% of your annual income in a very speculative or high-risk venture."),
            ("q_dospert_gamble",    "Betting a day's income at a high-stakes game of chance or casino."),
        ]
        return {
            "platform_name":   C.PLATFORM_NAME,
            "is_manipulative": player.ui_condition == "manipulative",
            "perceptions":     perceptions,
            "dospert_items":   dospert_items,
            "reached_fee2":    bool(player.field_maybe_none('fee1_paid')),
            "f1":              C.F1,
            "f2":              C.F2,
            "sure_scale":      list(range(0, 101, 10)),
            "realworld_options": [
                ("pay",     "Pay the fee"),
                ("support", "Contact the app's support team"),
                ("report",  "Report it (e.g. cybercrime.gov.in or helpline 1930)"),
                ("family",  "Ask family or friends for advice"),
                ("stop",    "Stop using the app"),
            ],
        }


class LotteryContact(o.Page):
    """
    Step 8: Lottery contact form.
    Participants are enrolled by default with claim token (opt-out treatment).
    Contact data written directly to lottery_contacts.sqlite3 via lottery_db.
    No PII stored in oTree Player fields.
    """
    form_model  = "player"
    form_fields = ["lottery_opt_out_str"]

    @staticmethod
    def is_displayed(player):
        return player.exit_code == ""

    @staticmethod
    def vars_for_template(player):
        _mark_stage(player, "LotteryContact")
        return {
            "platform_name": C.PLATFORM_NAME,
            "claim_token":   player.field_maybe_none('claim_token') or "",
            "prize_count":   C.PRIZE_COUNT,
            "prize_value":   C.PRIZE_VALUE,
            "allow_opt_out": LOTTERY_OPT_OUT,
        }

    @staticmethod
    def live_method(player, data):
        """Receive contact form submission or opt-out and write to lottery_db."""
        if data.get("action") == "submit_contact":
            name  = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip()
            phone = str(data.get("phone", "")).strip()
            token = player.field_maybe_none('claim_token')
            if token:
                lottery_db.update_contact(token, name, email, phone)
            return {player.id_in_group: {"status": "saved"}}

        if data.get("action") == "opt_out":
            player.lottery_opt_out = True
            player.lottery_weight = 0.0
            return {player.id_in_group: {"status": "opted_out"}}
        return {}

    @staticmethod
    def before_next_page(player, timeout_happened):
        if player.field_maybe_none('lottery_opt_out_str') == "1":
            player.lottery_opt_out = True
        if player.field_maybe_none('lottery_opt_out'):
            player.lottery_weight = 0.0



def _report_card(player):
    """
    Personalised debrief built from the participant's own frozen ledger values.
    Shown after every measure, so it cannot affect the data.
    Each item: {"tone": "good"|"warn"|"info", "title": str, "detail": str}.
    Reinvestment is never graded: at the time of each choice the pool had a
    positive expected return and the fees were not yet known.
    """
    items = []
    s = _state(player)
    manip = player.ui_condition == "manipulative"
    reward_pct = 35 if player.reward_condition == "35pct" else 0
    R1, R2 = int(s["R1"]), int(s["R2"])
    P = player.field_maybe_none('platform_balance_decision')
    paid1 = bool(player.field_maybe_none('fee1_paid'))
    paid2 = bool(player.field_maybe_none('fee2_paid'))
    left = player.field_maybe_none('s4_timer_left_at_submit')

    items.append({"tone": "info",
                  "title": f"Your first return of {reward_pct}% was set by the study",
                  "detail": ("Participants were randomly shown either 0% or 35% on their first Rs 100. "
                             "Fraud apps often show an early 'profit' to build trust before asking for more.")})

    if R1 > 0:
        if manip and left is not None and left > 0:
            d = (f"You confirmed with about {int(round(left))} seconds left on the countdown. "
                 "The countdown was not real: at zero it only changed to 'Window extended'.")
        elif manip:
            d = "You confirmed after the countdown had run out, which shows the deadline never mattered."
        else:
            d = "On fraud apps, the push to add money usually comes with countdowns, 'live' counts and status levels."
        items.append({"tone": "info", "title": f"You moved Rs {R1} into the Growth Pool", "detail": d})
        items.append({"tone": "info",
                      "title": f"Your first pool result ({_pct_str(s['r1'])}) was pre-set",
                      "detail": ("It came from a pre-shuffled random sequence and did not depend on your "
                                 "first return, the interface you saw, or how much you put in.")})
    else:
        items.append({"tone": "info", "title": "You kept your cash in the first round",
                      "detail": "You chose not to add money to the Growth Pool at the first opportunity."})

    if R2 > 0:
        if R1 > 0 and s["r1"] < 0:
            d = ("You added more right after a loss. Adding money to 'win it back' is one of the main ways "
                 "fraud apps deepen losses.")
        elif R1 > 0:
            d = "You added more after a gain. Early wins are often used to encourage bigger deposits."
        else:
            d = "You added money at the second opportunity."
        items.append({"tone": "info", "title": f"You added Rs {R2} before withdrawing", "detail": d})
    else:
        items.append({"tone": "info", "title": "You did not add more before withdrawing",
                      "detail": "You chose to stop adding money and go straight to the withdrawal."})

    if P is not None:
        if not paid1:
            items.append({"tone": "good", "title": f"You refused the Rs {F1} withdrawal fee",
                          "detail": ("You kept your cash and walked away from the platform balance. Refusing to pay "
                                     "up front to withdraw is the right reflex on any real app.")})
        else:
            items.append({"tone": "info", "title": f"You paid the Rs {F1} withdrawal fee",
                          "detail": "Then a second fee appeared. On real fraud apps, the first fee is almost never the last."})
            if not paid2:
                items.append({"tone": "good", "title": f"You stopped at the second fee (Rs {F2})",
                              "detail": (f"You lost the Rs {F1} already paid, but stopping when the fees keep coming "
                                         "is exactly what limits losses in real scams.")})
            elif P < F2:
                items.append({"tone": "warn", "title": f"You paid Rs {F2} more to release Rs {P}",
                              "detail": (f"Even ignoring the Rs {F1} already paid, this second fee cost more than it "
                                         "released. Feeling you must not 'waste' what you already paid is the sunk-cost "
                                         "trap scams depend on.")})
            elif P < F1 + F2:
                items.append({"tone": "warn", "title": f"You paid Rs {F1 + F2} in fees to release Rs {P}",
                              "detail": ("Each fee looked worth paying on its own, but together they cost more than you "
                                         "got back. That is how a fee ladder works.")})
            else:
                items.append({"tone": "info", "title": f"You paid Rs {F1 + F2} in fees to release Rs {P}",
                              "detail": ("Inside this task that came out ahead. On a real fraud app the balance usually "
                                         "never arrives: there is always another fee.")})

    hp = player.field_maybe_none('hyp_real_pay')
    hm = player.field_maybe_none('hyp_real_max')
    if hp is not None:
        if hp >= 4 or (hm or 0) > 0:
            amt = f" (up to Rs {hm})" if hm else ""
            items.append({"tone": "warn", "title": f"You said you might pay real money to unlock the balance{amt}",
                          "detail": ("Being asked to 'pay again to unlock' is how most victims lose the largest "
                                     "amounts. A real platform deducts its charges; it never asks you to pay first.")})
        elif hp == 3:
            items.append({"tone": "info", "title": "You were unsure about paying real money to unlock it",
                          "detail": "If an app asks you to pay before you can withdraw, treat that as a red flag."})
        else:
            items.append({"tone": "good", "title": "You said you would not pay real money to unlock it",
                          "detail": "Exactly right: never pay a fee, 'tax' or deposit to release a withdrawal."})

    if manip:
        items.append({"tone": "info", "title": "Your app used pressure tactics",
                      "detail": ("The countdown, the 'live' investor count, the pop-ups, the 'slots left' notice, the "
                                 "account manager's messages, the reviews, the Silver-to-Gold bar (fixed at 72% for "
                                 "everyone)" + (" and the account-freeze countdown" if FREEZE_TIMER_ENABLED else "")
                                 + " were all made up.")})
    else:
        items.append({"tone": "info", "title": "You saw the plain version of the app",
                      "detail": ("Other participants saw the same numbers with countdowns, made-up investor activity, "
                                 "an 'account manager' and a status bar added.")})
    return items


class Debrief(o.Page):
    """Final page: report card and full debrief."""
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
            "report_card":   _report_card(player) if player.exit_code == "" else [],
            "final_balance": player.field_maybe_none('final_balance_int'),
            "f1":            C.F1,
            "f2":            C.F2,
            "cap":           C.CAP,
            "freeze_enabled": FREEZE_TIMER_ENABLED,
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
    # Investment
    S1Endowment,
    S2Commitment,
    S3ReturnReveal,
    S4Reinvestment,
    S5PoolOutcome,
    S6Reinvest2,
    S7PoolOutcome2,
    # Withdrawal ladder
    W1Withdraw,
    W2Fee1,
    W3Fee2,
    W4Outcome,
    # Post-task
    HypotheticalRealMoney,
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
        "pool_usage": [{"queue": k, "used": u, "length": n} for k, (u, n) in sorted(usage_summary().items())],
    }



# One row per participant. Order matters: it is the analysis file's column order.
EXPORT_FIELDS = [
    # condition & completion
    "ui_condition", "reward_condition", "is_completed", "stage_reached", "stage_reached_ts",
    "completion_ts", "exit_code", "quiz_passed", "quiz_attempts",
    # round 1 (primary) and round 2
    "reinvest_amount", "pool_return_num", "pool_return_den", "pool1_seq_index",
    "reinvest2_amount", "pool2_return_num", "pool2_return_den", "pool2_seq_index", "pool_seq_version",
    # reinvestment process data
    "s4_first_render_ts", "s4_submit_ts", "s4_timer_left_at_submit", "s4_event_log",
    "s6_first_render_ts", "s6_submit_ts", "s6_event_log", "w1_withdraw_click_ts",
    # fee ladder
    "platform_balance_decision", "zone_at_fee",
    "fee1_paid", "fee1_first_render_ts", "fee1_submit_ts", "fee1_terms_opened", "fee1_support_clicks",
    "fee2_paid", "fee2_first_render_ts", "fee2_submit_ts", "fee2_terms_opened", "fee2_support_clicks",
    "fee2_timer_left_at_submit",
    "fees_paid_total", "funds_released", "step1_flag_myopic", "step1_flag_full", "step2_flag",
    "final_balance_int", "lottery_weight", "lottery_opt_out",
    # post-task
    "hyp_real_pay", "hyp_real_max", "q_sure_fee1", "q_sure_fee2", "q_realworld",
    "q_trust", "q_legitimacy", "q_risk", "q_confidence", "q_reward_noticed", "q_ui_noticed",
    "q_attention", "q_suspicion", "q_finlit_interest", "q_finlit_inflation", "q_finlit_risk",
    "q_dospert_invest", "q_dospert_speculate", "q_dospert_gamble",
    # large JSON logs last
    "fee1_process_log", "fee2_process_log",
]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def custom_export(players):
    """
    oTree Data -> Custom export (cedarline): one analysis-ready row per participant.
    The claim token is deliberately NOT exported (it links to contact data).
    """
    yield ["participant_code"] + EXPORT_FIELDS
    for p in players:
        yield [p.participant.code] + [_cell(p.field_maybe_none(f)) for f in EXPORT_FIELDS]
