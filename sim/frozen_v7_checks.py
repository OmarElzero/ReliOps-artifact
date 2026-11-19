"""Checks asked for by the reviews of AGENT paper v6, from the exported run records only (stdlib).

  python3 sim/frozen_v7_checks.py [--runs artifact-data/runs.csv] [--judge2 artifact-data/second_judge.csv]

1. Where duplicate valid runs come from (machine, delay after the counted run, same machine or not).
2. Same-machine split: each configuration vs A on cells whose two counted runs share a machine, and on the rest.
3. A's mitigation rate by machine; the machine mix of each configuration.
4. Run-to-run noise: for each configuration, counted run vs its later valid duplicate of the same cell (agreement).
5. Holm over the three problem-level sign tests of the gate configurations (post-hoc).
6. Run ledger by phase and experiment bucket.
"""
import argparse, collections, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from frozen_recompute import ARMS, FROZEN, INFRA, is_infra, load, sign_test, holm  # noqa: E402

HOME = {"F30 A": FROZEN[0], "F30 B2 +FLAT": FROZEN[0], "F30 STRATUS": FROZEN[0],
        "F30 V3 A +CARDS +T1": FROZEN[1], "F30 V3 A +T1v2": FROZEN[1], "F30 V5": FROZEN[2]}
GATES = ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2", "F30 V5"]


def valid_runs(runs):
    """{arm: {(problem, repeat): [valid runs, earliest first]}}"""
    out = {a: collections.defaultdict(list) for a in ARMS}
    for r in sorted(runs, key=lambda r: r.get("started_utc") or ""):
        a = r.get("arm")
        if a in HOME and r.get("experiment") == HOME[a] and not is_infra(r):
            out[a][(r["problem_id"], str(r.get("repeat")))].append(r)
    return out


def ok(r, k="m"):
    return r.get("mitigation") == "True" if k == "m" else r.get("diagnosis_judge1") == "True"


