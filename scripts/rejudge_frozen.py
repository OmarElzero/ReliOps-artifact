#!/usr/bin/env python3
"""Second judge on the frozen 30 (docs/plan/25 section 5, item 1): re-judge every valid run of the five frozen arms
(plan 19: F30 A, F30 B2 +FLAT, F30 STRATUS; plans 23/25: F30 V3 A +CARDS +T1, F30 V3 A +T1v2) with a judge from another
provider, through the Lab's own re-judge (SREGym's judge and reference answers; only the judge model changes).

Run AFTER both v3 arms are complete, with the Lab's venv:
  /root/ReliOps-Lab/.venv/bin/python scripts/rejudge_frozen.py [--model openai/gpt-5.4] [--dry-run]

Needs OPENAI_API_KEY in the Lab's .env. Reads the two frozen experiments from Firestore once (a few hundred reads); skips
runs that already have a verdict from this model; each verdict is stored as soon as it arrives (Lab store "rejudges":
results/gui_rejudges.jsonl and Firestore), so a stopped run can simply be started again. Prints progress only.
"""
import argparse, collections, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/root/ReliOps-Lab/backend")
import firebase_sync, runner, store  # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402

EXPERIMENTS = {"Final - Frozen 30 confirmation - first try": ("F30 A", "F30 B2 +FLAT", "F30 STRATUS"),
               "Final - Frozen 30 V3 - first try": ("F30 V3 A +CARDS +T1", "F30 V3 A +T1v2")}
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-5.4", help="second judge (the 12 Nov second judge was openai/gpt-5.4)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not runner.merged_env_vars().get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not in the Lab's .env")
    print("firebase:", firebase_sync.try_auto_connect())
    have = {r["run_id"] for r in store.read("rejudges")
            if r.get("judge_model_id") == a.model and isinstance(r.get("success"), bool)}
    items, per_arm = [], collections.Counter()
    for exp, arms in EXPERIMENTS.items():
        rows = [d.to_dict() for d in firebase_sync._client.collection("runs")
                .where(filter=FieldFilter("experiment", "==", exp)).stream()]
        for r in rows:
            if r.get("config_label") not in arms or any(k in (r.get("incomplete_reason") or "") for k in INFRA):
                continue
            if not (r.get("diagnosis_text") or "").strip() or r["run_id"] in have:
                continue
            items.append({"run_id": r["run_id"], "problem_id": r["problem_id"], "submission": r["diagnosis_text"]})
            per_arm[r["config_label"]] += 1
    print(f"to re-judge with {a.model}: {len(items)} runs", dict(per_arm), f"({len(have)} already done)")
    if a.dry_run or not items:
        return
    n = 0
    for line in runner.stream_rejudge(a.model, items, on_result=lambda rec: store.append("rejudges", rec)):
        if "verdict" in line.lower() or "judged" in line.lower():
            n += 1
            if n % 25 == 0:
                print(f"  {n}/{len(items)} done", flush=True)
        elif any(w in line.lower() for w in ("error", "stopped", "not found", "full log")):
            print(" ", line.strip()[:200], flush=True)
    print("finished")


if __name__ == "__main__":
    main()
