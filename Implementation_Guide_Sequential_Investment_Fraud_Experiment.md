# Implementation Guide: Sequential Investment-Fraud Experiment

**Source documents:** `Team5_ApproachPaper (2).pdf` and the supplied experimental-design notes  
**Status:** Implementation specification for protocol finalization, application build, pilot, and main study  
**Version:** 1.0

---

## 1. Purpose and scope

This guide turns the approach paper and design notes into an implementable behavioral experiment. The study examines whether a displayed initial gain and a manipulative interface affect a participant's subsequent reinvestment and response to a withdrawal barrier.

The design is a **2 × 2 between-subjects experiment**:

| | 0% initial apparent return | 35% initial apparent return |
|---|---|---|
| Neutral UI | Condition 1 | Condition 2 |
| Manipulative UI | Condition 3 | Condition 4 |

Each participant is assigned to one condition. The financial rules, pool mechanism, timing of outcomes, and decision options must be the same across conditions, except for the assigned initial-return display and UI presentation.

The application is a simulated, virtual-money environment. It does not measure neural activity, and the results should be described as behavioral evidence consistent with proposed mechanisms, not as direct evidence of neural processes, FOMO, arousal, regret, or heuristic processing.

This document is an implementation plan, not ethics approval or a final preregistration. Do not begin main data collection until the unresolved choices in Section 3 have been signed off and the ethics/instructor requirements have been met.

## 2. Decisions already established by the source material

Treat the following as the current design specification:

1. **Design:** between-subjects 2 × 2 factorial; random assignment to one of four cells.
2. **Endowment:** ₹1,000 virtual starting capital.
3. **Initial commitment:** fixed ₹100.
4. **Reward manipulation:** the initial ₹100 is shown as earning either 0% or 35% apparent gain. This manipulation applies only to the initial ₹100.
5. **Reinvestment:** participant chooses an amount `R`, provisionally ₹0–₹700 in ₹50 increments, subject to ledger and pilot confirmation. Record amount and latency.
6. **Growth Pool:** its return applies to the reinvested amount; its distribution is identical for every assigned condition, generated on the server, and frozen before main collection. It must not depend on the participant's UI assignment, reward assignment, or reinvestment choice. No rerolls after refresh.
7. **Withdrawal barrier:** ₹200, described consistently as a fee/tax/processing charge. The paper defines this as 20% of the initial ₹1,000; the notes recommend keeping ₹200 subject to pilot. The implementation should use one neutral, ethically approved label throughout, not rotate labels.
8. **Fee choice:** pay the fee or abandon the withdrawal. The decision and final balance are recorded. Analyze net-loss payments and forgone-gain abandonments separately, with indifference cases identified.
9. **Neutral UI:** simple banking-style presentation, no countdown, fabricated social proof, or urgency cues.
10. **Manipulative UI:** non-binding 60-second countdown, the same social-proof message in both reward arms, and salient progress/status cues. Example social-proof wording in the notes: “1,284 investors active.” Do not include a return claim in that message. At zero, show “Window extended”; allow continuation. Timer expiry must neither alter payoffs nor terminate the session.
11. **Measures:** primary outcome is reinvestment amount. Fee decision is secondary. Secondary measures include perceived trust and risk, financial literacy, and DOSPERT financial risk-taking. Latency is descriptive/manipulation-related, not proof of a mechanism, because the timer itself affects latency.
12. **Incentives:** final virtual balance determines entries in a real-world voucher lottery, with a fixed conversion rule disclosed and frozen before data collection. Keep contact details separate from experimental data.
13. **Recruitment planning:** approximately 140 recruits for 128 complete records is a starting estimate, not a power guarantee. At 128 complete, there are 32 participants per cell. Simulate power for the interaction and binary fee outcome before setting the final target.
14. **Technology recommendation:** FastAPI + Jinja2 + JavaScript + SQLite, or oTree as a single alternative. Keep assignment, financial calculations, and pool draws server-side. Use persistent hosting; use Postgres/Supabase if persistent SQLite storage cannot be guaranteed.

## 3. Freeze these design decisions before implementation

The source documents do not fully specify the payoff ledger. Do not infer or hard-code these decisions without documenting them. Convene the research team and create a signed protocol decision sheet covering each item below.

### 3.1 Canonical financial ledger

Specify, in rupees and with equations, the account balance at every stage. In particular, decide:

