# Finalized Research and Implementation Pipeline

> **Change log (2026-11-04):** Reframed fee outcomes and power; made the fee tunable with a derived reinvestment cap; expanded pool simulation and pilot criteria; clarified reward salience, withdrawal staging, cap rationale, architecture, and reconciliation with the approach paper.

**Study:** Behavioral Sequences in App-Based Investment Frauds  
**Basis:** Team 5 approach paper, original design notes, and the proposed protocol decision sheet  
**Protocol status:** Core design and accounting rules selected; pool distribution, incentive administration, and deception remain subject to simulation, pilot, and instructor/institutional approval.

## 1. Final design decision

Use a 2 × 2 between-subjects factorial design. Each participant is assigned once to one condition:

| | 0% initial apparent return | 35% initial apparent return |
|---|---|---|
| Neutral UI | 1 | 2 |
| Manipulative UI | 3 | 4 |

The primary behavioral outcome is the amount reinvested after the initial feedback. The later withdrawal-fee decision is secondary because its financially optimal choice depends directly on the balance participants see. The manipulative interface is one bundled treatment; this design cannot identify the individual effects of its timer, social proof, and progress cues.

The financial sequence is: ₹1,000 virtual endowment → fixed ₹100 investment → 0% or 35% apparent return on that ₹100 → participant-selected reinvestment → independently generated Growth Pool outcome → ₹200 processing fee → pay or abandon.

## 2. Financial ledger to implement

Use two server-side balances: available cash `C` and platform balance `P`. Keep calculations in integer paise or exact decimal arithmetic; do not use binary floating point for money.

### 2.1 Start and initial return

At the start, `C = ₹1,000` and `P = ₹0`. The fixed ₹100 commitment transfers from cash to the simulated platform:

- After commitment: `C = ₹900`, `P = ₹100`.
- Let `g = 0` in the 0% condition and `g = 0.35` in the 35% condition.
- After the displayed initial return: `P = ₹100 × (1 + g)`, so the platform shows ₹100 or ₹135. Cash remains ₹900.

Show the platform balance prominently (for example, ?135) with identical placement, size, and layout in both reward arms; change only the return and resulting value. Add a post-task reward-noticed check. Explain in the debrief that the apparent ₹35 gain was simulated. It increases displayed virtual wealth, so the reward manipulation combines positive feedback with a wealth change; acknowledge this in the report.

### 2.2 Reinvestment and pool outcome

The participant chooses `R ∈ {₹0, ₹50, …, ₹700}`. This is transferred from available cash into the Growth Pool. The ₹700 ceiling is a platform limit, not a fee reserve. The participant has enough cash to pay the later ₹200 fee at every allowed `R`.

Before pool resolution:

- `C = ₹900 − R`
- `P_before = ₹100 × (1 + g) + R`

Let `r` be the Growth Pool return. After resolution:

- `C = ₹900 − R`
- `P = ₹100 × (1 + g) + R × (1 + r)`

The pool return applies only to `R`; it does not apply again to the original ₹100. The same formula applies in all four conditions. Generate and persist the outcome on the server, independently of reward assignment, UI assignment, and `R`. Refreshes and retries must return the stored outcome, never a new draw. Never select an outcome based on the reinvestment decision.

### 2.3 Fee and final balance

Use one label throughout: **withdrawal processing fee**. Set `F = ₹200` (20% of the original ₹1,000 endowment). Deduct it from remaining cash, not from the platform balance.

- **Pay:** deduct ₹200 from cash and release the entire platform balance. `W_pay = C − ₹200 + P = ₹700 − R + P`.
- **Abandon:** do not pay; retain remaining cash and forfeit the platform balance. `W_abandon = C = ₹900 − R`.

The difference is `W_pay − W_abandon = P − ₹200`. Therefore:

- Pay with `P < ₹200`: net-loss payment.
- Abandon with `P > ₹200`: forgone-gain abandonment.
- `P = ₹200`: financially indifferent.

Record the platform balance at the fee decision so these classifications can be calculated from the same ledger. Do not present them as psychological categories or treat the fee choice as a pure measure of commitment.

The candidate pool's lowest platform values remain nonnegative, and the ₹700 reinvestment cap leaves at least ₹200 cash for the fee. Preserve these as invariants in the simulator and application. Do not silently add a balance cap; the lottery rule below accommodates a possible final balance above ₹1,000.

