# Protocol Changes: Design v2

**Study:** Behavioral Sequences in App-Based Investment Frauds (Cedarline)
**Compared against:** *Implementation Guide: Sequential Investment Fraud Experiment* (change log 2026-11-04)
**Date:** 2026-11-08
**Status:** Built and tested. **Not yet approved.** Every item marked *Needs approval* must be signed off by the instructor and the ethics reviewer, and added to the preregistration, before pilot data are collected.

The 2 × 2 design, the random assignment and the **primary outcome (round-1 reinvestment R1)** are unchanged. The changes below extend what happens *after* R1, so they cannot affect it.

---

## 1. Summary of changes

| # | Change | Guide section affected | Status |
|---|---|---|---|
| 1 | Second reinvestment round (R2) after the first pool result | §2.2, §5 step 9–10, §12 | Needs approval |
| 2 | Withdrawal fee ladder: F1 = Rs 200, then F2 = Rs 150 only if F1 is paid | §2.3, §5 steps 11–13 | Needs approval |
| 3 | Total reinvestment cap Rs 550 across both rounds (was Rs 700, one round) | §2.2, §2.4, §5 step 4, quiz | Needs approval |
| 4 | Fee screens no longer pre-compute "final balance if you pay / abandon" | §2.3, §6 | Needs approval |
| 5 | Growth Pool switched to Candidate C (−30% / +20% / +50%, E[r] = +15%) | §3 | Aligns with guide (C is the named pilot candidate) |
| 6 | Pool outcomes pre-generated per cell **and round**, never replenished, index and version stored | §3 | Aligns with guide; fixes a deviation |
| 7 | Additional manipulative-arm cues (account manager, scarcity, reviews, FOMO line, sunk-cost line) | §6 | Needs approval |
| 8 | Second, non-binding countdown ("account freeze") on the F2 screen, manipulative arm only | §6 ("one countdown") | Needs approval; can be switched off |
| 9 | New process measures and post-task items | §5 step 14, §7 | Needs approval (exploratory) |
| 10 | Hypothetical real-money question after the fee ladder | §5 step 13 | Needs approval (exploratory) |
| 11 | Personalised "report card" debrief | §5 step 15 | Needs approval |

---

## 2. Financial ledger (replaces guide §2.2–2.3)

Exact arithmetic (Python `Fraction`) in `logic/ledger.py`.

- Cash after commitment: `C0 = 900`
- Reinvestments: `R1 ∈ {0, 50, …, 550}`; `R2 ∈ {0, 50, …, 550 − R1}`
- Platform balance: `P = 100(1+g) + R1(1 + r1) + R2(1 + r2)`
  Each pool return applies **only to its own round's amount**.
- Cash: `C = 900 − R1 − R2`

| Withdrawal path | Final balance W |
|---|---|
| Refuse F1 | `C` |
| Pay F1, refuse F2 | `C − 200` (forfeits P and loses the Rs 200 paid) |
| Pay F1 and F2 | `C − 350 + P` (balance released) |

**Invariant:** `R1 + R2 ≤ 550 = 900 − F1 − F2`, so both fees are affordable from cash at every allowed choice. This is checked in the simulator and in every bot test.

Lottery weight remains `W / 10` with fractional weights (guide §4).

**Worked example (checked by hand and in code):** g = 35%, R1 = 200 at +50%, R2 = 100 at −30%.
P = 135 + 300 + 70 = **505**, C = 600. Refuse F1 → 600; pay F1 only → 400; pay both → 600 − 350 + 505 = **755**.

## 3. Why the fee ladder (changes 2 and 4)

With one fee and the final balances printed on screen, the fee choice reduced to comparing two numbers. The guide itself warns that it is "not a pure measure of commitment" (§2.3). The ladder reproduces the escalation sequence of real advance-fee fraud and creates a clean test of **sunk-cost escalation**: at the F2 screen the Rs 200 is already spent, so the only forward-looking comparison is P vs F2.

Zones at the fee stage (`ledger.zone`):

- **Z0** `P < F2`: paying F2 loses money even ignoring F1. Paying here is pure escalation.
- **Z1 (trap)** `F2 ≤ P < F1+F2`: each fee looks worth paying, but the ladder as a whole loses money.
- **Z2** `P ≥ F1+F2`: paying both is financially better.

Step 1 is classified two ways: *myopic* (P vs F1, what the participant could see) and *full* (P vs F1+F2, hindsight).

Every statement on the fee screens is true inside the task. Step 1 says paying "continues processing" (not "releases"). Only step 2 says paying releases the balance. The "View fee terms" text states that "additional verification may be required." Pre-task instructions say withdrawals "may involve processing charges" (plural).

## 4. Choice of F2 and the cap (change 3)

`simulator/payoff_simulator_v2.py` → `simulator/output_v2.txt`. It enumerates every (R1, R2), both pool draws, both reward arms, three pools and F2 ∈ {100, 150, 200}.

- **Rule v1** (written first) picked F2 = 200 by closeness to target zone shares. It ignored the cost to the primary outcome: at F2 = 200 the cap falls to Rs 500, and no investor can finish above a non-investor's Rs 900.
- **Rule v2** (revised 2026-11-08, **before any participant data**) applies v1 only among options that keep the cap ≥ Rs 550. It selects **F2 = 150**. Both rules are printed in the output.