- Whether the ₹1,000 is a withdrawable account balance, an experimental endowment from which funds are committed, or a display-only starting capital.
- Whether the fixed ₹100 commitment is deducted from available cash or moved to an investment balance.
- Whether the 0%/35% return is added to the ₹100 investment (so ₹100 becomes ₹100/₹135), or whether “35% apparent return” means a ₹35 gain shown separately. These are mathematically equivalent only if displayed and ledgered consistently.
- What balance is eligible for reinvestment and how the ₹0–₹700 range follows from the displayed balance. Explain why a participant may reinvest ₹700 even though the account began at ₹1,000 and has already committed ₹100.
- Whether the reinvested amount is deducted immediately and whether the Growth Pool return is added to it or replaces it.
- Whether the withdrawal fee is paid from remaining cash, deducted from the displayed portfolio, or required as an additional payment. The notes say fee payment reduces virtual balance/lottery entries; implement that directly and make the debit source explicit.
- What “abandon” means in the ledger: forfeiting the withdrawable balance, declining to pay and retaining some funds, or ending the session with zero accessible funds. This is essential to classifying net-loss and forgone-gain decisions.
- Whether the ₹200 fee is affordable in every possible balance state. If not, define the UI and analysis treatment for participants who cannot pay.
- How the final balance is calculated in every branch and capped, if at all.

Produce a ledger table with one row per branch and worked examples for both reward conditions, at least two reinvestment amounts, both pool outcomes, and pay/abandon choices. The same balance formula must be implemented in app code, participant-facing explanations, payoff simulator, analysis code, and QA expected values.

### 3.2 Growth Pool outcome distribution

The source notes explicitly advise against freezing an unpiloted `+5%` return. Before coding the final production draw, specify:

- Outcome set (for example, gain/loss/zero categories), probability of each outcome, and return multiplier or amount.
- Whether outcomes are sampled independently for each participant or assigned from a pre-generated balanced sequence. If using a balanced sequence, generate and shuffle it before collection, and define handling at exhaustion. Never choose an outcome based on `R` or condition.
- How the pool return changes the participant's balance and whether any loss can reduce balance below zero.
- The participant-facing description of uncertainty, including whether odds are disclosed. Keep it truthful and identical across cells.
- Whether the pool is intended to be known-odds risk or to test belief updating. If testing beliefs, specify the theoretical contrast and measure perceived return likelihood before and/or after the pool as appropriate.

Build a payoff simulator and examine expected returns, variance, frequency of negative/positive final balances, and how often the fee is financially advantageous. Run pilot checks for reinvestment endpoint concentration and fee choice ceilings/floors. Then freeze the distribution and randomization procedure before main collection.

### 3.3 Lottery conversion and prize procedure

Set the prize value, entry conversion, maximum entries (if any), draw date, winner notification, eligibility, contact-data storage, and unclaimed-prize procedure. Verify that every possible final balance maps to a valid number of entries. The rule must be the same for all participants and communicated in consent/instructions without revealing the specific hypotheses.

### 3.4 Other protocol items

Freeze exact text and options for instructions, comprehension items, trust/risk ratings, manipulation checks, attention/suspicion checks, literacy instrument, DOSPERT items, debrief, withdrawal procedure, recruitment method, eligibility (adult-only as proposed), completion criteria, sample target, stopping date, and missing-data/exclusion rules.

## 4. Hypotheses, outcomes, and analysis alignment

### 4.1 Confirmatory outcomes

- **Primary:** reinvestment amount `R` (₹0–₹700, ₹50 increments, if confirmed).
- **Secondary:** binary fee payment, with categories based on the signed ledger: net-loss payment, forgone-gain abandonment, and indifference. Define these categories mathematically before data collection.

### 4.2 Hypotheses

- **H1, reward escalation:** 35% initial apparent return increases subsequent reinvestment relative to 0%.
- **H3, UI effect:** manipulative UI increases reinvestment relative to neutral UI. The fee-payment UI effect is secondary.
- **H4, interaction:** manipulative UI amplifies the effect of 35% reward on reinvestment. Fee interaction is secondary unless the team explicitly powers and preregisters it as confirmatory.
- **H2, withdrawal commitment:** higher apparent balance is associated with fee payment. Treat as exploratory/non-causal because balance is mechanically related to reward and pool outcomes and determines the financial attractiveness of paying.
- **H5, individual differences:** financial literacy and DOSPERT financial risk-taking may moderate susceptibility. Treat moderation as exploratory at an N near 120–140 unless a power analysis supports otherwise.