### 2.4 Participant-facing balance explanation

Explain the ₹1,000 endowment and fixed ₹100 commitment clearly. State that the participant may transfer ₹0–₹700, in ₹50 increments, from available cash into the simulated investment. Explain that the investment value may rise or fall and that the resulting value is shown at withdrawal. Do not describe the ₹700 maximum as money held back for a fee. All instructions and displayed balances must agree with the equations above.

## 3. Growth Pool decision: candidate, not yet frozen

Compare at least three candidate distributions in the simulator, targeting expected returns `E[r]` of about 0%, +5%, and +15%. The distribution below can serve as the +15% candidate for payoff simulation and pilot only:

| Pool outcome | Return | Probability |
|---|---:|---:|
| Negative | −30% | 25% |
| Moderate gain | +20% | 50% |
| High gain | +50% | 25% |

Its expected return is +15%. Do not call it final until all candidates and the pilot have been reviewed. Select using low pile-up at `R=0` and the cap, enough variance in `R`, and an adequate share in net-loss territory (`P < F`). If `E[r] > 0`, interpret `R` as commitment/risk-taking, not irrational escalation. The older 50% chance of +40% and 50% chance of −30% is not the selected candidate.

For the research question, the proposed participant disclosure is that the value of reinvested funds may increase or decrease and the resulting value will appear at withdrawal, without stating exact odds. This is limited disclosure and requires approval. Do not tell participants that initial reward predicts pool outcomes; in fact, it does not. Debrief that the pool was controlled and random, its outcome did not depend on initial reward, and the interface elements were simulated. If the instructor requires disclosure of exact odds, use the approved disclosed-risk version and update the interpretation/preregistration before data collection.

For outcome allocation, generate a sufficiently long sequence before recruitment, separately for each condition, with each four-outcome block containing one −30%, two +20%, and one +50%, then securely shuffle the order. Conceal sequence position, assign the next unused outcome only after reinvestment submission, and record sequence version/index. Do not recycle unused outcomes or replenish a depleted sequence during collection. This produces approximate balance by condition while randomizing order; document that draws are balanced-sequence assignments rather than independent with-replacement draws. Any change to this method requires a protocol update.

### Required payoff simulation

Before building production screens, enumerate both reward levels, all allowed reinvestment amounts for each configured `F`, all outcomes in at least three candidate distributions, both fee choices, and every resulting final balance. Verify examples independently by hand. Calculate:

- Expected final balance and variance by reinvestment amount and condition.
- Frequency with which paying is financially better, worse, or indifferent.
- Expected lottery weight under each choice.
- Values of `R` where fee decisions switch financial advantage.
- Whether the candidate creates substantial zero or maximum reinvestment concentration.

Run the simulator again after any pilot change. Archive the code, output, and decision explaining why the final distribution was selected.

## 4. Lottery rule

Recommended prize structure: four unique winners, each receiving a ₹250 voucher; total budget ₹1,000. Define participant weight as `final balance / 10` (₹10 per weight unit), allowing fractional weights. Examples: ₹590 → 59; ₹1,185 → 118.5. Do not round down.

Run four sequential weighted draws without replacement after collection closes, using a documented and reproducible draw procedure. The initial selection probability is proportional to weight; with multiple winners drawn without replacement, a participant's overall chance of appearing among four winners is not simply their weight divided by the total weight. Avoid promising a fixed individual probability. Set eligibility, one-session rule, draw date, contact/claim method, seven-calendar-day claim period, and redraw rule for unclaimed prizes before recruitment. Keep contact data separate from behavioral data, linked only by a claim token. Obtain instructor/institutional approval before announcing the lottery.

Participant-facing explanation should say that final virtual balance determines lottery weight, define the conversion, specify four ₹250 vouchers, and state that no deposit or payment is required. Show this before consent.

## 5. Final participant flow

