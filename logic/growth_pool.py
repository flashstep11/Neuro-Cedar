from fractions import Fraction as Fr
# (return, probability) candidates -- PILOT/SIMULATION ONLY until frozen
CANDIDATES = {
    "A_EV0":  [(Fr(-30,100), Fr(1,2)), (Fr(30,100), Fr(1,2))],
    "B_EV5":  [(Fr(-30,100), Fr(1,2)), (Fr(40,100), Fr(1,2))],
    "C_EV15": [(Fr(-30,100), Fr(1,4)), (Fr(20,100), Fr(1,2)), (Fr(50,100), Fr(1,4))],
}
def expected_return(pool):
    return sum(r * p for r, p in pool)
