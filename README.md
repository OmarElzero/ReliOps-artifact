# ReliOps artifact: trusting AI SRE agent comparisons

Companion to the AGENT 2027 workshop paper *"Trusting AI SRE Agent Comparisons: Lessons from 3,391 Live Kubernetes
Runs"*. ReliOps is a graduation research project (Faculty of Computing and Artificial Intelligence, Cairo University).

This repository is a filtered copy of the team's working repository. It keeps only the files a reviewer needs, and it
keeps **their original git history and commit dates**, so you can check that each pre-registration was committed before
the frozen results were read (git commit dates are written by the committer's machine; the run timestamps in the Lab's
store are independent of them).

## Claims and where to check them

| Paper item | Where |
|---|---|
| Pre-registered frozen protocol (problems, arms, rules, tests) | `docs/plan/19-frozen-30-preregistration.md` (12 Nov), `23-...` (15 Nov), `25-...` (16 Nov), `27-...` (17 Nov). The frozen results were first read on 17 Nov at 11:49 (+0200): see the commit that adds `results/frozen30_analysis.md` |
| Development rounds and the decisions they drove | `docs/plan/12`, `13`, `15`, `16`, `22`, `24`, `26`; `results/r2-main-screening-*`, `r3-first-try-*`, `r4-interim-*`, `r4-review-*`, `final-r2-r3-*` |
| The 30 frozen problems and the 12 development problems | `experiments/first-30.csv`, `experiments/dev-12.csv` (pinned by hash in `experiments/pins.json`) |
| Reference answers the judges compare against | `experiments/frozen30-reference-answers.json` (dumped from SREGym by `scripts/dump_root_causes.py`) |
| Agent code per configuration | Base and A: `agent/react_v2` with the switches listed in plan 19 (Base: `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS FLAT_ARGS`; A adds `ROUTING ROUTE_REVIEW PROC_V2`); A+cards+gate and A+driver gate: `agent/react_v3_r4` (pin in plan 23); V5: `agent/react_v3_r5` (r5.1, pin in plan 27). STRATUS: the published agent, run through the Lab ([xlab-uiuc/stratus](https://github.com/xlab-uiuc/stratus)) |
| Problem cards (the "cards" configurations) | `experiments/problem-cards/` |
| Changes to the benchmark | `scripts/apply_sregym_patches.py` |
| Second judge (GPT-5.4 with SREGym's judge prompt) | `scripts/rejudge.py`, `scripts/rejudge_frozen.py` |
| Table III, sign tests, Holm, kappa | `results/frozen30_analysis.md` (written by `sim/frozen_analysis.py` from the Lab's store); **offline recompute:** `sim/frozen_recompute.py` |
| Problem-level tests, bootstrap intervals, E2E under the second judge, rerun sensitivity, pairing, run accounting | `results/frozen30_review_followups.md` (`sim/frozen_review_followups.py`) |
| Cost per configuration, fix-gate counts, example cell, run total | `results/frozen30_paper_facts.md` (`sim/frozen_paper_facts.py`) |
| Do-nothing calibration and hand label | `sim/frozen_followups.py` (+ tests); results in `results/` when present |
| Earlier judge check (development, 40 diagnoses, three labelers) | `experiments/judge-audit/` |
| Run records | `artifact-data/runs.csv` and `artifact-data/second_judge.csv` (see `artifact-data/README.md`) |

## Recompute the frozen results

Python 3.9 or later, no packages:

```
python3 sim/frozen_recompute.py --runs artifact-data/runs.csv --judge2 artifact-data/second_judge.csv
python3 -m unittest discover -s sim -p "test_frozen_recompute.py"
```

The scripts named `frozen_analysis.py`, `frozen_paper_facts.py`, `frozen_followups.py`, `frozen_review_followups.py` and
`rejudge_frozen.py` read the Lab's Firestore store directly and need the Lab
([ReliOps-Lab](https://github.com/OmarElzero/ReliOps-Lab)); they are here so the rules can be read. `frozen_recompute.py`
applies the same rules to the exported CSV.

## Re-running the agents

The runs were made with the ReliOps Lab (public: [OmarElzero/ReliOps-Lab](https://github.com/OmarElzero/ReliOps-Lab))
driving SREGym on kind clusters, with `gemini/gemini-3.5-flash-lite` as the agent model and first judge. Setup notes:
`experiments/testbed-setup.md`. A live run needs a model API key and about 9 minutes per problem; results will vary
run to run, which is the point of the paper.

## What is not here

Prompts, agent transcripts and model replies (they can contain API error text and were not reviewed for release), the
team's internal notes, and API keys. Machine names in the run records are pseudonyms.
