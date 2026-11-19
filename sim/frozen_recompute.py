"""Recompute the frozen-30 results table and tests offline, from the exported CSVs (no Firestore, no cluster, stdlib only).

Same rules as sim/frozen_analysis.py (plans 19, 23, 25, 27):
  - one cell = (arm, problem, repeat); the earliest valid run counts; later valid runs of a counted cell are duplicates;
  - a run is lost to infrastructure (not scored, re-run) when its incomplete_reason contains any INFRA marker;
  - any other incomplete run counts as a failure;
  - end-to-end = diagnosis (first judge) and mitigation; E2E-J2 = second-judge diagnosis and mitigation;
  - paired exact two-sided sign test on discordant cells; Holm over the primary tests.

  python3 sim/frozen_recompute.py --runs artifact-data/runs.csv --judge2 artifact-data/second_judge.csv [--out FILE]
"""
import argparse, collections, csv, math, sys

ARMS = ["F30 B2 +FLAT", "F30 A", "F30 V3 A +CARDS +T1", "F30 V3 A +T1v2", "F30 V5", "F30 STRATUS"]
FROZEN = ("Final - Frozen 30 confirmation - first try", "Final - Frozen 30 V3 - first try",
          "Final - Frozen 30 V5 - first try")
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")
JUDGE2 = "openai/gpt-5.4"
# The do-nothing calibration is the "second try" only: the "first try" (4 Nov) ran agent code that ignored NULL_AGENT, so it
# ran as the plain v2 agent and must not be used (team log, 4 Nov 2026 noon).
CAL_EXPERIMENT = "Calibration - null agent - frozen 30 - second try"
# Each arm counts only inside its own frozen experiment (as sim/frozen_analysis.py); three stray rows labelled F30 A,
# F30 B2 +FLAT and F30 STRATUS in the V3 experiment are not part of those arms.
ARM_EXPERIMENT = {"F30 A": FROZEN[0], "F30 B2 +FLAT": FROZEN[0], "F30 STRATUS": FROZEN[0],
                  "F30 V3 A +CARDS +T1": FROZEN[1], "F30 V3 A +T1v2": FROZEN[1], "F30 V5": FROZEN[2]}
PRIMARY = [("plan 19: A vs base, E2E", "F30 B2 +FLAT", "e"),
           ("plan 25: A+cards+gate vs A, mitigation", "F30 V3 A +CARDS +T1", "m"),
           ("plan 25: A+driver gate vs A, mitigation", "F30 V3 A +T1v2", "m"),
           ("plan 27: V5 vs A, mitigation", "F30 V5", "m")]


