import sys, os, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fractions import Fraction as Fr
from logic.ledger import *
from logic.growth_pool import CANDIDATES, expected_return

GS = {"0%": Fr(0), "35%": Fr(35, 100)}
FEES = [200, 250, 300]

def netloss_counts(pool, g, F):
    return [sum(1 for R in r_options(F) if platform_balance(g, R, r) < F) for r, _ in pool]

def e_w_best(pool, g, R, F):
    """E[final] if participant pays only when P>F (known at fee stage)."""
    return sum(p * (cash(R) + max(platform_balance(g, R, r) - F, 0)) for r, p in pool)

def p_net_loss_zone(pool, g, R, F):
    return sum(p for r, p in pool if platform_balance(g, R, r) < F)

def sanity():
    # hand-checked examples
    assert platform_balance(0, 100, Fr(-3,10)) == 170
    assert final_balance(0, 100, Fr(-3,10), 200, True) == 770
    assert final_balance(0, 100, Fr(-3,10), 200, False) == 800
    assert platform_balance(Fr(35,100), 300, Fr(1,5)) == 495
    assert final_balance(Fr(35,100), 300, Fr(1,5), 200, True) == 895
    for F in FEES:                       # fee always affordable at every R
        assert all(cash(R) >= F for R in r_options(F))
    for pool in CANDIDATES.values():     # probs sum to 1, platform never negative
        assert sum(p for _, p in pool) == 1
        assert all(platform_balance(0, R, r) >= 0 for R in r_options(200) for r, _ in pool)

def main():
    sanity()
    print("Sanity checks passed.\n")
    for name, pool in CANDIDATES.items():
        print(f"=== Pool {name}  E[r] = {float(expected_return(pool)):+.3f} ===")
        for F in FEES:
            opts = r_options(F)
            print(f"-- F={F}, cap={int(cap(F))}, {len(opts)} options")
            for gl, g in GS.items():
                nl = netloss_counts(pool, g, F)
                best = max(opts, key=lambda R: e_w_best(pool, g, R, F))
                print(f"   reward {gl}: net-loss option counts per outcome {nl}; "
                      f"R maximizing E[final] (if pay when P>F) = {int(best)}")
        print()
    # Detail table for one pool: E[final] by R
    F = 200
    print("E[final balance] by R, F=200, paying only when P>F (rows R, cols pool/reward):")
    hdr = "R    " + "  ".join(f"{n}-{gl}".ljust(11) for n in CANDIDATES for gl in GS)
    print(hdr)
    for R in r_options(F):
        row = [f"{float(e_w_best(p, g, R, F)):.0f}".ljust(11) for p in CANDIDATES.values() for g in GS.values()]
        print(f"{int(R):<5}" + "  ".join(row))

if __name__ == "__main__":
    main()