def hours(a, b):
    from datetime import datetime
    f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (f(b) - f(a)).total_seconds() / 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="artifact-data/runs.csv")
    ap.add_argument("--judge2", default="artifact-data/second_judge.csv")
    a = ap.parse_args()
    runs, j2 = load(a.runs, a.judge2)
    V = valid_runs(runs)
    first = {arm: {c: rs[0] for c, rs in V[arm].items()} for arm in ARMS}
    L = ["# Frozen 30: checks for paper v7 (from artifact-data)", ""]

    L += ["## 1. Duplicate valid runs", "", "| Configuration | cells with >1 valid run | extra runs | same machine as counted run | median hours after counted run |", "|---|---|---|---|---|"]
    for arm in ARMS:
        extra = [(rs[0], r) for rs in V[arm].values() for r in rs[1:]]
        same = sum(x["machine"] == y["machine"] for x, y in extra)
        hs = sorted(hours(x["started_utc"], y["started_utc"]) for x, y in extra)
        med = hs[len(hs) // 2] if hs else float("nan")
        L.append(f"| {arm} | {sum(len(rs) > 1 for rs in V[arm].values())} | {len(extra)} | {same} | {med:.1f} |")
    for arm in ARMS:
        extra = [(rs[0], r) for rs in V[arm].values() for r in rs[1:]]
        mach = collections.Counter((x["machine"], y["machine"]) for x, y in extra)
        L.append(f"- {arm}: (counted machine, duplicate machine) {dict(mach.most_common(6))}")

    L += ["", "## 2. Same-machine split, mitigation vs A (discordant cells: configuration better : A better)", "",
          "| Configuration | same-machine cells | split there | other cells | split there |", "|---|---|---|---|---|"]
    for arm in ARMS:
        if arm == "F30 A":
            continue
        same = [c for c in first[arm] if c in first["F30 A"] and first[arm][c]["machine"] == first["F30 A"][c]["machine"]]
        other = [c for c in first[arm] if c in first["F30 A"] and c not in same]
        def split(cs):
            b = sum(ok(first[arm][c]) and not ok(first["F30 A"][c]) for c in cs)
            d = sum(ok(first["F30 A"][c]) and not ok(first[arm][c]) for c in cs)
            return f"{b}:{d}, p = {sign_test(b, d):.3f}"
        L.append(f"| {arm} | {len(same)} | {split(same)} | {len(other)} | {split(other)} |")

    L += ["", "## 3. Machines", ""]
    for arm in ARMS:
        by = collections.defaultdict(list)
        for r in first[arm].values():
            by[r["machine"]].append(ok(r))
        L.append(f"- {arm}: " + ", ".join(f"{m} {sum(v)}/{len(v)}" for m, v in sorted(by.items(), key=lambda kv: -len(kv[1]))))

    L += ["", "## 4. Run-to-run agreement (counted run vs the next valid run of the same cell, same configuration)", "",
          "| Configuration | pairs | mitigation agree | diagnosis J1 agree | mitigation pass, counted vs next |", "|---|---|---|---|---|"]
    tot = collections.Counter()
    for arm in ARMS:
        prs = [(rs[0], rs[1]) for rs in V[arm].values() if len(rs) > 1]
        am = sum(ok(x) == ok(y) for x, y in prs)
        ad = sum(ok(x, "d") == ok(y, "d") for x, y in prs)
        tot.update(n=len(prs), m=am, d=ad)
        L.append(f"| {arm} | {len(prs)} | {am}/{len(prs)} | {ad}/{len(prs)} | {sum(ok(x) for x, _ in prs)} vs {sum(ok(y) for _, y in prs)} |")
    L.append(f"| all | {tot['n']} | {tot['m']}/{tot['n']} | {tot['d']}/{tot['n']} | |")

    L += ["", "## 5. Problem-level sign tests of the gate configurations vs A, Holm over the three (post-hoc)", ""]
    pv = {}
    for arm in GATES:
        per = collections.defaultdict(lambda: [0, 0])
        for (p, _), r in first[arm].items():
            per[p][0] += ok(r)
        for (p, _), r in first["F30 A"].items():
            per[p][1] += ok(r)
        b = sum(x > y for x, y in per.values())
        c = sum(y > x for x, y in per.values())
        pv[arm] = sign_test(b, c)
        L.append(f"- {arm}: {b}:{c}, p = {pv[arm]:.4f}")
    for arm, (p, bar, sig) in holm(pv).items():
        L.append(f"- Holm: {arm} p = {p:.4f} vs bar {bar:.4f}: {'significant' if sig else 'not significant'}")
    # Holm-adjusted p values
    srt = sorted(pv.items(), key=lambda kv: kv[1])
    adj, run_max = {}, 0
    for i, (k, p) in enumerate(srt):
        run_max = max(run_max, min(1, (len(srt) - i) * p))
        adj[k] = run_max
    L.append("- Holm-adjusted p: " + ", ".join(f"{k} {v:.3f}" for k, v in adj.items()))

    L += ["", "## 6. Run ledger", ""]
    ph = collections.Counter(r["phase"] for r in runs)
    L.append(f"- by phase: {dict(ph)}; total {len(runs)}")
    fz = collections.Counter((r["experiment"], r["arm"] if r["arm"] in HOME and HOME.get(r['arm']) == r['experiment'] else "other label")
                             for r in runs if r["phase"] == "frozen")
    L.append(f"- frozen by (experiment, arm or stray): {dict(fz)}")
    cal = collections.Counter(r["experiment"] for r in runs if r["phase"] == "calibration")
    L.append(f"- calibration: {dict(cal)}")
    dev = collections.Counter(r["experiment"] or "(none)" for r in runs if r["phase"] == "development")
    L.append(f"- development experiments ({len(dev)}): {dict(dev.most_common(8))} ...")
    print("\n".join(L))


if __name__ == "__main__":
    main()