Key consequence, to state in the ethics form and paper: **once both fees are counted, reinvesting rarely pays off** (the best possible final balance is Rs 960, and in hindsight R = 0 maximises the expected final balance). This mirrors real fraud. Because the fees are not disclosed in advance, the guide's interpretation of R as commitment/risk-taking at the time of the decision still holds (§3). The debrief explains this explicitly.

Planning estimate for the share landing in net-loss territory: about 17% if round 2 stays small (inside the guide's 15–20% pilot target), but lower if people reinvest heavily in both rounds. **Re-run the simulator after the pilot** with real R1/R2 and retune F2 in `config.py` if needed.

## 5. Pool assignment (changes 5 and 6)

`pool_sequence.py`:

- Generated once at startup on the persistent disk, 160 outcomes per (cell × round).
- Balanced blocks of 4 (one −30%, two +20%, one +50%), each shuffled with `random.SystemRandom`.
- Outcomes are assigned in order, only after the reinvestment is submitted, and **only if that round's amount is > 0**.
- **Never replenished.** An exhausted queue raises an error, and extending it is a protocol change.
- The sequence index and version are stored per participant. The admin report shows usage per queue.
- A changed pool or length refuses to start rather than mixing sequences.

The previous code topped up the sequence when it ran out and did not record positions, which contradicted guide §3.

## 6. Interface bundle (changes 7 and 8)

Still **one bundled treatment**, identical in both reward arms. No cue mentions returns, amounts, percentages or 35%. Financial facts, options and the rise/fall disclosure are word-for-word identical across UI arms.

| Cue | Where (manipulative arm only) |
|---|---|
| 60 s non-binding countdown ("Window extended" at zero) | S4 only (unchanged rule) |
| Live investor count, activity card, pop-up toasts | S1–W4 (toasts **disabled on fee screens**, so a toast can never cover one option) |
| Silver → Gold status card, fixed at 72% | S1–S6 |
| "9 out of 10 Gold members reinvest", "Only 3 Gold slots left" | S4, S6 |
| Scripted "account manager" messages (no return promises) | S4, S6, W2, W3 |
| Member reviews (no amounts) | S5 |
| "Don't miss this cycle" | S6 |
| "Don't lose the Rs 200 you've already paid!" | W3 (both arms see the neutral fact "Fees paid so far: Rs 200") |
| **Second countdown:** "Account freeze in 01:00", non-binding ("Freeze deadline extended" at zero) | W3; `FREEZE_TIMER_ENABLED` in `config.py` (set `False` if one timer is required) |

Deliberately **not** used: pre-selected amounts, return promises or "guarantees", fake regulators or certificates, guilt-trip wording on the abandon button.

Both arms share the same phone-app shell and the same "processing" sequences before each fee, so the contrast is a legitimate app versus a scam app, not a plain page versus an app.

## 7. New measures (changes 9 and 10): all exploratory

| Measure | Field(s) |
|---|---|
| Round-2 amount, and its pool result | `reinvest2_amount`, `pool2_return_*` |
| Fee path | `fee1_paid`, `fee2_paid`, `fees_paid_total`, `funds_released` |
| Classifications | `zone_at_fee`, `step1_flag_myopic`, `step1_flag_full`, `step2_flag` |
| Seconds left on the S4 countdown / freeze countdown at submit | `s4_timer_left_at_submit`, `fee2_timer_left_at_submit` |
| Reinvestment events (changes, disclosure on screen, tab switches) | `s4_event_log`, `s6_event_log` |
| Fee-screen process data: pointer path, hovers, terms/support opened, tab switches | `fee1_process_log`, `fee2_process_log`, `fee*_terms_opened`, `fee*_support_clicks` |
| Retrospective sureness that paying would release the balance (0–100) | `q_sure_fee1`, `q_sure_fee2` |
| Intended real-world action | `q_realworld` |
| Hypothetical real-money payment (intention 1–5, maximum Rs) | `hyp_real_pay`, `hyp_real_max` |

Sureness is asked **afterwards** on purpose: asking before the decision would change the decision. Mouse-tracking uses stacked options, not the standard two-corner layout, so treat it as descriptive.

## 8. Analysis notes for the preregistration

- **Primary:** R1. Unchanged model (OLS, HC3) and hypotheses.
- **Round 2:** R2, or R2 as a share of the remaining cap (`550 − R1`), by round-1 outcome (loss / moderate / high) and condition. The round-1 outcome is random and independent of condition.
- **Fee ladder:** to avoid post-treatment selection, the confirmatory or secondary fee outcomes are **unconditional, on the full randomised sample**: paid both; fees paid (0 / 1 / 2); escalation payment (paid F2 with P < F2). Analyses conditional on reaching step 2 are descriptive only.
- **Report** pool-sequence version and index, and any exhausted queue.

## 9. Verification

- `simulator/payoff_simulator_v2.py`: invariants and hand-worked examples pass.
- `otree test` on all five session configs × five withdrawal-path cases (25 sessions). Final balance, fees, release, zone, flags and lottery weight match `logic.ledger` exactly. Skipped pages are skipped correctly.
- Real-browser runs (Edge) for all three withdrawal paths, in both UI arms and at phone and desktop widths. Data written to the database match the ledger exactly, and there were no console errors.

## 10. Still open

- Instructor and ethics approval for items 1–4 and 7–11 above.
- Lottery draw script (four sequential weighted draws without replacement, seeded), and claim instructions in the debrief (draw date, 7-day claim window, redraw rule).
- Move file-based state (assignment, pool sequence, lottery contacts) to Postgres before the main study.
- Re-run the simulator with pilot data and confirm F2 and the cap.
