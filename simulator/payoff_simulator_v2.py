"""
payoff_simulator_v2.py — two reinvestment rounds + two-step withdrawal fee.

Enumerates every allowed (R1, R2), every pool outcome in both rounds, both
reward levels, every candidate pool and every candidate second fee F2, and
reports where participants' platform balances land relative to the fee ladder.

Run:  python simulator/payoff_simulator_v2.py      (writes simulator/output_v2.txt)

F2 SELECTION RULE
  v1 (written first): under the uniform reinvestment profile, averaged over both
  reward arms, for the active pool, pick the F2 closest to the targets
  Z0 (P < F2) = 15% and Z1 (trap) = 25%, measured as |Z0-.15| + |Z1-.25|.
  v1 picked F2 = 200, but it ignored the cost to the PRIMARY outcome: every
  extra Rs 50 of fee removes Rs 50 of reinvestment range (cap 500), and at
  F2 = 200 no investor can finish above a non-investor's Rs 900.
  v2 (revised 2026-11-08, before any participant data): apply v1 only among
  F2 values that keep the total cap >= MIN_CAP = 550. Ties -> smaller F2.
  v2 selects F2 = 150 (cap 550). Both versions are printed for transparency.
"""
import os
import sys
from fractions import Fraction as Fr
from itertools import product

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from logic.ledger import (total_cap, r1_options, r2_options, cash, platform_after_r1,
                          platform_balance, final_balance, zone, classify_step1,
                          classify_step2, START_CASH)
from logic.growth_pool import CANDIDATES, expected_return

F1 = 200
F2_CANDIDATES = [100, 150, 200]
GS = {"0%": Fr(0), "35%": Fr(35, 100)}
ACTIVE = "C_EV15"
TARGET_Z0, TARGET_Z1 = Fr(15, 100), Fr(25, 100)
MIN_CAP = 550
OUT = []


def say(s=""):
    OUT.append(s)


# ---------------------------------------------------------------------------
# Reinvestment profiles: probability weight over (R1, R2). These are NOT
# predictions of behaviour; they bracket plausible behaviour for planning.
# ---------------------------------------------------------------------------
def profile_uniform(F2):
    """R1 uniform over its options; R2 uniform over what remains."""
    o1 = r1_options(F1, F2)
    for R1 in o1:
        o2 = r2_options(R1, F1, F2)
        for R2 in o2:
            yield R1, R2, Fr(1, len(o1)) * Fr(1, len(o2))


def profile_single_round(F2):
    """R1 uniform, nobody reinvests in round 2."""
    o1 = r1_options(F1, F2)
    for R1 in o1:
        yield R1, Fr(0), Fr(1, len(o1))


def profile_moderate(F2):
    """R1 uniform on 100..300, R2 uniform on 0..200 (clipped to the cap)."""
    o1 = [R for R in r1_options(F1, F2) if 100 <= R <= 300]
    for R1 in o1:
        o2 = [R for R in r2_options(R1, F1, F2) if R <= 200]
        for R2 in o2:
            yield R1, R2, Fr(1, len(o1)) * Fr(1, len(o2))


PROFILES = {"uniform": profile_uniform, "single-round": profile_single_round,
            "moderate": profile_moderate}


def zone_shares(pool, g, F2, profile):
    z = {"Z0_below_F2": Fr(0), "Z1_trap": Fr(0), "Z2_worth_it": Fr(0)}
    below_F1 = Fr(0)
    for R1, R2, w in profile(F2):
        for (r1, p1), (r2, p2) in product(pool, pool):
            P = platform_balance(g, R1, r1, R2, r2)
            z[zone(P, F1, F2)] += w * p1 * p2
            if P < F1:
                below_F1 += w * p1 * p2
    return z, below_F1


def pct(x):
    return f"{float(x) * 100:5.1f}%"


# ---------------------------------------------------------------------------
# Hand-checked examples and invariants
# ---------------------------------------------------------------------------
def sanity():
    # Round-1 examples carried over from v1 (R2 = 0)
    assert platform_balance(0, 100, Fr(-3, 10)) == 170
    assert platform_balance(Fr(35, 100), 300, Fr(1, 5)) == 495
    # Two-round example, worked by hand:
    #   g=35%, R1=200 @ +50% -> 135 + 300 = 435 ; R2=100 @ -30% -> +70 => P=505
    #   cash = 900-200-100 = 600
    assert platform_balance(Fr(35, 100), 200, Fr(1, 2), 100, Fr(-3, 10)) == 505
    assert cash(200, 100) == 600
    # Paths with F1=200, F2=150:
    assert final_balance(Fr(35, 100), 200, Fr(1, 2), 100, Fr(-3, 10), 200, 150, False, False) == 600
    assert final_balance(Fr(35, 100), 200, Fr(1, 2), 100, Fr(-3, 10), 200, 150, True, False) == 400
    assert final_balance(Fr(35, 100), 200, Fr(1, 2), 100, Fr(-3, 10), 200, 150, True, True) == 755
    # Zones
    assert zone(100, 200, 150) == "Z0_below_F2"
    assert zone(150, 200, 150) == "Z1_trap"
    assert zone(349, 200, 150) == "Z1_trap"
    assert zone(350, 200, 150) == "Z2_worth_it"
    assert classify_step2(120, 150, True) == "escalation_payment"
    assert classify_step2(300, 150, False) == "forgone_gain_abandonment"
    assert classify_step1(250, 200, 150, True) == {"myopic": "ok", "full": "net_loss_payment"}

    for F2 in F2_CANDIDATES:
        cap = total_cap(F1, F2)
        for R1 in r1_options(F1, F2):
            for R2 in r2_options(R1, F1, F2):
                assert R1 + R2 <= cap
                assert cash(R1, R2) >= F1 + F2, "fees must always be affordable"
                for pool in CANDIDATES.values():
                    for (r1, _), (r2, _) in product(pool, pool):
                        assert platform_balance(0, R1, r1, R2, r2) >= 0
    for pool in CANDIDATES.values():
        assert sum(p for _, p in pool) == 1


