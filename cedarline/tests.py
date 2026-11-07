"""
tests.py — oTree bot tests for the Cedarline study (v2: two rounds + fee ladder).

Each test case walks the full flow along one withdrawal path and checks, against
logic.ledger (exact Fractions):
  - final balance, fees paid, release, zone, step-1/step-2 flags, lottery weight
  - invariants: both fees affordable at the chosen R1+R2; platform balance >= 0
  - pages that should be skipped are skipped (S7 when R2 = 0, W3 when F1 refused)
  - pool outcomes come from the pre-generated sequence (index + version stored)
  - the quiz is passed only through the real server-side grading
  - no contact data on the Player model

Run every case in every cell with:  otree test <session_config>
"""
import os
import sys
from fractions import Fraction as Fr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from otree.api import Bot, Submission, expect
from cedarline import (
    C, ContentWarning, Instructions, Consent, ComprehensionQuiz, Assignment,
    S1Endowment, S2Commitment, S3ReturnReveal, S4Reinvestment, S5PoolOutcome,
    S6Reinvest2, S7PoolOutcome2, W1Withdraw, W2Fee1, W3Fee2, W4Outcome,
    HypotheticalRealMoney, PostTask, LotteryContact, Debrief,
)
from logic import ledger
from config import F1, F2, LOTTERY_WEIGHT_DIVISOR


def call_live_method(method, group, page_class, **kwargs):
    """
    oTree calls this once per group per live page. The quiz can only be left
    after server-side grading, so bots answer it through the real live_method.
    """
    if page_class.__name__ == "ComprehensionQuiz":
        for p in group.get_players():
            reply = method(p.id_in_group, {"action": "submit_quiz", **C.QUIZ_CORRECT})
            assert reply and reply[p.id_in_group]["status"] == "pass", reply


def _frac(num, den):
    return Fr(0) if num is None else Fr(num, den)