1. **Entry and eligibility:** adults aged 18 or older; one valid session per person. Give study description, estimated duration, voluntary participation, privacy/contact details, voucher mechanics, and withdrawal procedure.
2. **Consent:** disclose that this is a simulated digital investment task, all task balances and charges are virtual, and no real money is deposited or required. If approved, explain that some details of the simulated process will be withheld until debrief. Provide a study withdrawal code and a clear withdrawal deadline/process.
3. **General instructions and comprehension:** explain the endowment, fixed initial commitment, reinvestment range, possible increase/decrease, and lottery weight. Do not reveal exact hypotheses. Do not reveal the surprise fee amount before its task stage if limited disclosure is approved. Consent must still disclose the possibility of simulated charges at a level approved by the ethics reviewer.
4. **Comprehension quiz, before assignment:** four questions: initial investment (₹100), maximum reinvestment (₹700), whether pool value may rise or fall (yes), and what determines lottery weight (final virtual balance). Allow two attempts with fixed feedback. If failed twice, exit before randomization and record the reason.
5. **Assignment:** concealed server-side 2 × 2 allocation after consent and quiz. Use a pre-specified allocation method that maintains reasonable cell balance. Persist assignment once; never reassign on refresh.
6. **Stage 1:** display ₹1,000 starting endowment.
7. **Stage 2:** transfer the fixed ₹100 to the platform; show cash/platform balances.
8. **Stage 3:** display 0% or 35% apparent return on the initial ₹100 only.
9. **Stage 4:** choose `R` from ₹0 to ₹700 in ₹50 increments. Record first render, changes, final choice, and latency definition.
10. **Stage 5:** resolve and store the Growth Pool outcome; display outcome and updated platform balance.
11. **Stage 6:** display the ₹200 withdrawal processing fee.
13. **Stage 8:** choose pay or abandon. Compute final balance from the frozen ledger. After choice, ask any planned fee-comprehension check; it must not alter the choice.
14. **Post-task:** include reward-noticed check; trust/legitimacy/risk/confidence ratings; UI manipulation checks; attention and suspicion checks; financial literacy and DOSPERT financial items.
15. **Debrief and exit:** explain that the reinvestment cap guarantees fee affordability, along with simulated rewards, pool, interface cues, fee, and purpose; explain simulated rewards, pool, interface cues, fee, and purpose; provide contacts and withdrawal process.

Keep the exact validated instrument wording/scoring for financial literacy and DOSPERT. The decision sheet proposes Lusardi–Mitchell Big Three and validated DOSPERT financial investment/gambling items, but confirm the appropriate version, wording, and permissions before freezing the questionnaire. Use 1–7 ratings for perceived trustworthiness, legitimacy, risk, and confidence as proposed; describe these as secondary self-reports, not direct measures of mechanisms. Ask suspicion questions after behavior. Do not automatically exclude everyone who guesses the study purpose; retain the randomized primary analysis and report any pre-specified sensitivity analysis.

## 6. Interface conditions

**Neutral:** plain banking-style layout, ordinary stage label, no countdown, fabricated social proof, urgency language, or salient persuasion cues.

**Manipulative:** one 60-second non-binding countdown, fabricated social proof (“1,284 investors active”), and salient progress/status display. Start the timer on the reinvestment screen, do not reset on refresh, and at zero show “Window extended.” The participant continues without automatic submission, disabled controls, altered outcomes, or termination. Use identical timer/social-proof/progress elements in both reward arms. Do not mention 35% in social proof.

Keep the financial information and decision options identical across UI conditions. Store screenshots and exact copy for every condition. Treat UI components as one bundle. Since countdown affects response time, latency comparisons across UI conditions are descriptive/manipulation-related and not proof of a psychological mechanism.

## 7. Outcomes and analysis plan

### Primary outcome

Reinvestment amount `R`. Fit the factorial mean model:

`R_i = β0 + β1 G_i + β2 U_i + β3 (G_i × U_i) + ε_i`

where `G=1` for 35%, `U=1` for manipulative UI. Use OLS with HC3 robust standard errors. Report four cell means, contrasts, confidence intervals, interaction estimate, and effect sizes. Pre-specify sensitivity analyses: any reinvestment, amount among reinvestors, endpoint concentration, and permutation or rank-based test.

### Confirmatory status at the provisional sample size

A target of 128 completed participants (32 per cell), with about 140 recruited to allow for attrition, is only a planning starting point. Before fixing N, simulate power for H1 (reward), H3 (UI), H4 (interaction), and the binary fee outcome using defensible assumptions. If capacity remains near 128, make H1 and H3 the confirmatory tests for the primary outcome; report H4 as a preregistered, estimation-focused interaction with confidence interval and cautious interpretation unless simulation justifies confirmatory status. Apply Holm correction across the confirmatory family actually specified. Keep H5 moderation exploratory. Do not claim 128 guarantees power for a medium interaction.

