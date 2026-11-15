# 23. Frozen 30: pre-registration of the react_v3 arm (addendum to plan 19)

Status: **draft for the team lead's approval, written 15 Nov 2026 11:50, before any frozen-30 result has been read.**
The frozen queue ("Final - Frozen 30 confirmation - first try") is running on the cloud machine; its runs are not opened
until this addendum is approved and committed. If anyone has read frozen results before approval, that is stated here at
approval and the arm is reported as exploratory, not confirmatory.

## Why a new arm

Plan 19 froze three arms on 14 Nov (B2 +FLAT, A, STRATUS). Since then plan 21 and plan 22 built `agent/react_v3`, chosen
on dev-12 only: evidence cards before the first diagnosis turn (C-027) and a transactional fix (T1, C-029). The question
for the paper is whether those gains hold on problems the changes were not shaped on. Plan 19's arms stay exactly as
they are; this adds one arm, run once.

## Arm (fixed)

`F30 V3 A +CARDS +T1`: agent `reliops_v3`, switches `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS ROUTING ROUTE_REVIEW
FLAT_ARGS PROC_V2 EVIDENCE_FIRST TRANSACTIONAL_FIX`, `REACT_V1_EVIDENCE_MODE=cards` (collector r4), the same model and
first judge as plan 19 (`gemini/gemini-3.5-flash-lite`), 30 problems x 3 repeats, same SREGym copy and profile.

Code: `agent/react_v3_r4` at commit `a7f87c3`, tree hash `72a5f6bfda77e6c4` (sha256 over path and bytes of every file, `__pycache__`
excluded; the copy in the Lab's SREGym clone has the same hash on 15 Nov 11:50). No change after this addendum is approved.

## Comparisons and decision rule (written before the run)

Paired by problem and repeat against plan 19's `F30 A` (same switches minus the two new ones):
1. Mitigation pass (primary for T1): sign test on discordant pairs, two-sided, p < 0.05.
2. Diagnosis pass, first judge: same test.
3. End-to-end pass: same test.
Reported whatever the outcome, with the counts of discordant pairs. `F30 STRATUS` and `F30 B2 +FLAT` are shown for
reference, without tests against this arm.

## Known risks, stated in advance

- **Overfitting.** The card rules were chosen after reading dev-12 failures. On a 6-problem check set outside dev-12 and
  the frozen 30 the cards (no tools) scored 3/30 against 38/60 on dev-12 (plan 21 section 11). A smaller frozen gain than
  on dev-12 is expected.
- **Simulator numbers are not cluster numbers.** The simulator under-states arm A (36% against 67% on the cluster).
- **Three dev problems fail in every arm** (priority preemption, GC tuning, ingress misroute): misread evidence, not
  missing evidence. Neither cards, references (REF) nor a stronger final model fixed them on dev-12.
- **Quota.** Runs that end on an API quota error are re-run (they are infrastructure failures, not agent results), as
  the Lab already does; the count is reported.

## Approval

- [ ] Approved by the team lead (date): ________
- [ ] Frozen results read by anyone before approval: yes / no