class PlayerBot(Bot):
    # (R1, R2, pay fee 1, pay fee 2) — one full session per case
    cases = [
        {"name": "two_rounds_pay_both",   "R1": 300, "R2": 100, "pay1": True,  "pay2": True},
        {"name": "no_invest_refuse_fee1", "R1": 0,   "R2": 0,   "pay1": False, "pay2": None},
        {"name": "pay1_stop_at_fee2",     "R1": 200, "R2": 0,   "pay1": True,  "pay2": False},
        {"name": "max_round1_pay_both",   "R1": C.CAP, "R2": 0, "pay1": True,  "pay2": True},
        {"name": "round2_only_refuse",    "R1": 0,   "R2": 250, "pay1": False, "pay2": None},
    ]

    def play_round(self):
        case = self.case
        R1, R2, pay1, pay2 = case["R1"], case["R2"], case["pay1"], case["pay2"]

        yield Submission(ContentWarning, {"exit_code": ""}, check_html=False)
        yield Submission(Instructions, {}, check_html=False)
        yield Submission(Consent, {}, check_html=False)
        yield Submission(ComprehensionQuiz, {}, check_html=False)
        assert self.player.quiz_passed, "quiz must be passed via server-side grading"
        yield Submission(Assignment, {}, check_html=False)

        yield Submission(S1Endowment, {}, check_html=False)
        yield Submission(S2Commitment, {}, check_html=False)
        yield Submission(S3ReturnReveal, {}, check_html=False)
        yield Submission(S4Reinvestment, {"reinvest_amount": R1}, check_html=False)
        if R1 > 0:
            assert self.player.pool_return_num is not None and self.player.pool1_seq_index is not None
        else:
            assert self.player.field_maybe_none("pool_return_num") is None, "no draw when R1 = 0"
        yield Submission(S5PoolOutcome, {}, check_html=False)
        yield Submission(S6Reinvest2, {"reinvest2_amount": R2}, check_html=False)
        if R2 > 0:
            assert self.player.pool2_return_num is not None
            yield Submission(S7PoolOutcome2, {}, check_html=False)

        yield Submission(W1Withdraw, {}, check_html=False)
        yield Submission(W2Fee1, {"fee1_decision_str": "pay" if pay1 else "abandon",
                                  "fee1_process_log": '{"v":2,"events":[[120,"terms_open"],[900,"terms_close"]]}'},
                         check_html=False)
        assert self.player.fee1_terms_opened == 1 and self.player.fee1_support_clicks == 0
        if pay1:
            yield Submission(W3Fee2, {"fee2_decision_str": "pay" if pay2 else "abandon",
                                      "fee2_process_log": ""}, check_html=False)
        yield Submission(W4Outcome, {}, check_html=False)
        yield Submission(HypotheticalRealMoney, {"hyp_real_pay": 2, "hyp_real_max": 0}, check_html=False)

        # ---- Ledger checks (exact) ----
        p = self.player
        g = Fr(35, 100) if p.reward_condition == "35pct" else Fr(0)
        r1 = _frac(p.field_maybe_none("pool_return_num"), p.pool_return_den)
        r2 = _frac(p.field_maybe_none("pool2_return_num"), p.pool2_return_den)
        P = ledger.platform_balance(g, R1, r1, R2, r2)
        W = ledger.final_balance(g, R1, r1, R2, r2, F1, F2, pay1, bool(pay2))

        expect(p.platform_balance_decision, "==", int(P))
        expect(p.final_balance_int, "==", int(W))
        expect(p.fees_paid_total, "==", int(ledger.fees_paid(F1, F2, pay1, bool(pay2))))
        expect(bool(p.funds_released), "==", bool(pay1 and pay2))
        expect(p.zone_at_fee, "==", ledger.zone(P, F1, F2))
        flags = ledger.classify_step1(P, F1, F2, pay1)
        expect(p.step1_flag_myopic, "==", flags["myopic"])
        expect(p.step1_flag_full, "==", flags["full"])
        expect(p.step2_flag, "==", ledger.classify_step2(P, F2, bool(pay2)) if pay1 else "")
        assert abs(p.lottery_weight - max(0.0, float(W) / LOTTERY_WEIGHT_DIVISOR)) < 0.01
        if not pay1:
            assert p.field_maybe_none("fee2_paid") is None, "step 2 must be skipped after refusing fee 1"

        # Invariants
        assert R1 + R2 <= C.CAP
        assert ledger.cash(R1, R2) >= F1 + F2, "both fees must be affordable"
        assert P >= 0
        assert p.claim_token, "claim token created when the ledger closes"
        for field_name in ["name", "email", "phone", "contact_name", "contact_email", "contact_phone"]:
            assert not hasattr(p, field_name), f"PII field '{field_name}' on Player"

        post = {
            "q_sure_fee1": 50, "q_realworld": "support,report",
            "q_trust": 4, "q_legitimacy": 4, "q_risk": 4, "q_confidence": 4,
            "q_reward_noticed": "no", "q_ui_noticed": "no", "q_attention": 4, "q_suspicion": "",
            "q_finlit_interest": "more_102", "q_finlit_inflation": "less", "q_finlit_risk": "false",
            "q_dospert_invest": 4, "q_dospert_speculate": 3, "q_dospert_gamble": 2,
        }
        if pay1:
            post["q_sure_fee2"] = 30
        yield Submission(PostTask, post, check_html=False)
        expect(self.player.q_realworld, "==", "support,report")
        if pay1:
            expect(self.player.q_sure_fee2, "==", 30)

        yield Submission(LotteryContact, {"lottery_opt_out_str": "0"}, check_html=False)
        yield Submission(Debrief, {}, check_html=False)

        p = self.player
        assert p.is_completed, "should be completed after Debrief"
        assert p.stage_reached == "Debrief"
        assert p.completion_ts is not None