### Secondary fee outcomes

The main fee-decision outcome is net-loss payment (`paid AND P < F`), analyzed on the full randomized sample. Never restrict this analysis to a `P < F` subset, because `P` follows treatment and reinvestment. Simulate power for this binary outcome; if underpowered, label its analysis descriptive. Fit logistic regression with reward, UI, and their interaction; report predicted probabilities and average marginal effects. The companion fee-decision error outcome is net-loss payment OR forgone-gain abandonment (`abandoned AND P > F`). Tabulate both categories and indifference cases. H2 is reframed as the fee-decision hypothesis; the balance-vs-payment association remains exploratory and non-causal because balance determines the relative financial value of paying. Report a ceiling/floor if choices are nearly universal rather than forcing elaborate claims.

Trust, perceived risk, latency, literacy, and DOSPERT are secondary. Do not add exploratory interactions after seeing results or call questionnaire associations causal. Specify missing data, exclusions, incomplete sessions, and multiplicity in the preregistration.

### Recruitment and stopping

Provisional plan: recruit about 140 for 128 eligible completions. Set a target and calendar closing date before collection; stop at whichever limit is reached first. Do not extend recruitment based on interim hypothesis results. Track attrition and technical failures by cell, while monitoring only quality and balance during collection.

## 8. Application architecture and data integrity

Recommend oTree. FastAPI + Jinja2 + JavaScript + persistent SQLite (or Postgres) is the alternative. Keep ledger, pool, and lottery logic in plain, unit-tested Python modules. Store lottery contact data separately from behavioral data.

Suggested project modules:

```text
app/
  main.py, config.py
  routes/ consent.py, assignment.py, experiment.py, questionnaires.py, debrief.py
  logic/ ledger.py, growth_pool.py, randomization.py, lottery.py, validation.py
  templates/ shared/, neutral/, manipulative/
  database/ models.py, schema.sql
simulator/ payoff_simulator.py
analysis/ clean_data.py, descriptive.py, hypothesis_tests.py
tests/ test_ledger.py, test_pool.py, test_randomization.py, test_sessions.py
```

The server controls condition, balances, validation, pool outcome, final balance, and lottery weight. Browser code only renders and submits choices/events. Persist a random study ID, consent version, condition, stage state, decisions, outcomes, timestamps, and app/protocol version. Use server time as authoritative; client time supplements it. Make transitions idempotent: double-click, retry, refresh, or back navigation must not double-invest, pay twice, reassign, or redraw. Restore the saved state on refresh.

Suggested tables: participants/sessions; decisions; pool outcomes (including sequence/version reference); questionnaire responses; event log; and a physically/logically separate lottery-contact store. Keep identifiers out of analysis exports. Restrict database access, use HTTPS, document retention, and verify backup restoration.

## 9. Build-to-study pipeline

### Phase A — Decision freeze

Approve the ledger in Section 2, exact participant text, pool candidate/disclosure plan, lottery procedure, measures, eligibility, sample/stopping rule, and analysis. Mark each as approved, pilot-provisional, or ethics-dependent in a signed decision log.

**Output:** signed protocol, ledger examples, screen script, ethics draft, preregistration draft.

### Phase B — Simulator before application

Implement and review all combinations and invariants. The pool must be independent of condition and `R`; final balances must match hand calculations; lottery weights must match final balance/10.

**Output:** simulator, payoff report, review sign-off.

### Phase C — Ethics and preregistration

Obtain instructor/institutional approval for limited disclosure, fabricated social proof, simulated reward, artificial fee, prize draw, privacy, and withdrawal. Finalize target N, stop date, exclusions, missing-data handling, and analysis before main data.

**Output:** approval and time-stamped preregistration.

### Phase D — Application

Build consent/eligibility and comprehension first; then server assignment and durable session state; then the neutral 0% path; implement ledger and outcome persistence; add 35% and manipulative UI via shared logic; then fee, lottery weight, questionnaires, debrief, exports, and backup.

**Output:** all four cells on a single application with shared financial logic.

### Phase E — Technical QA

