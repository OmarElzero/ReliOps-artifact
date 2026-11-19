# Run records (exported from the Lab's store)

`runs.csv`: 3391 runs (calibration 150, development 2449, frozen 792). One row per stored run, including runs lost to infrastructure (see `incomplete_reason`; the infrastructure rule is `INFRA` in `sim/frozen_recompute.py`). `diagnosis_judge1` and `mitigation` are SREGym's graded outcomes (`True`/`False`, empty when the run did not reach grading). `machine` is a stable pseudonym. `incomplete_reason` is cut to 160 characters and scrubbed. The `calibration` phase holds both null-agent experiments; only `Calibration - null agent - frozen 30 - second try` is the do-nothing calibration (the first try ran agent code that ignored NULL_AGENT, i.e. the plain v2 agent; `sim/frozen_recompute.py` uses the second try only). 

`second_judge.csv`: 1526 second-judge verdicts (diagnosis only), keyed by `run_id`.

Recompute the frozen-set table and tests: `python3 sim/frozen_recompute.py --runs artifact-data/runs.csv --judge2 artifact-data/second_judge.csv`.
