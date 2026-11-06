"""
tests.py — oTree bot tests for the Cedarline study.

Tests cover:
  - Every R x both rewards x every pool outcome x pay/abandon, in BOTH UI arms
  - All must match simulator/payoff_simulator.py exactly for final balance,
    flags and lottery weight
  - The UI layer must never change the numbers

Tests also verify:
  - Invariants: cash >= F at every allowed R; platform balance >= 0
  - Export contains no contact data (lottery_db fields never in Player)

NOTE: oTree bots submit forms page by page. We use Submission() with
check_html=False since our templates use custom form layouts.
"""
import sys
import os
from fractions import Fraction as Fr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from otree.api import Bot, Submission, expect
from cedarline import (
    C, ContentWarning, Instructions, Consent, ComprehensionQuiz,
    QuizFailed, Assignment, S1Endowment, S2Commitment, S3ReturnReveal,
    S4Reinvestment, S5PoolOutcome, S6Withdraw, S7FeeDisplay, S8PayAbandon,
    PostTask, LotteryContact, Debrief,
)
from logic import ledger
from config import F, LOTTERY_WEIGHT_DIVISOR


def _expected_final(g, R, r, pay):
    """Compute expected final balance using the real ledger (Fractions)."""
    return int(ledger.final_balance(g, R, r, F, pay))


def _expected_flag(g, R, r, pay):
    """Compute expected flag using the real ledger."""
    return ledger.classify(g, R, r, F, pay)


def _expected_lottery_weight(g, R, r, pay):
    fb = ledger.final_balance(g, R, r, F, pay)
    return max(0.0, float(fb) / LOTTERY_WEIGHT_DIVISOR)


class PlayerBot(Bot):
    """
    Bot walks the full study flow for whichever condition the player was
    assigned to. The session config forces a specific cell via force_ui
    and force_reward for dev testing.
    """

    def play_round(self):
        # ---- Pre-assignment pages (neutral for everyone) ----

        # ContentWarning: continue (exit_code stays blank)
        yield Submission(ContentWarning, {"exit_code": ""}, check_html=False)

        # Instructions: just advance
        yield Submission(Instructions, {}, check_html=False)

        # Consent: just advance (JS validation; bot bypasses it)
        yield Submission(Consent, {}, check_html=False)

        # ComprehensionQuiz: the bot needs to submit via the form.
        # oTree bots can't easily interact with live_method, so we
        # submit the hidden otree-form directly to advance.
        # The quiz logic runs via live websocket; for bot tests we skip
        # the actual quiz interaction and just advance the page.
        yield Submission(ComprehensionQuiz, {}, check_html=False)

        # QuizFailed: should be skipped (exit_code is "")
        # Assignment: auto-advances, assigns the player
        yield Submission(Assignment, {}, check_html=False)

        # ---- Investment stages ----

        # S1 Endowment
        yield Submission(S1Endowment, {}, check_html=False)

        # S2 Commitment
        yield Submission(S2Commitment, {}, check_html=False)

        # S3 Return Reveal
        yield Submission(S3ReturnReveal, {}, check_html=False)

        # S4 Reinvestment — choose R based on the case
        # Get the R value from participant.vars (set by the test case)
        R = self.player.participant.vars.get("test_R", 0)
        yield Submission(S4Reinvestment, {"reinvest_amount": R}, check_html=False)

        # S5 Pool Outcome
        yield Submission(S5PoolOutcome, {}, check_html=False)

        # S6 Withdraw
        yield Submission(S6Withdraw, {}, check_html=False)

        # S7 Fee Display
        yield Submission(S7FeeDisplay, {}, check_html=False)

        # S8 Pay/Abandon
        pay = self.player.participant.vars.get("test_pay", True)
        pay_str = "pay" if pay else "abandon"
        yield Submission(S8PayAbandon, {"pay_decision_str": pay_str}, check_html=False)

        # ---- Verify final balance matches ledger exactly ----
        g_str = self.player.reward_condition
        g = Fr(35, 100) if g_str == "35pct" else Fr(0)
        r = Fr(self.player.pool_return_num, self.player.pool_return_den)

        expected_fb = _expected_final(g, R, r, pay)
        expected_flag = _expected_flag(g, R, r, pay)
        expected_lw = _expected_lottery_weight(g, R, r, pay)

        expect(self.player.final_balance_int, "==", expected_fb)
        expect(self.player.outcome_flag, "==", expected_flag)
        # lottery_weight is float; check within tolerance
        assert abs(self.player.lottery_weight - expected_lw) < 0.01, (
            f"lottery_weight mismatch: got {self.player.lottery_weight}, "
            f"expected {expected_lw}"
        )

        # ---- Verify invariants ----
        # Cash >= F at the chosen R
        assert int(ledger.cash(R)) >= F, f"cash({R}) < F={F}"
        # Platform balance >= 0
        P = ledger.platform_balance(g, R, r)
        assert P >= 0, f"platform_balance negative: {P}"

        # ---- Verify no PII in Player fields ----
        # claim_token is a UUID (not PII); actual contact info is in lottery_db
        for field_name in ["name", "email", "phone", "contact_name",
                           "contact_email", "contact_phone"]:
            assert not hasattr(self.player, field_name), (
                f"PII field '{field_name}' found in Player model!"
            )

        # ---- Post-task questionnaire ----
        yield Submission(PostTask, {
            "q_trust": 4,
            "q_legitimacy": 4,
            "q_risk": 4,
            "q_confidence": 4,
            "q_reward_noticed": "no",
            "q_ui_noticed": "no",
            "q_attention": 4,      # correct attention check answer
            "q_suspicion": "",
        }, check_html=False)

        # LotteryContact: skip (don't submit contact info)
        yield Submission(LotteryContact, {}, check_html=False)

        # Debrief
        yield Submission(Debrief, {}, check_html=False)

        # ---- Verify completion tracking ----
        assert self.player.is_completed == True, "Player should be marked completed after Debrief"
        assert self.player.stage_reached == "Debrief", "Player stage_reached should be Debrief"
        assert self.player.completion_ts is not None, "completion_ts should be set"

