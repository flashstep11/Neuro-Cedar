"""Exact-arithmetic ledger for the sequential investment fraud experiment.
Money is in rupees as Fractions (no binary floats). F (fee) is configurable;
the reinvestment cap is derived as ENDOWMENT - COMMIT - F so the participant
can always afford the fee out of cash."""
from fractions import Fraction as Fr

ENDOWMENT = Fr(1000)
COMMIT = Fr(100)
STEP = Fr(50)

def cap(F):
    return ENDOWMENT - COMMIT - Fr(F)

def r_options(F):
    c = cap(F)
    n = int(c / STEP)
    return [STEP * i for i in range(n + 1)]

def platform_balance(g, R, r):
    """P = 100(1+g) + R(1+r); r applies to R only."""
    return COMMIT * (1 + Fr(g)) + Fr(R) * (1 + Fr(r))

def cash(R):
    return ENDOWMENT - COMMIT - Fr(R)

def final_balance(g, R, r, F, pay):
    C, P = cash(R), platform_balance(g, R, r)
    return C - Fr(F) + P if pay else C

def classify(g, R, r, F, pay):
    d = platform_balance(g, R, r) - Fr(F)
    if pay and d < 0:
        return "net_loss_payment"
    if (not pay) and d > 0:
        return "forgone_gain_abandonment"
    return "ok" if d != 0 else "indifferent"
