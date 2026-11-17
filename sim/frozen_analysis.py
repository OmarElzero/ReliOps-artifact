"""Frozen-30 analysis as pre-registered (plans 19, 23, 25): per arm diagnosis (first judge), mitigation and end-to-end
pass; paired exact sign tests against F30 A (Holm over the two v3 arms for mitigation); second judge (openai/gpt-5.4)
diagnosis pass and agreement (percent, Cohen's kappa). One cell = (problem, repeat); its earliest valid run counts
(plan 25 rule); runs that ended on an infrastructure error are not valid.
  /root/ReliOps-Lab/.venv/bin/python sim/frozen_analysis.py [--out results/frozen30_analysis.md]"""
import argparse, collections, json, math, sys, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/root/ReliOps-Lab/backend")
import firebase_sync, store  # noqa: E402
from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402

ARMS = {"Final - Frozen 30 confirmation - first try": ["F30 A", "F30 B2 +FLAT", "F30 STRATUS"],
        "Final - Frozen 30 V3 - first try": ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2"],
        "Final - Frozen 30 V5 - first try": ["F30 V5"]}
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")
JUDGE2 = "openai/gpt-5.4"


def sign_test(b, c):
    """Two-sided exact sign test on discordant pairs (b = arm wins, c = A wins)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def kappa(pairs):
    n = len(pairs)
    if not n:
        return float("nan"), float("nan")
    agree = sum(a == b for a, b in pairs) / n
    pa = sum(a for a, _ in pairs) / n
    pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return agree, (agree - pe) / (1 - pe) if pe < 1 else float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/frozen30_analysis.md")
    a = ap.parse_args()
    firebase_sync.try_auto_connect()
    cl = firebase_sync._client
    rj = {}
    for r in store.read("rejudges"):
        if r.get("judge_model_id") == JUDGE2 and isinstance(r.get("success"), bool):
            rj[r["run_id"]] = r["success"]
    cells, dups = {}, collections.Counter()
    for exp, arms in ARMS.items():
        rows = [d.to_dict() for d in cl.collection("runs").where(filter=FieldFilter("experiment", "==", exp)).stream()]
        for r in sorted(rows, key=lambda r: r.get("timestamp_utc") or ""):
            arm = r.get("config_label")
            if arm not in arms or any(k in (r.get("incomplete_reason") or "") for k in INFRA):
                continue
            key = (arm, r["problem_id"], r.get("repeat_index"))
            if key in cells:
                dups[arm] += 1
                continue
            row = r.get("row") or {}
            d, m = row.get("Diagnosis.success") == "True", row.get("Mitigation.success") == "True"
            cells[key] = {"d": d, "m": m, "e": d and m, "d2": rj.get(r["run_id"]), "run_id": r["run_id"]}
    arms = [x for v in ARMS.values() for x in v]
    by = {arm: {(p, i): v for (a2, p, i), v in cells.items() if a2 == arm} for arm in arms}
    out = ["# Frozen 30: results (plans 19, 23, 25)", "",
           "One cell = (problem, repeat); earliest valid run counts; infrastructure failures excluded and re-run.", "",
           "| Arm | cells | diagnosis (judge 1) | mitigation | end-to-end | diagnosis (gpt-5.4) | judge agreement (kappa) | duplicates |",
           "|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        c = by[arm]
        if not c:
            out.append(f"| {arm} | 0 | | | | | | |"); continue
        n = len(c)
        f = lambda k: sum(v[k] for v in c.values())
        pairs = [(v["d"], v["d2"]) for v in c.values() if v["d2"] is not None]
        ag, kp = kappa(pairs)
        d2 = sum(b for _, b in pairs)
        out.append(f"| {arm} | {n} | {f('d')}/{n} ({100*f('d')/n:.0f}%) | {f('m')}/{n} ({100*f('m')/n:.0f}%) | "
                   f"{f('e')}/{n} ({100*f('e')/n:.0f}%) | {d2}/{len(pairs)} | {100*ag:.0f}% ({kp:.2f}) | {dups[arm]} |")
    out += ["", "## Paired sign tests against F30 A (two-sided exact, discordant pairs: arm better : A better)", "",
            "| Arm | mitigation | diagnosis | end-to-end |", "|---|---|---|---|"]
    base = by["F30 A"]
    pm = {}
    for arm in arms:
        if arm == "F30 A" or not by[arm]:
            continue
        row = [arm]
        for k in ("m", "d", "e"):
            common = set(base) & set(by[arm])
            b = sum(by[arm][x][k] and not base[x][k] for x in common)
            c = sum(base[x][k] and not by[arm][x][k] for x in common)
            p = sign_test(b, c)
            if k == "m":
                pm[arm] = p
            row.append(f"{b}:{c}, p = {p:.3f} (n = {len(common)})")
        out.append("| " + " | ".join(row) + " |")
    v3 = [x for x in ("F30 V3 A +CARDS +T1", "F30 V3 A +T1v2") if x in pm]
    if len(v3) == 2:
        order = sorted(v3, key=lambda x: pm[x])
        h = {order[0]: pm[order[0]] < 0.025, order[1]: pm[order[0]] < 0.025 and pm[order[1]] < 0.05}
        out += ["", "Holm (plan 25, the two primary mitigation tests): " +
                "; ".join(f"{x}: p = {pm[x]:.3f}, {'significant' if h[x] else 'not significant'}" for x in v3)]
    text = "\n".join(out) + "\n"
    open(a.out, "w").write(text)
    print(text)


if __name__ == "__main__":
    main()