def main():
    sanity()
    say("Payoff simulator v2 — two reinvestment rounds, two-step withdrawal fee")
    say(f"F1 = Rs {F1}; F2 candidates = {F2_CANDIDATES}; start cash = Rs {int(START_CASH)}")
    say("Sanity checks and hand-worked examples: PASSED")
    say()
    say("Zones at the fee stage (share of participants, by platform balance P):")
    say("  Z0  P < F2          paying the 2nd fee loses money even ignoring the 1st (pure escalation)")
    say("  Z1  F2 <= P < F1+F2 each fee looks worth paying, but the whole ladder loses money (trap)")
    say("  Z2  P >= F1+F2      paying both fees is financially better")
    say("  'P<F1' = would already be a net loss at step 1 even if no 2nd fee existed")
    say()

    choice = {}
    for name, pool in CANDIDATES.items():
        say(f"=== Pool {name}   E[r] = {float(expected_return(pool)):+.3f}   "
            f"outcomes {[f'{int(r * 100):+d}%' for r, _ in pool]} ===")
        for F2 in F2_CANDIDATES:
            cap = int(total_cap(F1, F2))
            say(f"-- F2 = Rs {F2}   total reinvestment cap = Rs {cap}")
            for pname, prof in PROFILES.items():
                cells = []
                avg = {"Z0_below_F2": Fr(0), "Z1_trap": Fr(0)}
                for gl, g in GS.items():
                    z, b1 = zone_shares(pool, g, F2, prof)
                    cells.append(f"{gl}: Z0 {pct(z['Z0_below_F2'])}  Z1 {pct(z['Z1_trap'])}  "
                                 f"Z2 {pct(z['Z2_worth_it'])}  P<F1 {pct(b1)}")
                    avg["Z0_below_F2"] += z["Z0_below_F2"] / 2
                    avg["Z1_trap"] += z["Z1_trap"] / 2
                say(f"   {pname:<13} " + " | ".join(cells))
                if name == ACTIVE and pname == "uniform":
                    choice[F2] = (abs(avg["Z0_below_F2"] - TARGET_Z0) + abs(avg["Z1_trap"] - TARGET_Z1), avg)
        say()

    # Apply the pre-registered selection rule
    best_v1 = min(F2_CANDIDATES, key=lambda f: (choice[f][0], f))
    eligible = [f for f in F2_CANDIDATES if total_cap(F1, f) >= MIN_CAP]
    best = min(eligible, key=lambda f: (choice[f][0], f))
    say(f"F2 selection (pool {ACTIVE}, uniform profile, averaged over reward arms):")
    for f in F2_CANDIDATES:
        d, avg = choice[f]
        tag = []
        if f == best_v1:
            tag.append("rule v1 pick")
        if f == best:
            tag.append("SELECTED (rule v2: cap >= %d)" % MIN_CAP)
        if f not in eligible:
            tag.append("excluded: cap %d < %d" % (int(total_cap(F1, f)), MIN_CAP))
        say(f"   F2={f:<4} cap {int(total_cap(F1, f))}  Z0 {pct(avg['Z0_below_F2'])}  Z1 {pct(avg['Z1_trap'])}  "
            f"distance {float(d):.3f}   " + "; ".join(tag))
    say()

    # Detail for the selected configuration
    F2 = best
    cap = total_cap(F1, F2)
    pool = CANDIDATES[ACTIVE]
    say(f"Detail for pool {ACTIVE}, F1={F1}, F2={F2}, total cap Rs {int(cap)}:")
    say("  Room left for round 2 after round 1 (R2 max = cap - R1):")
    say("   " + ", ".join(f"R1={int(R1)}->{int(cap - R1)}" for R1 in r1_options(F1, F2)))
    say("  Final balance range by path (all R1, R2, outcomes, both reward arms):")
    for label, p1, p2 in [("abandon at fee 1", False, False), ("pay fee 1, abandon fee 2", True, False),
                          ("pay both fees", True, True)]:
        vals = [final_balance(g, R1, r1, R2, r2, F1, F2, p1, p2)
                for g in GS.values() for R1 in r1_options(F1, F2) for R2 in r2_options(R1, F1, F2)
                for (r1, _), (r2, _) in product(pool, pool)]
        say(f"   {label:<26} Rs {int(min(vals))} .. Rs {int(max(vals))}   "
            f"(lottery weight {float(min(vals)) / 10:.1f} .. {float(max(vals)) / 10:.1f})")
    say("  E[final] if paying both fees only when P >= F1+F2, by R1 (R2=0), reward 0% / 35%:")
    for R1 in r1_options(F1, F2):
        row = []
        for g in GS.values():
            e = sum(p * (cash(R1) + max(platform_balance(g, R1, r) - F1 - F2, 0)) for r, p in pool)
            row.append(f"{float(e):7.1f}")
        say(f"   R1={int(R1):<4} " + "  ".join(row))

    text = "\n".join(OUT)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_v2.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
