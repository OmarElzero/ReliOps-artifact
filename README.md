# ReliOps artifact

Companion repository for the AGENT 2027 short paper **"Trusting AI SRE Agent Comparisons: Lessons from 3,391 Live
Kubernetes Runs"** (O. Betawy, N. Yasser, A. Mohamed, A. Shaban, Z. Mohamed; Faculty of Computing and Artificial
Intelligence, Cairo University).

It holds what a reader needs to check the paper: the pre-registered plans, the problem sets, the agent code of every
configuration, the run records, and the scripts that turn the records into the paper's numbers.

## Recompute the paper's frozen-set results

Python 3.9 or later, standard library only:

```
python3 sim/frozen_recompute.py      # Table III: rates, kappa, losses, sign tests, Holm, do-nothing calibration
python3 sim/frozen_v7_checks.py      # run ledger, duplicate runs, same-machine split, run-to-run agreement
python3 -m unittest discover -s sim -p "test_frozen_*.py"
```

Both read `artifact-data/runs.csv` (one row per recorded run, 3,391 rows) and `artifact-data/second_judge.csv`.

## Where each claim is checked

| Paper | Files |
|---|---|
| Pre-registered frozen protocol | `docs/plan/19-frozen-30-preregistration.md` (12 Nov), `23-…` (15 Nov), `25-…` (16 Nov), `27-…` (17 Nov). Their git history shows each plan's commits; the frozen results were first read on 17 Nov at 11:49 (+02:00), the commit that adds `results/frozen30_analysis.md`. |
| Problem sets | `experiments/first-30.csv` (frozen 30), `experiments/dev-12.csv` (development 12), pinned by hash in `experiments/pins.json` |
| Reference answers the judges compare against | `experiments/frozen30-reference-answers.json` (SREGym's `root_cause`, dumped by `scripts/dump_root_causes.py`) |
| Agent code | `agent/react_v2`: Base (`TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS FLAT_ARGS`) and A (adds `ROUTING ROUTE_REVIEW PROC_V2`). `agent/react_v3_r4`: A+cards+gate and A+driver gate (plan 23). `agent/react_v3_r5`: V5 (r5.1, plan 27). STRATUS is the published agent ([xlab-uiuc/stratus](https://github.com/xlab-uiuc/stratus)). |
| Evidence cards | `experiments/problem-cards/` |
| Table I-III, judge agreement, Holm | `results/frozen30_analysis.md` (written on 17 Nov from the Lab's store) and `results/frozen30_recompute.md` (from the CSVs) |
| Problem-level tests, bootstrap intervals, rerun sensitivity, pairing | `results/frozen30_review_followups.md` |
| Run ledger, duplicate valid runs, same-machine split, machine mix, run-to-run agreement | `results/frozen30_v7_checks.md` |
| Cost, fix-gate events, example cell | `results/frozen30_paper_facts.md` |
| Development rounds (Table II, L1-L5) | `results/r2-main-screening-2026-11-11.md`, `r3-first-try-2026-11-10.md`, `r4-interim-2026-11-12.md`, `r4-review-2026-11-14.md`, `final-r2-r3-2026-11-11.md` |
| Development hand label (40 diagnoses) | `experiments/judge-audit/` and `results/final-r2-r3-2026-11-11.md` |
| Second judge | `scripts/rejudge.py`, `scripts/rejudge_frozen.py` |
| Changes to the benchmark | `scripts/apply_sregym_patches.py` (see `REPRODUCE.md`) |

## The run records

`artifact-data/runs.csv` holds every stored run: development (2,449), frozen (792) and do-nothing calibration (150).
Each row has the configuration, problem, repeat, start time, machine (as a pseudonym, `machine-1` to `machine-9`;
`machine-4` is the cloud machine), model, agent commit, the graded outcome, calls, tokens, duration, and the reason a
run ended without a result. Prompts, transcripts and diagnosis texts are not included. Column meanings:
`artifact-data/README.md`.

The scripts `sim/frozen_analysis.py`, `frozen_followups.py`, `frozen_paper_facts.py`, `frozen_review_followups.py` and
`scripts/rejudge_frozen.py` read the Lab's store directly; they are here so their rules can be read. `frozen_recompute.py`
applies the same rules to the CSVs.

## Notes on the plans

- The plans were written as working documents. For publication, every commit of this history was edited on 19 Nov 2026
  with `git filter-repo`: names of people and machines were replaced by roles and pseudonyms, internal remarks were
  removed, and pointers to files that are not published were replaced. Rules, numbers, dates, times, commit order and
  the agent code were not changed. The unedited history is kept in the team's private repository and can be shown to
  the programme chairs on request. "The team lead" is the first author. "The analysis assistant" is the AI assistant (Claude, Anthropic)
  that drafted plans and analysis code and ran the analyses under the team's direction.
- References to other plans (for example plan 16, 22, 24 or 26) and to `docs/...` point to the team's internal notes,
  which are not part of this artifact.
- The do-nothing calibration has two tries; only the second counts (the first ran the plain agent by mistake).

## Running the agents

See `REPRODUCE.md`. Runs were driven by ReliOps Lab ([OmarElzero/ReliOps-Lab](https://github.com/OmarElzero/ReliOps-Lab)).