The pasted notes recommend reinvestment as the primary outcome and Holm correction across confirmatory H1, H3, and H4 tests. This is a deliberate refinement of the paper, whose original “primary outcomes” also included fee payment. State this decision consistently in the preregistration and final report.

### 4.3 Models

Code treatment indicators as `G` (35% = 1, 0% = 0) and `U` (manipulative = 1, neutral = 0). Fit the primary factorial model:

`R_i = β0 + β1 G_i + β2 U_i + β3 (G_i × U_i) + ε_i`

Use OLS with HC3 robust standard errors as the primary estimand for mean reinvestment. Report all four cell means, contrasts, confidence intervals, interaction estimate, and effect sizes. Apply Holm correction to the preregistered H1/H3/H4 family. Do not add covariates post hoc to rescue significance.

Pre-specify sensitivity analyses because `R` is bounded and discrete: probability of any reinvestment; amount among reinvestors; endpoint concentration; and a permutation or rank-based analysis. Explain that OLS estimates mean differences and is not automatically invalid due to bounded outcomes.

For fee payment, use logistic regression with `G`, `U`, and `G×U`; report predicted probabilities and average marginal effects. Report the three payoff categories separately. If the outcome is near all-pay or all-abandon, report the ceiling/floor and avoid over-interpreting unstable estimates. Treat fee tests as secondary unless a separate power and multiplicity plan supports confirmatory claims.

Analyze trust, perceived risk, latency, literacy, and DOSPERT as specified in the preregistration. Latency is skewed and the countdown changes the interface experience, so report it descriptively or as a manipulation-related measure. Do not claim that latency establishes a psychological mechanism. Avoid a large family of exploratory interactions.

## 5. Participant flow and screen-by-screen specification

The paper's seven stages are financial-task stages. The implementation also needs consent, comprehension, questionnaires, and debrief screens. Recommended full flow:

### Screen 0: Study entry and eligibility

Show study title at a broad level (digital investment decision-making), estimated duration, adult eligibility, voluntary nature, compensation/lottery details, privacy, withdrawal procedure, and researcher/contact information. Do not disclose the specific hypotheses before the task if the approved protocol permits limited disclosure. Do not misrepresent real money: clearly state that task balances are virtual and explain the lottery link.

Record eligibility and a random session ID. Do not collect direct identifiers in the experiment database.

### Screen 1: Consent

Require affirmative consent before proceeding. Record consent version and timestamp. A participant who declines must exit without assignment or experimental records beyond any ethically approved minimal consent-decline count.

### Screen 2: General instructions and comprehension quiz

Explain the virtual account, fixed initial commitment, reward display, reinvestment options, pool resolution, withdrawal fee, final-balance rule, and lottery conversion. Quiz participants on the rules before randomization. Use a pre-specified number of attempts and feedback policy. Do not reveal condition assignment before comprehension is passed. If a participant fails the maximum attempts, follow the preregistered exclusion/exit path and record the reason.

### Screen 3: Random assignment

After eligibility, consent, and comprehension, assign one condition server-side with concealed allocation. Use permuted blocks of size(s) chosen in advance, stratified only if justified (e.g., recruitment site). Keep block sizes undisclosed to operators where feasible. Save assignment once; it must survive refresh/resume. Never assign by URL or client-side JavaScript.

### Stage 1: Endowment

Display ₹1,000 virtual starting capital and a concise balance summary. Record the displayed value and timestamp.

### Stage 2: Initial commitment

Present the fixed ₹100 investment/commitment. Since it is fixed, do not present a choice that implies agency. State exactly what happens to the ₹100 under the frozen ledger. Record the commitment event and resulting balance.

### Stage 3: Initial reward feedback

Show either 0% or 35% apparent return on the initial ₹100 only. Make the display layout, duration, wording, and all non-return content equivalent across reward arms and UI arms. Do not apply this reward to the later reinvestment amount. Record assigned reward, displayed amount, and resulting balance.

### Stage 4: Reinvestment decision

Ask for `R` using the frozen permitted range and increments. Provide the current available balance and a neutral explanation of consequences. Validate on the server that the amount is permitted and affordable under the approved ledger. Record selected amount, first display time, final submission time, number of changes, and latency definition. Preserve the response if the browser reloads; reject duplicate commits idempotently.

### Stage 5: Growth Pool resolution

Resolve the draw on the server using the frozen algorithm. Store the outcome, draw reference/seed or auditable sequence index, algorithm version, and timestamp before displaying it. The outcome must be independent of condition and `R`. Display outcome and updated balance at the same task point, with the same format in all conditions. A refresh must return the same stored result.

