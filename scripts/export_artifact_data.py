"""Export the run records behind the AGENT 2027 paper as plain CSV, so reviewers can recompute every number offline.

Reads Firestore through the Lab (needs a machine whose Lab reaches Firestore) and writes:
  artifact-data/runs.csv          every stored run (development, calibration, frozen), one row each, graded outcome only
  artifact-data/second_judge.csv  every second-judge verdict (run_id, judge model, pass/fail)
  artifact-data/README.md         column meanings and row counts

Nothing private leaves: no prompts, no transcripts, no keys. Machine names become machine-1, machine-2, ... (the mapping
is printed to the terminal, not written). Free-text failure reasons are cut to 160 characters and scrubbed of anything
that looks like a key, a token, an e-mail address or a URL query string.

  /root/ReliOps-Lab/.venv/bin/python scripts/export_artifact_data.py [--out artifact-data] [--list-fields]
--list-fields prints the keys seen on 200 run records and exits (to check the column whitelist below).
"""
import argparse, collections, csv, re, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/root/ReliOps-Lab/backend")

FROZEN = ("Final - Frozen 30 confirmation - first try", "Final - Frozen 30 V3 - first try",
          "Final - Frozen 30 V5 - first try")
CAL_PREFIX = "Calibration - null agent - frozen 30"
# Run-record keys copied as they are, when present (first match wins for each output column).
COLUMNS = {
    "run_id": ["run_id"], "experiment": ["experiment"], "arm": ["config_label"], "problem_id": ["problem_id"],
    "repeat": ["repeat_index"], "started_utc": ["timestamp_utc"], "agent_model": ["model_id", "model", "agent_model"],
    "judge_model": ["judge_model_id", "judge_model"], "agent_commit": ["reliops_commit", "agent_commit", "commit"],
    "llm_calls": ["num_llm_calls"], "total_tokens": ["total_tokens"], "duration_s": ["duration_s"],
    "incomplete_kind": ["incomplete_kind"], "run_class": ["run_class"],
}
SECRETISH = [re.compile(p) for p in (r"AIza[0-9A-Za-z_\-]{10,}", r"sk-[A-Za-z0-9_\-]{10,}", r"gsk_[A-Za-z0-9]{10,}",
                                     r"gh[pousr]_[A-Za-z0-9]{10,}", r"github_pat_[A-Za-z0-9_]{10,}",
                                     r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", r"\?[^\s\"']*=[^\s\"']*",
                                     r"\b[A-Za-z0-9_\-]{32,}\b")]


def scrub(text: str) -> str:
    t = " ".join((text or "").split())[:160]
    for p in SECRETISH:
        t = p.sub("[removed]", t)
    return t


def phase(exp: str) -> str:
    if exp in FROZEN:
        return "frozen"
    if exp.startswith(CAL_PREFIX):
        return "calibration"
    return "development"


def flat(r: dict, machines: dict) -> dict:
    out = {}
    for col, keys in COLUMNS.items():
        out[col] = next((r.get(k) for k in keys if r.get(k) not in (None, "")), "")
    row = r.get("row") or {}
    out["diagnosis_judge1"] = row.get("Diagnosis.success", "")
    out["mitigation"] = row.get("Mitigation.success", "")
    out["phase"] = phase(out["experiment"] or "")
    who = r.get("run_by") or r.get("machine") or ""
    out["machine"] = machines.setdefault(who, f"machine-{len(machines) + 1}") if who else ""
    out["incomplete_reason"] = scrub(r.get("incomplete_reason") or "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "artifact-data"))
    ap.add_argument("--list-fields", action="store_true")
    a = ap.parse_args()
    import firebase_sync  # noqa: E402
    firebase_sync.try_auto_connect()
    cl = firebase_sync._client
    if a.list_fields:
        seen = collections.Counter()
        for d in cl.collection("runs").limit(200).stream():
            seen.update(d.to_dict().keys())
        for k, n in seen.most_common():
            print(f"{n:4d} {k}")
        return 0
    runs = [d.to_dict() for d in cl.collection("runs").stream()]
    machines: dict = {}
    rows = sorted((flat(r, machines) for r in runs), key=lambda x: (x["phase"], x["experiment"], x["started_utc"] or ""))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["run_id", "phase", "experiment", "arm", "problem_id", "repeat", "started_utc", "machine", "agent_model",
            "judge_model", "agent_commit", "diagnosis_judge1", "mitigation", "llm_calls", "total_tokens", "duration_s",
            "incomplete_kind", "incomplete_reason", "run_class"]
    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    rj = []
    for d in cl.collection("rejudges").stream():
        r = d.to_dict()
        if isinstance(r.get("success"), bool) and r.get("run_id"):
            rj.append({"run_id": r["run_id"], "judge_model": r.get("judge_model_id", ""), "success": r["success"]})
    with open(out / "second_judge.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run_id", "judge_model", "success"])
        w.writeheader()
        w.writerows(sorted(rj, key=lambda x: (x["judge_model"], x["run_id"])))
    by_phase = collections.Counter(r["phase"] for r in rows)
    (out / "README.md").write_text(
        "# Run records (exported from the Lab's store)\n\n"
        f"`runs.csv`: {len(rows)} runs ({', '.join(f'{k} {v}' for k, v in sorted(by_phase.items()))}). One row per stored "
        "run, including runs lost to infrastructure (see `incomplete_reason`; the infrastructure rule is `INFRA` in "
        "`sim/frozen_recompute.py`). `diagnosis_judge1` and `mitigation` are SREGym's graded outcomes (`True`/`False`, "
        "empty when the run did not reach grading). `machine` is a stable pseudonym. `incomplete_reason` is cut to 160 "
        "characters and scrubbed.\n\n"
        f"`second_judge.csv`: {len(rj)} second-judge verdicts (diagnosis only), keyed by `run_id`.\n\n"
        "Recompute the frozen-set table and tests: `python3 sim/frozen_recompute.py --runs artifact-data/runs.csv "
        "--judge2 artifact-data/second_judge.csv`.\n", encoding="utf-8")
    print(f"wrote {len(rows)} runs ({dict(by_phase)}), {len(rj)} second-judge verdicts to {out}")
    print("machine pseudonyms (not written):", {v: k for k, v in machines.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
