"""Exact-arithmetic ledger for the sequential investment fraud experiment (v2).

Money is in rupees as Fractions (no binary floats).

Sequence
--------
  Endowment 1000 -> fixed commitment 100 -> apparent return g on the 100
  -> reinvestment R1 -> pool outcome r1 (applies to R1 only)
  -> reinvestment R2 -> pool outcome r2 (applies to R2 only)
  -> withdrawal fee ladder: F1, then (only if F1 was paid) F2
  -> release of the platform balance only if BOTH fees are paid.

Balances
--------
  cash C            = 900 - R1 - R2
  platform P        = 100(1+g) + R1(1+r1) + R2(1+r2)

Final balance W by withdrawal path
  abandon at step 1 : W = C
  pay F1, abandon 2 : W = C - F1                (loses F1 AND forfeits P)
  pay F1 and F2     : W = C - F1 - F2 + P

Invariant: R1 + R2 <= TOTAL_CAP = 900 - F1 - F2, so the participant can always
afford both fees from cash at every allowed choice.
"""
from fractions import Fraction as Fr

ENDOWMENT = Fr(1000)
COMMIT = Fr(100)
STEP = Fr(50)
START_CASH = ENDOWMENT - COMMIT          # 900


# ---------------------------------------------------------------------------
# Caps and options
# ---------------------------------------------------------------------------
def total_cap(F1, F2):
    """Most cash that may be moved into the pool across both rounds."""
    return START_CASH - Fr(F1) - Fr(F2)


def _steps(limit):
    n = int(Fr(limit) / STEP)
    return [STEP * i for i in range(n + 1)]


def r1_options(F1, F2):
    return _steps(total_cap(F1, F2))


def r2_options(R1, F1, F2):
    return _steps(total_cap(F1, F2) - Fr(R1))


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------
def cash(R1, R2=0):
    return START_CASH - Fr(R1) - Fr(R2)


def platform_after_reward(g):
    return COMMIT * (1 + Fr(g))


def platform_after_r1(g, R1, r1):
    """P after round 1: 100(1+g) + R1(1+r1)."""
    return platform_after_reward(g) + Fr(R1) * (1 + Fr(r1))


def platform_balance(g, R1, r1, R2=0, r2=0):
    """Final P: 100(1+g) + R1(1+r1) + R2(1+r2). Each return applies to its own round only."""
    return platform_after_r1(g, R1, r1) + Fr(R2) * (1 + Fr(r2))


# ---------------------------------------------------------------------------
# Withdrawal ladder
# ---------------------------------------------------------------------------
def fees_paid(F1, F2, paid1, paid2):
    return (Fr(F1) if paid1 else 0) + (Fr(F2) if (paid1 and paid2) else 0)


def released(paid1, paid2):
    return bool(paid1 and paid2)


def final_balance(g, R1, r1, R2, r2, F1, F2, paid1, paid2):
    C = cash(R1, R2)
    P = platform_balance(g, R1, r1, R2, r2)
    return C - fees_paid(F1, F2, paid1, paid2) + (P if released(paid1, paid2) else 0)


def zone(P, F1, F2):
    """
    Where the platform balance P sits relative to the fee ladder.
      'Z0_below_F2'  P <  F2       : paying F2 is a net loss even ignoring the sunk F1
      'Z1_trap'      F2 <= P < F1+F2: each payment looks locally worth it, but the
                                      whole ladder loses money (classic fraud trap)
      'Z2_worth_it'  P >= F1+F2    : paying both fees is financially better overall
    """
    P, F1, F2 = Fr(P), Fr(F1), Fr(F2)
    if P < F2:
        return "Z0_below_F2"
    if P < F1 + F2:
        return "Z1_trap"
    return "Z2_worth_it"


def classify_step1(P, F1, F2, paid1):
    """
    Step-1 flags. 'myopic' compares P with F1 only (what the participant can see);
    'full' compares P with F1+F2 (the whole ladder, known only in hindsight).
    """
    P = Fr(P)
    myopic_gap = P - Fr(F1)
    full_gap = P - Fr(F1) - Fr(F2)
    def flag(gap):
        if paid1 and gap < 0:
            return "net_loss_payment"
        if (not paid1) and gap > 0:
            return "forgone_gain_abandonment"
        return "ok" if gap != 0 else "indifferent"
    return {"myopic": flag(myopic_gap), "full": flag(full_gap)}


def classify_step2(P, F2, paid2):
    """
    Step-2 flag (only meaningful if F1 was paid). F1 is sunk, so the only
    forward-looking comparison is P vs F2.
      'escalation_payment'       paid F2 although P < F2
      'forgone_gain_abandonment' refused F2 although P > F2 (also forfeits the paid F1)
    """
    gap = Fr(P) - Fr(F2)
    if paid2 and gap < 0:
        return "escalation_payment"
    if (not paid2) and gap > 0:
        return "forgone_gain_abandonment"
    return "ok" if gap != 0 else "indifferent"