### Stage 6: Withdrawal attempt and fee disclosure

Present the same withdrawal interface and ₹200 charge in every condition, with neutral and approved language. The charge is artificial and must be fully explained in debrief. Record fee display and the balance available for the decision. Do not make the fee depend on condition, response time, or reinvestment amount.

### Stage 7: Pay or abandon

Offer clearly labeled pay and abandon actions. Explain consequences consistent with the ledger, without adding urgency outside the assigned UI manipulation. Record choice, submission timestamp, final balance, and fee classification. Add a post-decision comprehension check if planned; the design notes call for a fee comprehension check after the final decision, so do not let it alter the already-recorded choice.

### Post-task measures

Collect, in the preregistered order:

1. Trust and perceived-risk ratings.
2. UI manipulation checks (noticed timer/social proof/status cues; perceived urgency/credibility as approved).
3. Attention and suspicion checks.
4. Financial literacy measure.
5. DOSPERT financial risk-taking items.

Keep item wording and scoring key fixed. Avoid leading questions that disclose the hypothesis before behavior is measured.

### Debrief and exit

Explain the simulated platform, fabricated reward/UI elements, artificial fee, randomization, and study purpose. Reiterate virtual balances and lottery mechanics. Provide investigator/contact details and the approved procedure for withdrawing data after debrief, including deadline and how an anonymous participant can identify their record if withdrawal is possible. Store any lottery contact details separately, linked only by a random claim token if needed.

## 6. UI and interaction requirements

### Neutral UI

- Banking-style layout with plain typography and restrained colors.
- No countdown, social proof, urgency language, streaks, flashing, or emotionally loaded status messages.
- Keep all financial facts visible and legible.

### Manipulative UI

- Show a 60-second non-binding countdown at the pre-specified point(s). The protocol must state exactly which screen starts it and whether it restarts on navigation; recommended: start at the reinvestment screen and do not reset on refresh.
- At zero, replace timer text with “Window extended” and permit continuation. No auto-submit, disabling controls, loss of funds, or altered odds.
- Use the exact same fabricated social-proof message in both reward arms, at the same point and with the same visual prominence.
- Use the same progress/status cues in both reward arms. The manipulative treatment is a bundle; do not independently vary its components.
- Do not mention or imply the 35% return in social proof.

All visual/wording differences between conditions should be version-controlled and documented. Take screenshots of every condition at each task stage before pilot and preserve them with the protocol materials.

## 7. Technical architecture and data handling

### 7.1 Recommended stack

- **FastAPI:** routes, server-side session logic, assignment, validation, calculations, outcome draws, and exports.
- **Jinja2:** server-rendered screens and condition-specific templates/partials.
- **JavaScript:** slider/buttons, client event timestamps, timer display, and tab-focus events. Client code must never decide assignment, balance, or pool outcome.
- **SQLite:** suitable for a single persistent instance and modest study only if storage survives restarts and backups are verified. Otherwise use Postgres (including Supabase Postgres) with access controls and backups.
- **Python:** payoff simulator, data validation, export, and analysis.

Use oTree instead if the team prefers a behavioral-experiment framework; do not build parallel systems in both stacks.

### 7.2 Core data entities

A normalized schema can use these tables (or equivalent linked records):

**participants/sessions**
- random participant ID; session status; consent version/time; eligibility; condition; assignment block/sequence reference; start/completion times; protocol/app version; exclusion/withdrawal status.

**decisions**
- participant ID; stage; response value; amount; balance before/after; first view and submit timestamps; latency; validation status; idempotency key.

**pool_outcomes**
- participant ID; outcome category/value; draw time; algorithm and distribution version; seed/reference or pre-generated sequence index; whether displayed; no personal information.

**questionnaires**
- participant ID; instrument/version; item ID; response; score where appropriate; completion timestamp.

**events**
- participant ID; event type; stage; server timestamp; client timestamp if collected; tab visibility/focus changes; errors; refresh/resume events. Collect only what is justified and disclosed.

**lottery contacts (separate store)**
- claim token/contact details; prize status. No questionnaire or behavioral data in this store. Access is restricted.

### 7.3 Session and event rules