Verify every `R`, both rewards, every pool outcome, fee edge cases, final balances, lottery weights, assignment persistence, session restoration, duplicate requests, timer behavior, condition consistency, timestamps, data export, and backup restoration. Compare expected/actual values to the simulator. Archive synthetic test data and QA report.

**Output:** signed QA report and screenshots.

### Phase F — Pilot

Run about 8–12 pilot participants if feasible and approved. Assess comprehension, time, failures, reinvestment at endpoints, fee ceiling/floor, reward notice, UI notice, credibility, and debrief comprehension. Change the pool/fee/UI only at this stage. If the protocol changes, update the app, materials, and preregistration; exclude earlier pilot participants from confirmatory data if procedure changed.

**Output:** pilot report and final frozen protocol.

### Phase G — Freeze and main collection

Version-lock app, pool distribution/sequence, instructions, measures, analysis code, and stopping rule. Recruit; monitor technical quality and cell balance without interim hypothesis testing. Preserve raw data snapshot and document deviations.

**Output:** de-identified, validated dataset and reproducible analysis.

### Phase H — Analysis and paper

Run preregistered models, report all condition means and uncertainty, disclose deviations, and preserve the study limitations below.

## 10. Pilot go/no-go checklist

Proceed only when:

- Participants understand the ₹1,000 endowment, ₹100 commitment, ₹700 maximum, and lottery basis.
- Ledger, final balance, and lottery-weight examples match code exactly.
- Reinvestment is not overwhelmingly concentrated at ₹0 or ₹700 (or this is explicitly accepted and justified).
- Fee choice is not nearly universal in one direction (or the limitation is explicitly accepted).
- The share in net-loss territory meets a pilot threshold, initially about 15?20% and adjustable before the main study.
- Simulated `E[r]` is close to the candidate target and pile-up at `R=0` and the cap is acceptable.
- Reward and UI manipulations are noticed without social proof leaking reward assignment.
- Timer expiry is non-binding and does not affect payoffs.
- No refresh, retry, or duplicate submission can reassign or reroll.
- Task duration, technical completion, and debrief are acceptable.
- Ethics/instructor approvals and final preregistration are in place.

## 11. Reconciliation with approach paper

- Growth Pool added to the task.
- H2 reframed around fee decisions; fee decision is a secondary outcome.
- Removed ?controlling for initial commitment? because it is fixed at ?100.

## 12. Limitations for the paper

State that virtual balances are not real investment losses; the 35% condition changes apparent wealth as well as reward feedback; the Growth Pool is a simplified simulation; fee choice is mechanically related to balance; the UI components are bundled; a convenience/student sample may not generalize to actual victims; no neural activity is measured; and one reinvestment decision does not establish a repeated learning trajectory.

## 13. Decision register

| Decision | Selected approach | Status |
|---|---|---|
| Factorial design | 2 × 2 between-subjects | Freeze |
| Starting endowment | ₹1,000 virtual; ₹900 cash + ₹100 invested after commitment | Freeze |
| Initial commitment | Fixed ₹100 | Freeze |
| Apparent return | 0% vs 35% on initial ₹100 only | Freeze |
| Reinvestment | ₹0–₹700 in ₹50 increments | Freeze provisionally; validate in simulator/pilot |
| Fee | ₹200 from remaining cash | Freeze provisionally; ethics/pilot |
| Abandon | Keep cash, forfeit platform balance | Freeze provisionally; ensure approved disclosure |
| Growth Pool formula | `P = 100(1+g) + R(1+r)` | Freeze |
| Pool candidate | −30%/25%, +20%/50%, +50%/25% | Pilot only; do not use in main study until accepted |
| Pool disclosure | Rise/fall language; odds withheld | Ethics-dependent |
| Pool assignment | Pre-generated, shuffled, balanced within condition | Recommended; document as sequence assignment |
| Lottery | Four unique ₹250 vouchers | Approval and budget confirmation |
| Lottery weight | Final balance / 10, fractional weights | Freeze after draw-rule approval |
| Primary outcome | Reinvestment amount | Freeze |
| Confirmatory tests | H1 and H3 at N≈128; H4 confirmatory only if power supports | Preregister after simulation |
| H5 | Exploratory moderation | Freeze |
| UI bundle | Timer + social proof + salient status/progress | Freeze; one manipulation |
| Framework | oTree; FastAPI alternative | Recommended |
| Target sample | 128 complete / about 140 recruited | Provisional; power and capacity review |