def sign_test(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def kappa(pairs):
    n = len(pairs)
    if not n:
        return float("nan"), float("nan")
    agree = sum(a == b for a, b in pairs) / n
    pa, pb = sum(a for a, _ in pairs) / n, sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return agree, ((agree - pe) / (1 - pe) if pe < 1 else float("nan"))


def holm(pvals: dict, alpha: float = 0.05) -> dict:
    """Step-down Holm: sort ascending, compare the i-th smallest (0-based) with alpha/(m-i); stop at the first miss."""
    m, out, go = len(pvals), {}, True
    for i, (k, p) in enumerate(sorted(pvals.items(), key=lambda kv: kv[1])):
        bar = alpha / (m - i)
        go = go and p < bar
        out[k] = (p, bar, go)
    return out


def is_infra(r: dict) -> bool:
    return any(k in (r.get("incomplete_reason") or "") for k in INFRA)


def cells(runs: list, j2: dict):
    """-> (cells {arm: {(problem, repeat): {d, m, e, d2, e2}}}, attempts, lost, duplicates) per arm."""
    out = {a: {} for a in ARMS}
    att, lost, dup = collections.Counter(), collections.Counter(), collections.Counter()
    for r in sorted(runs, key=lambda r: r.get("started_utc") or ""):
        arm = r.get("arm")
        if arm not in out or r.get("experiment") != ARM_EXPERIMENT[arm]:
            continue
        att[arm] += 1
        if is_infra(r):
            lost[arm] += 1
            continue
        key = (r["problem_id"], str(r.get("repeat")))
        if key in out[arm]:
            dup[arm] += 1
            continue
        d, m = r.get("diagnosis_judge1") == "True", r.get("mitigation") == "True"
        d2 = j2.get(r["run_id"])
        out[arm][key] = {"d": d, "m": m, "e": d and m, "d2": d2, "e2": (None if d2 is None else d2 and m)}
    return out, att, lost, dup


def paired(x: dict, y: dict, k: str):
    common = [c for c in set(x) & set(y) if x[c][k] is not None and y[c][k] is not None]
    b = sum(x[c][k] and not y[c][k] for c in common)
    c_ = sum(y[c][k] and not x[c][k] for c in common)
    return b, c_, len(common)


def report(runs: list, j2: dict) -> str:
    by, att, lost, dup = cells(runs, j2)
    pct = lambda a, n: f"{a}/{n} ({100 * a / n:.0f}%)" if n else "-"
    L = ["# Frozen 30, recomputed from the exported run records", "",
         "| Arm | cells | diagnosis J1 | diagnosis J2 | mitigation | E2E (J1) | E2E (J2) | kappa J1-J2 | lost / attempts | duplicates |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        c = by[arm]
        n = len(c)
        s = lambda k: sum(bool(v[k]) for v in c.values())
        pairs = [(v["d"], v["d2"]) for v in c.values() if v["d2"] is not None]
        n2 = len(pairs)
        _, kp = kappa(pairs)
        L.append(f"| {arm} | {n} | {pct(s('d'), n)} | {pct(sum(b for _, b in pairs), n2)} | {pct(s('m'), n)} | "
                 f"{pct(s('e'), n)} | {pct(sum(bool(v['e2']) for v in c.values() if v['e2'] is not None), n2)} | "
                 f"{kp:.2f} | {lost[arm]}/{att[arm]} | {dup[arm]} |")
    L += ["", "## Paired sign tests against F30 A (discordant cells, arm better : A better; two-sided exact)", "",
          "| Arm | mitigation | diagnosis J1 | E2E J1 | diagnosis J2 | E2E J2 |", "|---|---|---|---|---|---|"]
    for arm in ARMS:
        if arm == "F30 A" or not by[arm]:
            continue
        row = [arm]
        for k in ("m", "d", "e", "d2", "e2"):
            b, c_, n = paired(by[arm], by["F30 A"], k)
            row.append(f"{b}:{c_}, p = {sign_test(b, c_):.5f} (n = {n})")
        L.append("| " + " | ".join(row) + " |")
    pv = {}
    for name, arm, k in PRIMARY:
        if by[arm] and by["F30 A"]:
            b, c_, _ = paired(by["F30 A"], by[arm], k) if arm == "F30 B2 +FLAT" else paired(by[arm], by["F30 A"], k)
            pv[name] = sign_test(b, c_)
    L += ["", "## Holm over the four primary tests (alpha 0.05)", "", "| Test | p | Holm bar | significant |", "|---|---|---|---|"]
    for name, (p, bar, ok) in holm(pv).items():
        L.append(f"| {name} | {p:.5f} | {bar:.4f} | {'yes' if ok else 'no'} |")
    if by["F30 V5"]:
        L += ["", "## V5 against the other arms (secondary, uncorrected)", "", "| Comparison | mitigation | diagnosis J1 | E2E J1 |",
              "|---|---|---|---|"]
        for ref in ("F30 STRATUS", "F30 V3 A +T1v2", "F30 V3 A +CARDS +T1", "F30 B2 +FLAT"):
            row = [f"V5 vs {ref}"]
            for k in ("m", "d", "e"):
                b, c_, _ = paired(by["F30 V5"], by[ref], k)
                row.append(f"{b}:{c_}, p = {sign_test(b, c_):.5f}")
            L.append("| " + " | ".join(row) + " |")
    null = [r for r in runs if r.get("experiment") == CAL_EXPERIMENT and not is_infra(r)]
    if null:
        probs = sorted({r["problem_id"] for r in null})
        passing = sorted({r["problem_id"] for r in null if r.get("mitigation") == "True"})
        L += ["", "## Do-nothing calibration (plan 19)", "",
              f"`{CAL_EXPERIMENT}` (the first try ran the plain v2 agent and is excluded): {len(null)} valid null-agent runs on {len(probs)} problems; problems whose mitigation check passes with no "
              f"fix: {len(passing)}" + (f" ({', '.join(passing)})" if passing else "") + "."]
    return "\n".join(L) + "\n"


def load(runs_csv: str, judge2_csv: str):
    runs = list(csv.DictReader(open(runs_csv, encoding="utf-8")))
    j2 = {}
    if judge2_csv:
        for r in csv.DictReader(open(judge2_csv, encoding="utf-8")):
            if r.get("judge_model") == JUDGE2:
                j2[r["run_id"]] = r["success"] == "True"
    return runs, j2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="artifact-data/runs.csv")
    ap.add_argument("--judge2", default="artifact-data/second_judge.csv")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    text = report(*load(a.runs, a.judge2))
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