- Generate a cryptographically random study ID; do not put names/emails in it.
- Persist condition and all committed decisions server-side.
- Use server timestamps as the authoritative event time; client timestamps are supplemental.
- Make each stage transition idempotent. Repeated submission of the same action must return the saved result, not create another investment, fee, or draw.
- Support refresh/resume by reconstructing the last committed state from the database.
- Prevent participants from editing prior stages through back navigation; if revisiting is allowed for usability, show saved state and do not reprocess transactions.
- Use HTTPS, restricted database credentials, least-privilege access, and documented backups/retention.
- Keep raw identifiers out of analysis exports. Export a de-identified dataset and a separate data dictionary.

### 7.4 Suggested event names

`consent_given`, `comprehension_attempt`, `assignment_created`, `stage_viewed`, `initial_commitment_recorded`, `reward_displayed`, `reinvestment_changed`, `reinvestment_submitted`, `pool_resolved`, `pool_displayed`, `fee_displayed`, `fee_choice_submitted`, `questionnaire_item_submitted`, `tab_visibility_changed`, `session_resumed`, `validation_error`, `debrief_viewed`, `session_completed`.

Document the exact latency start/end definitions (for example, first render to committed choice) and apply consistently. Tab focus is a technical/context measure, not proof of attention.

## 8. Build sequence

### Phase 1: Protocol and payoff simulator

1. Complete the decision sheet in Section 3.
2. Write the financial ledger and decision tree before screens.
3. Implement a small payoff simulator that enumerates all allowed `R` values, reward arms, pool outcomes, fee choices, and edge balances.
4. Independently review formulas against hand-calculated examples.
5. Freeze exact instructions, quiz, UI copy, measures, incentives, and debrief.

**Deliverables:** signed protocol, ledger, simulator, screen script, draft preregistration/ethics materials.

### Phase 2: Ethics and preregistration

1. Obtain instructor/institutional approval for limited disclosure, simulated deception, fabricated UI elements, artificial fee, data handling, and voucher lottery.
2. Confirm eligibility and consent requirements.
3. Pre-specify hypotheses, primary/secondary outcomes, sample size, exclusions, missing data, multiple testing, models, and stop date.
4. Prepare debrief and any required participant-withdrawal process.

**Deliverable:** approval and time-stamped preregistration before main collection.

### Phase 3: Application implementation

Build in this order:

1. Project configuration, database schema, migrations, and secure random session IDs.
2. Consent and eligibility flow.
3. General instructions and comprehension quiz.
4. Server-side assignment and durable resume state.
5. Neutral 0% condition as the reference flow.
6. Server-side financial ledger and validations.
7. Pool draw persistence and repeat-safe stage transitions.
8. Remaining reward/UI combinations via shared templates and condition configuration.
9. Fee choice, final balance, and lottery-entry calculation.
10. Questionnaires, debrief, data export, and backup process.

Keep condition differences data-driven where practical (e.g., treatment flags and template tokens), while ensuring visual/wording fidelity. Do not duplicate financial logic per condition.

### Phase 4: Technical verification

Use a test environment and synthetic test participants. Verify:

- Each of four cells renders the correct reward and UI features.
- ₹1,000 endowment, fixed ₹100 commitment, 0%/35% reward, every permitted `R`, pool result, ₹200 fee, pay/abandon outcome, and lottery entries match the ledger.
- Pool outcomes are independent of condition and `R`; no refresh/reroute produces a second draw.
- Fee handling at balances below, equal to, and above ₹200 follows the stated rule.
- Random assignment balance and persistence on refresh/resume.
- Validation blocks out-of-range, unaffordable, or off-increment entries.
- Double-clicks, network retry, browser back, refresh, and duplicate requests do not double-commit.
- Timer behavior is non-binding and does not change financial outcomes or terminate sessions.
- The social-proof message and progress cues are identical across the two reward arms within Manipulative UI.
- Timestamps, latency, tab visibility, errors, and incomplete sessions are logged as specified.
- Data export reproduces the event/decision records and excludes direct identifiers.
- Backup restoration works in a clean environment.

**Deliverable:** test dataset, expected-versus-actual ledger report, screenshots, and QA sign-off. Do not use main-study data to discover calculation defects.

### Phase 5: Pilot and freeze

Run approximately 8–12 pilot participants if feasible, consistent with the source notes and ethics approval. Treat pilot observations as protocol calibration, not confirmatory evidence. Assess:

- Comprehension and misunderstanding patterns.
- Reinvestment distribution and concentration at ₹0/₹700.
- Whether the Growth Pool makes reinvestment a meaningful choice.
- Whether fee choices are nearly universal in either direction.
- Whether participants notice UI cues and whether the manipulative interface feels too coercive or implausible.
- Session duration, technical failures, dropout, and questionnaire burden.

