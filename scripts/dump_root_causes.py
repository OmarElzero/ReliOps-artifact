"""Print SREGym's reference answer (`root_cause`) for each listed problem as one JSON object {problem_id: text}.

This is the text both judges compare a diagnosis against (scripts/rejudge.py uses the same Problem classes). It needs no
cluster. Run it inside the SREGym clone:
  cd <SREGym clone> && uv run python <ReliOps>/scripts/dump_root_causes.py --problems-csv <ReliOps>/experiments/first-30.csv
"""
import argparse
import csv
import json
import sys


def loader():
    from sregym.conductor.problems import registry as reg  # type: ignore

    class _NoCluster:
        def is_emulated_cluster(self) -> bool:
            return False

        def __getattr__(self, name):          # any other kubectl call is a no-op stand-in
            return lambda *a, **k: None

    try:
        r = reg.ProblemRegistry()
    except Exception:  # noqa: BLE001
        reg.KubeCtl = lambda *a, **k: _NoCluster()  # type: ignore[attr-defined]
        r = reg.ProblemRegistry()
    return r.get_problem_instance


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems-csv", required=True, help="a CSV with a problem_id column (experiments/first-30.csv)")
    a = ap.parse_args()
    ids = [row["problem_id"] for row in csv.DictReader(open(a.problems_csv, encoding="utf-8"))]
    get = loader()
    out, missing = {}, []
    for pid in ids:
        try:
            out[pid] = str(get(pid).root_cause)
        except Exception as e:  # noqa: BLE001
            missing.append(f"{pid}: {type(e).__name__}: {str(e)[:120]}")
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    for m in missing:
        print("missing " + m, file=sys.stderr)
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
