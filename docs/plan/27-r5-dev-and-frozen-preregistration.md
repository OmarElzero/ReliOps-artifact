# 27. react_v3 r5: dev-12 and frozen-30 run, pre-registered (17 Nov 2026)

Status: **requested by the team lead on 17 Nov 2026 07:45** (build the r5 agent and run it on the dev and the
frozen set on the six machines the same day). Written 17 Nov 08:00, before any r5 run. Approval line at the end.

## 1. What is run

Agent `reliops_v5` = `agent/react_v3_r5` (plan 26), switches:
`TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS ROUTING ROUTE_REVIEW FLAT_ARGS PROC_V2 TRANSACTIONAL_FIX T1_DRIVER FIX_FAMILIES
ADAPTIVE_WAIT D1_PREDICT`. That is the plan 25 arm (A + T1 v2) plus:

- **r4.5 fixes** (C-034: a recreated PVC is unbound; re-baseline after a T1 v2 restore. C-035: lenient JSON).
- **3 TNR rounds** instead of 2 (`T1_MAX_ROUNDS` default 3).
- **FIX_FAMILIES** (C-037): every restore message names the routed procedure's ordered fix families and asks for the next
  untried one (procedure-guided TNR). Family lists: general Kubernetes knowledge per SREGym category (`prompts.py`).
- **ADAPTIVE_WAIT** (C-038): before a proof read or a driver verdict, wait until the namespace's rollouts have settled
  (30 to 180 s) instead of a fixed 60 s.
- **D1_PREDICT** (C-036): before the diagnosis is submitted, the model states one prediction that must hold if it is right
  and names one read; the driver runs it and shows the output; the model keeps or revises the diagnosis (one round).

Same model and first judge as plans 19/23/25 (`gemini/gemini-3.5-flash-lite`), same SREGym copy and profile.

Two Lab queues, 6 shares each, built by `scripts/make_v5_queues.py` from the existing queues (so problems, repeats, model,
judge and purpose cannot differ by hand):
- `Dev V5 (plan 27)`, experiment **`Dev - V5 r5 - first try`**: dev-12 x 3 = 36 runs.
- `F30 V5 (plan 27)`, experiment **`Final - Frozen 30 V5 - first try`**: frozen 30 x 3 = 90 runs, arm `F30 V5`.

Code: `agent/react_v3_r5`, tree hash `739ac06632b6c2e8` (sha256 over relative path and bytes of every file, `__pycache__`
excluded), committed with this plan (commit `a8003fd`). Synced as `clients/reliops_v5` by `scripts/sync_agent.sh`; needs ReliOps-Lab `main`
at `24d6dce` or later and `scripts/apply_sregym_patches.py` (registers `reliops_v5`).

## 2. Order and the smoke gate

The dev runs are **not** used to change the code: dev and frozen run in parallel, the dev only describes the version on the
development set. Before the first frozen run, one machine runs at least 4 dev runs; if any ends on an error caused by the
new code (agent exit with a traceback, a loop to the step cap, a refused write pattern), the code is fixed, re-pinned here
and the dev restarts; no frozen run starts before the gate passes. If a code fault appears during the frozen runs, the runs
stop and the fault is reported; no silent fix.

**Smoke gate result (17 Nov 09:58): one code fault found and fixed (r5.1).** A dev run (storage_user_unregistered-2)
reached the action cap; in the wrap-up the empty-diagnosis guard, ROUTE_REVIEW and then D1 each intercepted the submit, the
wrap-up calls ran out and the run ended unsubmitted (rc 4). Fix: D1 does not ask once the wrap-up has started. Unit test
added (`sim/test_r5.py`, case 1c). New pin: tree `58fa167ea2ccffc8` (commit below). Dev runs made with r5.0 are relabelled
`(r5.0)` and re-run; no frozen V5 run had started.

## 3. Comparisons (fixed now)

Paired by problem and repeat on the frozen 30, exact sign test on discordant pairs, two-sided, alpha 0.05:
1. **Primary:** `F30 V5` against `F30 A` (plan 19), mitigation pass.
2. Secondary, reported uncorrected: `F30 V5` against `F30 STRATUS` (mitigation, diagnosis, end-to-end); against
   `F30 V3 A +T1v2` (mitigation: the r5 additions on top of the same TNR); against `F30 A` (diagnosis, end-to-end).
Duplicate cells: the earliest valid run counts (plan 25 rule). Infrastructure failures are re-run and counted. The second
judge (plan 25 section 5) is applied to this arm too.

## 4. What was known when r5 was designed (disclosure)

r5 items 1 to 4 (D1, deeper TNR, r4.5, adaptive wait) were written in plan 26 at 17 Nov 01:15 from dev-12 observations.
Item 5 (FIX_FAMILIES) was added at 07:45 from a team question about procedures and TNR. Before that, three exposures of the
running frozen work are on record (plan 23, plan 25): a Lab table with one STRATUS infrastructure failure (15 Nov), one
STRATUS action on one frozen problem in a cloud-machine log (16 Nov 21:00), and a Queue-tab PASS/FAIL count per share of the pooled v3
arms (17 Nov 05:10). The frozen problem names were known (they are in `experiments/first-30.csv`). No frozen run of any arm
was opened, and no fix-family list or prompt was written from a frozen problem.

## 5. Risk

New code goes to the frozen 30 after unit tests and the smoke gate only, without a dev-12 selection round. A smaller or
negative effect is possible; it is reported as found.

## Approval

- [x] Approved by the team lead: 17 Nov 2026 about 08:05 (build, run the smoke gate, then the dev set and the frozen
  set). Paper deadline 20 Nov AoE (21 Nov Cairo).
