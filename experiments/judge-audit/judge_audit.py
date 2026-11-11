#!/usr/bin/env python3
"""Judge audit: draw a blind, stratified sample of judged diagnoses, split it across labelers, score the labels.

  python3 judge_audit.py draw  --r3 r3_runs.csv --r2 r2_runs.csv --labelers A,B,C --out out/
  python3 judge_audit.py score --key out/key.csv --sheets out/filled_A.csv out/filled_B.csv out/filled_C.csv

Inputs are the Lab's runs.csv exports (columns run_id, problem_id, config_label, judge_model_id, diagnosis_pass,
mitigation_pass, e2e_pass, diagnosis_text). The labeler sheets never contain the configuration, the judge verdict
or the judge reasoning; those stay in key.csv, which only the person who scores the audit opens.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

CARDS = Path(__file__).resolve().parents[1] / "problem-cards"
SHEET_COLS = ["item_id", "problem_id", "expected_from_card", "diagnosis_text", "d1_localization", "d2_characterization",
              "d3_scope", "overall_correct", "confidence", "reason", "labeler"]
KEY_COLS = ["item_id", "run_id", "stratum", "config_label", "problem_id", "judge_model_id", "judge_diagnosis_pass",
            "mitigation_pass", "e2e_pass", "anchor", "labelers"]
FLOOR_RE = re.compile(r"(dumb|do-?nothing|floor)", re.I)


def truthy(v) -> bool | None:
    s = str(v).strip().lower()
    return True if s == "true" else False if s == "false" else None


def read_csv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def eligible(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if (r.get("diagnosis_text") or "").strip() and truthy(r.get("diagnosis_pass")) is not None \
                and (r.get("judge_model_id") or "").strip() and not FLOOR_RE.search(r.get("config_label") or ""):
            out.append(r)
    return sorted(out, key=lambda r: r["run_id"])


def card_expected(problem_id: str) -> str:
    p = CARDS / f"{problem_id}.md"
    if not p.is_file():
        return "(no card found: ask the coordinator)"
    m = re.search(r"^## 4\..*?$(.*?)(?=^## |\Z)", p.read_text(encoding="utf-8"), re.M | re.S)
    return m.group(1).strip() if m else "(card has no section 4)"


def pick(rows, k, rng, cap, used):
    """k runs from rows at random, at most `cap` per problem across the whole stratum (`used` counts them)."""
    pool = rows[:]
    rng.shuffle(pool)
    chosen = []
    for relax in (False, True):
        for r in pool:
            if len(chosen) == k:
                break
            if r in chosen or (not relax and used[r["problem_id"]] >= cap):
                continue
            chosen.append(r)
            used[r["problem_id"]] += 1
    return chosen


def draw_stratum(rows, n, rng, cap):
    """n runs, half judged-pass and half judged-fail, so a lenient or a harsh judge cannot hide."""
    used = defaultdict(int)
    passed = [r for r in rows if truthy(r["diagnosis_pass"])]
    failed = [r for r in rows if not truthy(r["diagnosis_pass"])]
    kp, kf = n // 2, n - n // 2
    chosen = pick(passed, kp, rng, cap, used) + pick(failed, kf, rng, cap, used)
    if len(chosen) < n:  # one side too small: fill from the other and say so
        rest = [r for r in rows if r not in chosen]
        chosen += pick(rest, n - len(chosen), rng, cap, used)
    return chosen


def cmd_draw(a):
    labelers = [x.strip() for x in a.labelers.split(",") if x.strip()]
    rng = random.Random(a.seed)
    strata: dict[str, list[dict]] = {}
    r3 = eligible(read_csv(a.r3))
    configs = sorted({r["config_label"] for r in r3})
    if a.configs:
        configs = [c.strip() for c in a.configs.split(",")]
    elif len(configs) > 6:
        sys.exit(f"{len(configs)} configurations in {a.r3}; pass --configs with the ones to audit: {configs}")
    for c in configs:
        strata["R3 " + c] = [r for r in r3 if r["config_label"] == c]
    strata["R2 pooled"] = eligible(read_csv(a.r2)) if a.r2 else []
    key, notes = [], []
    for name, rows in strata.items():
        n = a.per_stratum if name != "R2 pooled" else a.r2_n
        if not rows or n == 0:
            notes.append(f"{name}: no eligible runs, skipped")
            continue
        got = draw_stratum(rows, min(n, len(rows)), rng, a.max_per_problem)
        npass = sum(1 for r in got if truthy(r["diagnosis_pass"]))
        notes.append(f"{name}: {len(got)} drawn from {len(rows)} eligible ({npass} judged pass, {len(got) - npass} judged fail)")
        rng.shuffle(got)
        for i, r in enumerate(got):
            r["_stratum"], r["_anchor"] = name, i < a.anchors_per_stratum
        key += got
    ids = list(range(1, len(key) + 1))
    rng.shuffle(ids)
    for r, i in zip(key, ids):
        r["_item"] = f"I{i:03d}"
    # assignment: anchors to everyone, the rest round-robin per stratum so each labeler sees every stratum
    assign = defaultdict(list)
    rr = itertools.cycle(range(len(labelers)))
    for name in strata:
        for r in [x for x in key if x["_stratum"] == name]:
            who = labelers if r["_anchor"] else [labelers[next(rr)]]
            r["_who"] = who
            for w in who:
                assign[w].append(r)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "key.csv", KEY_COLS, [{
        "item_id": r["_item"], "run_id": r["run_id"], "stratum": r["_stratum"], "config_label": r["config_label"],
        "problem_id": r["problem_id"], "judge_model_id": r["judge_model_id"], "judge_diagnosis_pass": r["diagnosis_pass"],
        "mitigation_pass": r.get("mitigation_pass", ""), "e2e_pass": r.get("e2e_pass", ""),
        "anchor": int(r["_anchor"]), "labelers": "|".join(r["_who"])} for r in sorted(key, key=lambda x: x["_item"])])
    for w in labelers:
        rows = assign[w][:]
        random.Random(f"{a.seed}-{w}").shuffle(rows)
        write_csv(out / f"sheet_{w}.csv", SHEET_COLS, [{
            "item_id": r["_item"], "problem_id": r["problem_id"], "expected_from_card": card_expected(r["problem_id"]),
            "diagnosis_text": r["diagnosis_text"], "labeler": w} for r in rows])
    (out / "DRAW.txt").write_text(
        f"seed {a.seed}\nr3 export sha256[:12] {sha(a.r3)}\nr2 export sha256[:12] {sha(a.r2) if a.r2 else '-'}\n"
        f"labelers {', '.join(labelers)}\nanchors per stratum {a.anchors_per_stratum}, runs per stratum {a.per_stratum}"
        f" (R2 pooled {a.r2_n}), at most {a.max_per_problem} per problem per stratum\n" + "\n".join(notes) + "\n")
    print("\n".join(notes))
    print(f"{len(key)} distinct runs; labels to give: " + ", ".join(f"{w} {len(assign[w])}" for w in labelers))
    print(f"Wrote {out}/key.csv (coordinator only) and one sheet per labeler.")


# ---- scoring ----------------------------------------------------------------------------------
def wilson(k, n, z=1.96):
    if n == 0:
        return (math.nan, math.nan)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def kappa(a: list[bool], b: list[bool]):
    n = len(a)
    if n == 0:
        return math.nan
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return math.nan if pe == 1 else (po - pe) / (1 - pe)


def yn(v):
    s = str(v).strip().lower()
    return True if s in ("y", "yes", "1", "true") else False if s in ("n", "no", "0", "false") else None


def cmd_score(a):
    key = {r["item_id"]: r for r in read_csv(a.key)}
    labels: dict[str, dict[str, bool]] = defaultdict(dict)  # item -> labeler -> overall_correct
    problems = []
    for s in a.sheets:
        for r in read_csv(s):
            v = yn(r.get("overall_correct"))
            who = (r.get("labeler") or Path(s).stem).strip()
            if r["item_id"] not in key:
                problems.append(f"{s}: unknown item {r['item_id']}")
            elif v is None:
                problems.append(f"{s}: {r['item_id']} has no Y/N in overall_correct")
            else:
                labels[r["item_id"]][who] = v
    for p in problems:
        print("WARNING", p)
    anchors = [i for i, k in key.items() if k["anchor"] == "1"]
    names = sorted({w for d in labels.values() for w in d})
    print(f"\nLabels read for {len(labels)} of {len(key)} items; labelers: {', '.join(names)}")
    print("\nLabeler reliability (anchors, overall_correct):")
    for x, y in itertools.combinations(names, 2):
        ids = [i for i in anchors if x in labels[i] and y in labels[i]]
        if ids:
            A, B = [labels[i][x] for i in ids], [labels[i][y] for i in ids]
            print(f"  {x} vs {y}: n={len(ids)}, agree {sum(p == q for p, q in zip(A, B))}, kappa {kappa(A, B):.2f}")
    human = {}
    for i, d in labels.items():
        votes = list(d.values())
        if len(votes) >= 2 and len(votes) % 2 == 0 and sum(votes) * 2 == len(votes):
            print(f"  WARNING {i}: tied labels, left out"); continue
        human[i] = sum(votes) * 2 > len(votes)
    print("\nJudge against human consensus (the sample is balanced on the judge's verdict, so read rates below as such):")
    groups = defaultdict(list)
    for i, h in human.items():
        k = key[i]
        groups["ALL"].append((truthy(k["judge_diagnosis_pass"]), h))
        groups[k["stratum"]].append((truthy(k["judge_diagnosis_pass"]), h))
    for g, pairs in groups.items():
        J, H = [p[0] for p in pairs], [p[1] for p in pairs]
        n, ag = len(pairs), sum(p == q for p, q in pairs)
        fp = sum(1 for p, q in pairs if p and not q)
        fn = sum(1 for p, q in pairs if not p and q)
        jp, jf = sum(J), n - sum(J)
        lo, hi = wilson(ag, n)
        print(f"  {g}: n={n}, agree {ag} ({ag / n:.0%}, 95% CI {lo:.0%}-{hi:.0%}), kappa {kappa(J, H):.2f}, "
              f"judge-pass but human-wrong {fp}/{jp}, judge-fail but human-right {fn}/{jf}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    d = s.add_parser("draw")
    d.add_argument("--r3", required=True); d.add_argument("--r2")
    d.add_argument("--configs", help="comma-separated config_label values to treat as R3 strata (default: all in the file)")
    d.add_argument("--labelers", default="L1,L2,L3"); d.add_argument("--out", default="out")
    d.add_argument("--seed", type=int, default=20261112)
    d.add_argument("--per-stratum", type=int, default=12); d.add_argument("--r2-n", type=int, default=12)
    d.add_argument("--anchors-per-stratum", type=int, default=3); d.add_argument("--max-per-problem", type=int, default=2)
    sc = s.add_parser("score")
    sc.add_argument("--key", required=True); sc.add_argument("--sheets", nargs="+", required=True)
    a = p.parse_args()
    {"draw": cmd_draw, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
