# 25. Frozen 30: a second react_v3 arm (A + T1 v2) and analysis additions (addendum to plans 19 and 23)

Status: **approved by the team lead on 16 Nov 2026 (about 06:10), with the queue in 6 shares.** Written 16 Nov 06:15,
before any react_v3 frozen run. No frozen-30 pass/fail result had been read (only progress counts, and run names and
machine names in a Lab screenshot shared within the team on 16 Nov 04:38, with the result columns outside the picture).

## 1. What is added

One arm, run once, beside the plan 23 arm:

`F30 V3 A +T1v2`: agent `reliops_v3`, switches `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS ROUTING ROUTE_REVIEW FLAT_ARGS
PROC_V2 TRANSACTIONAL_FIX T1_DRIVER`, same model and first judge as plan 19 (`gemini/gemini-3.5-flash-lite`), 30 problems
x 3 repeats, same SREGym copy and profile.

Code: the plan 23 pin, `agent/react_v3_r4` at commit `5955d65` (r4.4 plus `T1_DRIVER`). No new code: the r4.5 fixes
(C-034, C-035, `agent/react_v3_r45`) are not on the cluster yet and stay out of the frozen 30.

## 2. Why, and the deviation it makes

Plan 24 section 4 said T1 v2 could become a frozen arm only if it beat `V3 A +T1` on dev-12 mitigation by the plan 16
rule (exact sign test). It does not: at 16 Nov 06:00 (all Lab machines, quota failures excluded) dev-12 mitigation was
14/22 for A + T1 v2 and 13/22 for A + T1, close to equal. The team decided to add it anyway, for the paper: the frozen 30 is
the only place where the two T1 designs can be compared on problems they were not shaped on. This is stated as a
deviation from plan 24 section 4. The arm is pre-registered here, so its tests against `F30 A` are confirmatory; its
comparison with the plan 23 arm is secondary.

## 3. Comparisons (fixed now)

Paired by problem and repeat, exact sign test on discordant pairs, two-sided:

1. Primary, for each of the two react_v3 arms (the plan 23 arm and this one) against `F30 A`: mitigation pass. Two
   primary tests, so Holm's correction at family-wise 0.05 (the smaller p must be < 0.025, the other < 0.05).
2. Secondary, each v3 arm against `F30 A`: diagnosis pass (first judge), end-to-end pass. Uncorrected, reported as such.
3. Secondary: `F30 V3 A +T1v2` against the plan 23 arm, mitigation pass.
`F30 STRATUS` and `F30 B2 +FLAT` are shown for reference without tests, as in plan 23. Everything is reported whatever
the outcome, with the counts of discordant pairs.

## 4. How it runs

One Lab queue, `F30 V3 (plans 23 and 25)`, experiment name **`Final - Frozen 30 V3 - first try`**, two steps (the plan 23
arm, chosen on 16 Nov by its rule, then `F30 V3 A +T1v2`), `order: cell`, split by problem into **6 shares** (5 problems
each, the Lab's round-robin split). Built by `scripts/make_f30_v3_queue.py`, which copies the problem list, repeats,
model, judge and purpose from plan 19's queue (`7b033fffb6`), so the two queues cannot differ by hand. Runs that end on
an API quota or other infrastructure error are re-run, and counted and reported (plan 19 rule). Each machine runs with
its own keys, one key per Google Cloud project.

**Start order (16 Nov 10:45).** The dev-12 runs of share 5 were lost overnight (judge-check failures on that machine) and
must be re-run before the plan 23 rule can pick its arm. The plan 25 arm does not depend on that rule, so the queue was saved
with the `F30 V3 A +T1v2` step only (queue `fe1e776c37`, same name, experiment and 6 shares) and started first; the plan 23
arm is added to the same queue as a second step once the rule has picked it (`make_f30_v3_queue.py --arm X --queue-id
fe1e776c37 --post`). Same code, model, judge, problems and repeats; only the order in time differs.

**Duplicate cells (fixed 16 Nov 21:15, before any v3 frozen result is read).** A team machine ran the queue with no share
picked (all problems) for a while, so some cells may have two valid runs. For every arm, a cell counts once: its earliest
valid run by `timestamp_utc` (runs ended by an infrastructure error are not valid). Later duplicates are kept in the records
and reported as a count, not used in any test. The same rule applies to the plan 19 arms, where the same machine re-ran a
few cells of `F30 A`, `F30 B2 +FLAT` and `F30 STRATUS` under this experiment's name: those rows belong to plan 19's arms and
are not used here at all.

## 5. Analyses added (no extra runs; all fixed now, all reported)

1. **Second judge.** Re-judge every frozen-30 run of all five arms with a second judge model from another provider
   (OpenAI, the Lab's re-judge), after the v3 arms finish. Report each arm's diagnosis pass under both judges and the
   agreement (percent and Cohen's kappa). The first judge stays the one the tests use; the second shows whether a
   conclusion depends on the judge.
2. **What T1 did.** From the transcripts of the two v3 arms: runs with at least one write; proof reads asked and run;
   restores (by the model's `not_fixed`, by the T1 v2 driver) and whether the run then passed; T1 v2 verdicts
   (worse / no effect / partial / clear) against the final mitigation result. This shows the mechanism behind any gain
   and how often an automatic restore undid a fix that would have passed (the T1 v2 risk named in plan 24).
3. **Fix given a correct diagnosis.** Mitigation pass among runs whose diagnosis passed, per arm, so the fix-stage gain
   is separated from the diagnosis stage.
4. **Cost.** Model calls, input and output tokens and wall time per run, per arm (TOKEN_LOG), as median and total.
5. **Infrastructure losses.** Per arm: runs lost to quota, judge or cluster errors, and how they were re-run.

## 6. Known risks

The ones in plan 23 (overfitting to dev-12, simulator under-statement, three dev problems that fail in every arm, quota),
plus: T1 v2 restores on a 60 s check, so a slow but correct fix can be undone; and the restore of a deleted PVC is known to
leave it bound to the deleted volume (C-034, fixed in r4.5 only), which both T1 arms carry.

## Approval

- [x] Approved by the team lead: 16 Nov 2026 (see Status).
- [x] Frozen results read by anyone before approval: no pass/fail result (see Status for the screenshot of 04:38).
- Exposure noted 16 Nov 21:00: while checking the key proxy on the cloud machine, the end of a Lab queue log showed one action of an
  `F30 STRATUS` re-run on one frozen problem (a kubectl command it chose). No diagnosis, mitigation or judge result was
  shown; STRATUS is a reference arm without tests. Queue logs of frozen runs are not opened again; the proxy is checked
  only through its own log.
- Exposure noted 17 Nov 05:10: a Lab Queue-tab screenshot shared within the team showed a PASS / FAIL count per share of
  the v3 frozen queue (both arms pooled, metric not labelled) while 11 of its 180 runs were still to do. Seen by the team
  lead and the analysis assistant.
  Nothing decided after that point depends on results: arms, tests, the duplicate rule and the analyses were fixed before;
  the remaining work is finishing the same cells. From then on the Queue tab is used without that column until both arms
  are complete.
- Exposure noted 17 Nov 11:10: the first start of `scripts/rejudge_frozen.py` printed five second-judge verdicts
  (problem id and success true/false, arm not shown) for frozen runs, because its output filter let through every line
  containing "error" (each verdict line ends "error=None"). Seen by the analysis assistant only. The script was stopped within a minute, made
  progress-only, and restarted; nothing decided afterwards depends on those five lines (arms, tests and rules were fixed
  before; the v3 arms had 3 cells left, which run unchanged).