Make any payoff, wording, or UI changes now. If the pool, fee, ledger, or outcome definitions change, update all materials and the preregistration before main recruitment. Freeze app version, pool distribution, assignment plan, data schema, and analysis plan.

### Phase 6: Main collection

Use the frozen order: consent → comprehension → assignment → seven-stage task → trust/risk → manipulation checks → attention/suspicion → literacy → DOSPERT → debrief. Monitor technical quality and cell balance only. Do not inspect interim hypothesis results to decide whether to stop. Stop at the pre-specified target/date and document deviations.

### Phase 7: Analysis and reporting

1. Lock a raw-data snapshot and document exclusions before treatment-effect analysis.
2. Validate the data against the data dictionary and ledger invariants.
3. Run the preregistered primary and secondary models.
4. Produce reproducible tables/plots and code.
5. Report deviations, null results, uncertainty, and limitations.
6. Interpret findings as evidence from a simplified virtual simulation, not actual fraud victimization.

## 9. Recruitment and sample-size planning

The notes suggest around 140 recruited participants to yield 128 complete participants (32 per condition). This is only a planning starting point. Before fixing target N:

- Define a smallest effect of interest for the reinvestment main effects and interaction.
- Use expected cell means/SDs from pilot or justified assumptions to simulate the factorial design and HC3 analysis.
- Separately evaluate power for binary fee payment using plausible event rates and the interaction model.
- Account for incompletion/exclusions without using outcome-dependent exclusions.
- Set one target N and stop date in advance.

If recruitment capacity is limited, retain the factorial structure and prioritize reinvestment. Keep H5 exploratory if power is insufficient. Do not describe 128 as guaranteed to detect a medium effect without specifying assumptions; interaction power and binary-outcome power may be considerably lower.

## 10. Pre-launch checklist

### Protocol and ethics

- [ ] Four conditions and randomization plan frozen.
- [ ] Ledger has complete equations and worked examples.
- [ ] Reward applies only to initial ₹100.
- [ ] Reinvestment range and increments are feasible under ledger.
- [ ] Growth Pool distribution, disclosure, and draw method frozen.
- [ ] ₹200 fee base, debit source, and abandonment consequence explicit.
- [ ] Lottery conversion, prize, cap, and draw procedure frozen.
- [ ] Consent, limited disclosure, debrief, and withdrawal procedure approved.
- [ ] Adult eligibility, recruitment, sample target, and stop date set.
- [ ] Hypotheses, outcomes, exclusions, missing data, and analysis preregistered.

### Application and data

- [ ] All four conditions work and are visually reviewed.
- [ ] Assignment and calculations are server-side and durable.
- [ ] No duplicate submissions or pool rerolls are possible.
- [ ] Timer extension behavior is correct and non-binding.
- [ ] Social proof/progress cues match across reward arms.
- [ ] Fee edge cases and final balance match ledger.
- [ ] Comprehension, post-decision fee check, questionnaires, and debrief work.
- [ ] Session restoration and incomplete-session handling are verified.
- [ ] Timestamps/latency/focus events are defined and recorded.
- [ ] Direct contact details are kept separate.
- [ ] Export, data dictionary, backup, and restore are verified.
- [ ] QA report and test dataset are archived.

## 11. Limitations to preserve in the report

- Virtual money and a voucher lottery are not equivalent to real financial loss.
- The 35% condition changes apparent virtual wealth as well as feedback; the ledger must make this consequence explicit.
- The Growth Pool is a simplified mechanism, not a faithful reproduction of an investment scam.
- The fee choice has a built-in payoff threshold and may be mechanically related to balance.
- Student or convenience samples may not generalize to actual fraud victims.
- UI cues are bundled, so this design cannot identify the separate effect of timer, social proof, and progress cues.
- No neural activity is measured.
- A single post-reward reinvestment decision does not support claims about repeated learning trajectories.

## 12. Final implementation recommendation

Retain the 2 × 2 design, seven-stage financial sequence, fixed ₹100 initial commitment, and reinvestment as the primary outcome. Build a ledger and payoff simulator before final screens. Do not freeze a proposed +5% pool return without simulation and pilot evidence. Treat the ₹200 withdrawal fee as a pilot-tested fixed fee tied to the stated ₹1,000 starting capital, and define exactly how payment and abandonment change the final balance. Keep the timer non-binding. Once pilot changes are complete, freeze the protocol and preregistration before collecting main-study data.
