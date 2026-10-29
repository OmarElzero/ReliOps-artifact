#!/usr/bin/env python3
"""Re-judge stored agent diagnoses with a (different) judge model, using SREGym's own judge.

Run it inside SREGym's environment, from the SREGym clone, so `sregym` imports and keys resolve:

    cd external/envs/sregym
    JUDGE_MODEL_ID=gemini/gemini-3.5-flash PYTHONPATH=. \
      uv run python ../../../scripts/rejudge.py --in items.jsonl --out verdicts.jsonl

Input  (JSONL): {"run_id": "...", "problem_id": "...", "submission": "<the agent's diagnosis text>"}
Output (JSONL): one record per input with judge_model_id, judgment, success, composite_score,
                dimensions (D1..), reasoning, checklist, error.

Why this exists: the Phase A plan (docs/plan/03-testing-plan.md) needs the same diagnoses graded by a
stronger judge and by a second model family, then compared with hand labels (Cohen's kappa). The
reference answer for each problem comes from SREGym's own Problem class (`root_cause`), the same
source the original judge used, so only the judge model changes.

`--dry-run` skips SREGym and the model entirely and writes clearly-labelled fake verdicts
(judge_model_id "dry-run"); it exists so the plumbing can be tested without keys or a cluster.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _problem_loader():
    """Returns a function problem_id -> Problem instance. SREGym's registry builds a kubectl client in
    its constructor; if there is no cluster/kubeconfig that can fail, so retry once with a stand-in
    client (problem classes only need `root_cause`, not a live cluster, to be judged)."""
    from sregym.conductor.problems import registry as reg  # type: ignore

    try:
        registry = reg.ProblemRegistry()
    except Exception:  # noqa: BLE001
        class _NoCluster:
            def is_emulated_cluster(self) -> bool:
                return False

        reg.KubeCtl = lambda *a, **k: _NoCluster()  # type: ignore[attr-defined]
        registry = reg.ProblemRegistry()
    return registry.get_problem_instance


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    judge_model = "dry-run" if args.dry_run else os.environ.get("JUDGE_MODEL_ID", "")
    if not args.dry_run and not judge_model:
        print("JUDGE_MODEL_ID is not set", file=sys.stderr)
        return 2

    items = [json.loads(l) for l in Path(args.inp).read_text(encoding="utf-8").splitlines() if l.strip()]
    get_problem = None
    oracle_cls = None
    if not args.dry_run:
        from sregym.conductor.oracles.llm_as_a_judge.llm_as_a_judge_oracle import LLMAsAJudgeOracle  # type: ignore

        oracle_cls = LLMAsAJudgeOracle
        get_problem = _problem_loader()

    with open(args.out, "w", encoding="utf-8") as out:
        for n, item in enumerate(items, start=1):
            rec = {"run_id": item.get("run_id"), "problem_id": item.get("problem_id"), "judge_model_id": judge_model,
                   "judgment": None, "success": None, "composite_score": None, "dimensions": {},
                   "reasoning": None, "checklist": [], "error": None}
            submission = (item.get("submission") or "").strip()
            try:
                if args.dry_run:
                    rec.update(judgment="True", success=True, composite_score=1.0, reasoning="dry-run, not a real verdict")
                elif not submission:
                    rec.update(error="empty submission, skipped")
                else:
                    problem = get_problem(item["problem_id"])
                    result = oracle_cls(problem=problem, expected=problem.root_cause).evaluate(submission)
                    rec.update(judgment=result.get("judgment"), success=result.get("success"),
                               composite_score=result.get("composite_score"), dimensions=result.get("dimensions") or {},
                               reasoning=result.get("reasoning"), checklist=result.get("checklist") or [],
                               error=result.get("error") if result.get("judgment") == "Error" else None)
            except Exception as e:  # noqa: BLE001 - one bad item must not stop the batch
                rec["error"] = f"{type(e).__name__}: {e}"
            out.write(json.dumps(rec, default=str) + "\n")
            out.flush()
            print(f"[{n}/{len(items)}] {item.get('problem_id')} -> success={rec['success']} error={rec['error']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
