# 23. Frozen 30: pre-registration of the react_v3 arm (addendum to plan 19)

Status: **approved by the team lead on 15 Nov 2026 (about 17:40), with the arm to be chosen on 16 Nov by the rule below.**
Written 15 Nov 11:50, before any frozen-30 result had been read.
The frozen queue ("Final - Frozen 30 confirmation - first try") is running on the cloud machine; its runs are not opened
until this addendum is approved and committed. If anyone has read frozen results before approval, that is stated here at
approval and the arm is reported as exploratory, not confirmatory.

## Why a new arm

Plan 19 froze three arms on 14 Nov (B2 +FLAT, A, STRATUS). Since then plan 21 and plan 22 built `agent/react_v3`, chosen
on dev-12 only: evidence cards before the first diagnosis turn (C-027) and a transactional fix (T1, C-029). The question
for the paper is whether those gains hold on problems the changes were not shaped on. Plan 19's arms stay exactly as
they are; this adds one arm, run once.

## Arm (chosen on 16 Nov by a rule fixed now)

Rule, written 15 Nov 17:40 before the dev-12 cluster runs finish: of `V3 A +T1` (A + `TRANSACTIONAL_FIX`) and
`V3 A +CARDS +T1` (A + `EVIDENCE_FIRST` + `TRANSACTIONAL_FIX`), the arm with the higher dev-12 cluster mitigation pass
(Lab experiment "Dev - V3 r4.1 - first try", runs that ended on an API-quota error excluded) goes to the frozen 30. If the
two differ by one run or less, `V3 A +T1` goes (fewer parts). Both use the same code (commit `efc7bdc`, r4.4). Reason for the
change from the 11:50 draft: on the cluster the cards did not raise the diagnosis (plan 22, 15 Nov 17:30).

Default text below describes `V3 A +CARDS +T1`; for `V3 A +T1` drop `EVIDENCE_FIRST` and the evidence mode.

`F30 V3 A +CARDS +T1`: agent `reliops_v3`, switches `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS ROUTING ROUTE_REVIEW
FLAT_ARGS PROC_V2 EVIDENCE_FIRST TRANSACTIONAL_FIX`, `REACT_V1_EVIDENCE_MODE=cards` (collector r4), the same model and
first judge as plan 19 (`gemini/gemini-3.5-flash-lite`), 30 problems x 3 repeats, same SREGym copy and profile.

Code: `agent/react_v3_r4` at commit `efc7bdc`, tree hash `1451b865e2542881` (r4.4; was `a7f87c3` / r4.2 until 15 Nov 19:10, changed before any frozen v3 run because T1 looped to the step cap when the proof read went through the shell: 2 dev runs affected, one of them ended without a submission; the pin moves, the rule does not) (sha256 over path and bytes of every file, `__pycache__`
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

- [x] Approved by the team lead: 15 Nov 2026.
- [x] Frozen results read by anyone before approval: **no**. Only progress counts (how many frozen runs had finished, on
  the Lab's machine table) had been seen, not any pass/fail result.
