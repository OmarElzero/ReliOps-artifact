"""Review follow-ups for the AGENT 2027 paper (v5, commit 7e358e5), read-only. Writes results/frozen30_review_followups.md.

  /root/ReliOps-Lab/.venv/bin/python sim/frozen_review_followups.py [--cache DIR] [--out ...]

Arms, infrastructure rule and the counted-cell rule (earliest valid run per (arm, problem, repeat)) as in
sim/frozen_analysis.py. Second judge: openai/gpt-5.4 verdicts from the Lab store `rejudges`. Pure Python (no numpy/scipy
on the Lab machine): exact sign test, exact Wilcoxon signed-rank (zeros dropped, mid-ranks for ties, exact null
distribution by enumeration of sign assignments), percentile bootstrap over problems. Every random draw uses seed
20261119. Firestore reads: the three frozen experiments (~800 docs), one projected scan of `runs` (~3,400 docs, six
fields) for the accounting, the rejudge store. --cache reuses earlier pulls.
"""
import argparse, collections, json, math, random, statistics, sys, time, warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, "/root/ReliOps-Lab/backend")
SEED = 20261119
ARMS = {"Final - Frozen 30 confirmation - first try": ["F30 A", "F30 B2 +FLAT", "F30 STRATUS"],
        "Final - Frozen 30 V3 - first try": ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2"],
        "Final - Frozen 30 V5 - first try": ["F30 V5"]}
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")
JUDGE2 = "openai/gpt-5.4"
NAMES = {"F30 A": "A", "F30 B2 +FLAT": "Base", "F30 STRATUS": "STRATUS", "F30 V3 A +CARDS +T1": "A+cards+gate",
         "F30 V3 A +T1v2": "A+driver gate", "F30 V5": "V5"}
CONFIGS = ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2", "F30 V5", "F30 B2 +FLAT", "F30 STRATUS"]
ALL = ["F30 A", "F30 B2 +FLAT", "F30 STRATUS", "F30 V3 A +CARDS +T1", "F30 V3 A +T1v2", "F30 V5"]


# ---- statistics (pure functions) -------------------------------------------------------------------------------------
def sign_test(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def wilcoxon(diffs):
    """Exact two-sided Wilcoxon signed-rank: zeros dropped (Wilcoxon's method), mid-ranks for ties; the null
    distribution of W+ is enumerated over all 2^n sign assignments by dynamic programming on doubled ranks.
    Returns (n nonzero, W+, W-, p)."""
    nz = [d for d in diffs if d != 0]
    n = len(nz)
    if n == 0:
        return 0, 0.0, 0.0, 1.0
    order = sorted(range(n), key=lambda i: abs(nz[i]))
    ranks2 = [0] * n                                   # doubled mid-ranks, integers
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(nz[order[j + 1]]) == abs(nz[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks2[order[k]] = (i + 1) + (j + 1)       # 2 * mean rank of positions i..j (1-based)
        i = j + 1
    wplus2 = sum(r for r, d in zip(ranks2, nz) if d > 0)
    total2 = sum(ranks2)
    dist = collections.Counter({0: 1})
    for r in ranks2:
        nxt = collections.Counter()
        for s, c in dist.items():
            nxt[s] += c
            nxt[s + r] += c
        dist = nxt
    tot = 2 ** n
    lo = sum(c for s, c in dist.items() if s <= wplus2) / tot
    hi = sum(c for s, c in dist.items() if s >= wplus2) / tot
    return n, wplus2 / 2, (total2 - wplus2) / 2, min(1.0, 2 * min(lo, hi))


def bootstrap_diff(pa, pb, reps=10000, seed=SEED):
    """95% percentile interval for the difference in pass rate (percentage points), resampling problems.
    pa, pb: per-problem pass counts (same problem order), each out of 3."""
    rng = random.Random(seed)
    n = len(pa)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        out.append(100 * (sum(pa[i] for i in idx) - sum(pb[i] for i in idx)) / (3 * n))
    out.sort()
    return out[int(0.025 * reps)], out[int(0.975 * reps) - 1]


# ---- data ------------------------------------------------------------------------------------------------------------
def client():
    import firebase_sync
    firebase_sync.try_auto_connect()
    return firebase_sync._client


def cached(cache, name, fn):
    p = Path(cache) / name if cache else None
    if p and p.is_file():
        return json.loads(p.read_text())
    data = fn()
    if p:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, default=str))
    return data


def infra(r):
    return any(k in (r.get("incomplete_reason") or "") for k in INFRA)


def arm_rows(data):
    out = collections.defaultdict(list)
    for exp, arms in ARMS.items():
        for r in data[exp]:
            if r.get("config_label") in arms:
                out[r["config_label"]].append(r)
    for v in out.values():
        v.sort(key=lambda r: r.get("timestamp_utc") or "")
    return out


def pick(rows, rule):
    """rule: earliest | latest | first_attempt (the cell's first attempt if it was valid, else no cell)."""
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["problem_id"], r.get("repeat_index"))].append(r)
    cells = {}
    for k, rs in by.items():
        valid = [r for r in rs if not infra(r)]
        if rule == "earliest" and valid:
            cells[k] = valid[0]
        elif rule == "latest" and valid:
            cells[k] = valid[-1]
        elif rule == "first_attempt" and not infra(rs[0]):
            cells[k] = rs[0]
    return cells


def metrics(r, rj):
    row = r.get("row") or {}
    d, m = row.get("Diagnosis.success") == "True", row.get("Mitigation.success") == "True"
    d2 = rj.get(r["run_id"])
    if d2 is None and not (r.get("diagnosis_text") or "").strip():
        d2 = False                                  # nothing submitted: no judge can pass it
    return {"d": d, "m": m, "e": d and m, "d2": d2, "e2": (d2 and m) if d2 is not None else None}


# ---- reports ---------------------------------------------------------------------------------------------------------
def problem_level(cx, ca, k, problems):
    """cx, ca: {(problem, repeat): metrics}. Per-problem passes for both sides over the cells both have."""
    px, pa = [], []
    for p in problems:
        common = [c for c in cx if c[0] == p and c in ca and cx[c][k] is not None and ca[c][k] is not None]
        px.append(sum(cx[c][k] for c in common))
        pa.append(sum(ca[c][k] for c in common))
    return px, pa


def compare(name, cx, ca, k, problems, label_a="A"):
    common = [c for c in cx if c in ca and cx[c][k] is not None and ca[c][k] is not None]
    b = sum(cx[c][k] and not ca[c][k] for c in common)
    c_ = sum(ca[c][k] and not cx[c][k] for c in common)
    px, pa = problem_level(cx, ca, k, problems)
    diffs = [x - y for x, y in zip(px, pa)]
    more, less, tie = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs), sum(d == 0 for d in diffs)
    n_nz, wp, wm, pw = wilcoxon(diffs)
    full = all(sum(1 for cc in common if cc[0] == p) == 3 for p in problems)
    lo, hi = bootstrap_diff(px, pa) if full else (float("nan"), float("nan"))
    rate = 100 * (sum(px) - sum(pa)) / (3 * len(problems)) if full else float("nan")
    disc = collections.Counter()
    for cc in common:
        if cx[cc][k] != ca[cc][k]:
            disc[cc[0]] += 1
    nd = sum(disc.values())
    top = disc.most_common()
    cum, top5 = 0, 0
    for i, (_, v) in enumerate(top):
        if i < 5:
            top5 += v
    return {"name": name, "cells": len(common), "b": b, "c": c_, "p_cell": sign_test(b, c_), "more": more, "less": less,
            "tie": tie, "p_sign": sign_test(more, less), "wil": (n_nz, wp, wm, pw), "ci": (lo, hi), "diff": rate,
            "px": px, "pa": pa, "disc": top, "n_disc": nd, "n_disc_problems": len(top), "top5": top5, "label_a": label_a}


def fmt_compare(res, problems, what):
    r = res
    out = [f"### {r['name']} vs {r['label_a']}, {what}", "",
           f"- Cells (both sides): {r['cells']}; discordant cells {r['name']} better : {r['label_a']} better = "
           f"**{r['b']}:{r['c']}**, exact sign test p = {r['p_cell']:.3f}.",
           f"- Problems where {r['name']} has more passes : {r['label_a']} has more : ties = **{r['more']}:{r['less']}:{r['tie']}**, "
           f"exact sign test over problems p = {r['p_sign']:.3f}.",
           f"- Wilcoxon signed-rank on the 30 per-problem differences: {r['wil'][0]} nonzero, W+ = {r['wil'][1]:g}, "
           f"W- = {r['wil'][2]:g}, exact two-sided p = {r['wil'][3]:.3f}.",
           f"- Difference in rate: {r['diff']:+.1f} points; 95% bootstrap interval over problems (10,000 resamples, seed "
           f"{SEED}): [{r['ci'][0]:+.1f}, {r['ci'][1]:+.1f}].",
           f"- Concentration: the {r['n_disc']} discordant cells lie in {r['n_disc_problems']} problems; the 5 problems with "
           f"most carry {r['top5']}. By problem (discordant cells): "
           + ", ".join(f"`{p}` {v}" for p, v in r["disc"]) + ".",
           "", "| Problem | " + r["name"] + " (of 3) | " + r["label_a"] + " (of 3) |", "|---|---|---|"]
    for p, x, y in zip(problems, r["px"], r["pa"]):
        if x != y:
            out.append(f"| `{p}` | {x} | {y} |")
    out.append(f"| (the other {sum(1 for x, y in zip(r['px'], r['pa']) if x == y)} problems: equal) | | |")
    return out + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="")
    ap.add_argument("--out", default="results/frozen30_review_followups.md")
    a = ap.parse_args()
    cl = client()
    import store
    from google.cloud.firestore_v1.base_query import FieldFilter
    data = cached(a.cache, "frozen_runs.json", lambda: {e: [d.to_dict() for d in cl.collection("runs").where(
        filter=FieldFilter("experiment", "==", e)).stream()] for e in ARMS})
    light = cached(a.cache, "all_runs_light.json", lambda: [d.to_dict() for d in cl.collection("runs").select(
        ["run_id", "experiment", "config_label", "timestamp_utc", "run_by", "model_id"]).stream()])
    rj = {r["run_id"]: r["success"] for r in store.read("rejudges")
          if r.get("judge_model_id") == JUDGE2 and isinstance(r.get("success"), bool)}
    rows = arm_rows(data)
    problems = sorted({r["problem_id"] for r in rows["F30 A"]})
    assert len(problems) == 30, len(problems)
    cells = {arm: pick(rows[arm], "earliest") for arm in ALL}
    met = {arm: {k: metrics(r, rj) for k, r in cells[arm].items()} for arm in ALL}

    out = ["# Frozen 30: review follow-ups for the AGENT 2027 paper (v5)", "",
           f"Written by `sim/frozen_review_followups.py` on {time.strftime('%d %b %Y %H:%M %Z')}, read-only. Arms, "
           "infrastructure rule and counted cell (earliest valid run per (arm, problem, repeat)) as in "
           f"`sim/frozen_analysis.py`. Seed {SEED} for every random draw. Names: Base = `F30 B2 +FLAT`, A = `F30 A`, "
           "A+cards+gate = `F30 V3 A +CARDS +T1`, A+driver gate = `F30 V3 A +T1v2`, V5 = `F30 V5`, STRATUS = `F30 STRATUS`. "
           "Tests are two-sided. Cell-level sign test = the paper's pre-registered test; the problem-level tests treat the "
           "30 problems as the units (three repeats of a problem are not independent).", "", "SUMMARY_PLACEHOLDER", ""]

    # 1
    out += ["## 1. Problem-level tests, mitigation, each configuration vs A", ""]
    summ = {}
    for arm in CONFIGS:
        res = compare(NAMES[arm], met[arm], met["F30 A"], "m", problems)
        summ[("m", arm)] = res
        out += fmt_compare(res, problems, "mitigation")
    res = compare("A", met["F30 A"], met["F30 B2 +FLAT"], "e", problems, label_a="Base")
    summ[("plan19", "A")] = res
    out += ["## 1b. Plan 19 primary: A vs Base, end-to-end (first judge)", ""] + fmt_compare(res, problems, "end-to-end (first judge)")

    # 2
    out += ["## 2. End-to-end under the second judge (GPT-5.4)", "",
            "E2E J2 = GPT-5.4 passes the diagnosis and the mitigation check passes. A counted run with no diagnosis text "
            "counts as a J2 diagnosis fail (it was never sent to the judge); a counted run with text but no GPT-5.4 verdict "
            "is left out (listed).", "",
            "| Configuration | E2E J2 | E2E (first judge) | cells without a J2 verdict |", "|---|---|---|---|"]
    for arm in ALL:
        m = met[arm]
        have = [v for v in m.values() if v["e2"] is not None]
        out.append(f"| {NAMES[arm]} | {sum(v['e2'] for v in have)}/{len(have)} ({100 * sum(v['e2'] for v in have) / len(have):.0f}%) | "
                   f"{sum(v['e'] for v in m.values())}/{len(m)} ({100 * sum(v['e'] for v in m.values()) / len(m):.0f}%) | "
                   f"{len(m) - len(have)} |")
    out.append("")
    for arm in CONFIGS:
        res = compare(NAMES[arm], met[arm], met["F30 A"], "e2", problems)
        summ[("e2", arm)] = res
        out += fmt_compare(res, problems, "E2E under GPT-5.4")
    tab = collections.Counter()
    for arm in ALL:
        for v in met[arm].values():
            if v["d2"] is not None:
                tab[(v["d"], v["d2"])] += 1
    n = sum(tab.values())
    agree = tab[(True, True)] + tab[(False, False)]
    pa_ = (tab[(True, True)] + tab[(True, False)]) / n
    pb_ = (tab[(True, True)] + tab[(False, True)]) / n
    pe = pa_ * pb_ + (1 - pa_) * (1 - pb_)
    out += ["### Pooled 2x2, first judge x GPT-5.4, counted frozen diagnoses (all six arms)", "",
            "| | GPT-5.4 pass | GPT-5.4 fail | total |", "|---|---|---|---|",
            f"| first judge pass | {tab[(True, True)]} | {tab[(True, False)]} | {tab[(True, True)] + tab[(True, False)]} |",
            f"| first judge fail | {tab[(False, True)]} | {tab[(False, False)]} | {tab[(False, True)] + tab[(False, False)]} |",
            f"| total | {tab[(True, True)] + tab[(False, True)]} | {tab[(True, False)] + tab[(False, False)]} | {n} |", "",
            f"Agreement {agree}/{n} ({100 * agree / n:.0f}%), Cohen's kappa {(agree / n - pe) / (1 - pe):.2f}. "
            f"Disagreements: first judge pass / GPT-5.4 fail {tab[(True, False)]}, the reverse {tab[(False, True)]}. "
            f"The {sum(1 for arm in ALL for r in cells[arm].values() if not (r.get('diagnosis_text') or '').strip())} counted "
            "cells with no diagnosis text are in the fail/fail cell: the first judge failed every one of them (checked), "
            "and they count as a GPT-5.4 fail (never sent).", ""]
    summ["2x2"] = (tab, n, agree)

    # 3
    out += ["## 3. Sensitivity to reruns (mitigation vs A, cell-level sign test; problem level where every problem has "
            "three cells on both sides)", "",
            "| Configuration | earliest valid (paper) | first attempt valid on both sides only | latest valid run per cell |",
            "|---|---|---|---|"]
    alt = {rule: {arm: {k: metrics(r, rj) for k, r in pick(rows[arm], rule).items()} for arm in ALL}
           for rule in ("first_attempt", "latest")}
    for arm in CONFIGS:
        row = [NAMES[arm]]
        for m_x, m_a in ((met[arm], met["F30 A"]), (alt["first_attempt"][arm], alt["first_attempt"]["F30 A"]),
                         (alt["latest"][arm], alt["latest"]["F30 A"])):
            r = compare(NAMES[arm], m_x, m_a, "m", problems)
            extra = f"; problems {r['more']}:{r['less']}:{r['tie']}, Wilcoxon p = {r['wil'][3]:.3f}" if r["cells"] == 90 else ""
            row.append(f"{r['b']}:{r['c']}, p = {r['p_cell']:.3f} (n = {r['cells']}){extra}")
        summ[("sens", arm)] = row
        out.append("| " + " | ".join(row) + " |")
    lost = {arm: 90 - len(alt["first_attempt"][arm]) for arm in ALL}
    out += ["", "Cells whose first attempt ended on infrastructure (dropped in the middle column): "
            + ", ".join(f"{NAMES[k]} {v}" for k, v in lost.items()) + ". Cells whose latest valid run differs from the "
            "earliest: " + ", ".join(f"{NAMES[arm]} {sum(1 for k in cells[arm] if pick(rows[arm], 'latest')[k]['run_id'] != cells[arm][k]['run_id'])}"
                                     for arm in ALL) + ".", ""]

    # 4
    out += ["## 4. Pairing: same machine and time gap between the two counted runs of a cell", "",
            "Machine = the Lab's `run_by` field (one name per machine; names are replaced by pseudonyms in the published copy). "
            "The records have no host name, so two machines of one person would look the same.", "",
            "| Configuration vs A | cells on the same machine | time gap, days: median (min to max) |", "|---|---|---|"]

    def ts(r):
        return datetime.fromisoformat((r.get("timestamp_utc") or "").replace("Z", "+00:00"))
    for arm in CONFIGS:
        same, gaps = 0, []
        for k, r in cells[arm].items():
            ra = cells["F30 A"].get(k)
            if not ra:
                continue
            same += (r.get("run_by") or "") == (ra.get("run_by") or "")
            gaps.append(abs((ts(r) - ts(ra)).total_seconds()) / 86400)
        summ[("pair", arm)] = (same, statistics.median(gaps))
        out.append(f"| {NAMES[arm]} | {same}/{len(gaps)} | {statistics.median(gaps):.1f} ({min(gaps):.2f} to {max(gaps):.1f}) |")
    out += ["", "Counted runs per machine: " + "; ".join(
        f"{NAMES[arm]}: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(r.get('run_by') for r in cells[arm].values()).most_common())
        for arm in ALL) + ".", ""]

    # 5
    total = cl.collection("runs").count().get()[0][0].value
    rounds = {"Dev - Ladder R1 - M1 - first try": "1: first ladder", "Dev - Ladder R2 - main - first try": "2: scaffolds",
              "Dev - R3 Routing + STRATUS - first try": "3: knowledge, STRATUS", "Dev - R4 REF EXCAP FLOW - first try": "4: knowledge variants"}
    calib = {"Dev - Ladder R2 - null agent - first try", "Calibration - null agent - frozen 30 - first try",
             "Calibration - null agent - frozen 30 - second try"}
    later = {"Dev - V3 r4.1 - first try", "Dev - V5 r5 - first try"}
    buckets, other = collections.Counter(), collections.Counter()
    for r in light:
        e = r.get("experiment")
        if e in rounds:
            buckets["development rounds 1-4"] += 1
        elif e in ARMS:
            buckets["frozen experiments (all attempts, every label)"] += 1
        elif e in calib:
            buckets["do-nothing calibration (dev and frozen)"] += 1
        elif e in later:
            buckets["later development queues (v3 r4.1, V5 r5)"] += 1
        else:
            buckets["everything else"] += 1
            other[e] += 1
    r4 = sorted(r.get("timestamp_utc") or "" for r in light if r.get("experiment") == "Dev - R4 REF EXCAP FLOW - first try")
    out += ["## 5. Run accounting", "",
            f"Firestore `runs`: {int(total):,} documents by aggregation count; {len(light):,} read by the projected scan on "
            f"{time.strftime('%d %b %Y %H:%M %Z')}. Buckets by the `experiment` field:", "",
            "| Bucket | runs | experiments |", "|---|---|---|"]
    exps = collections.defaultdict(collections.Counter)
    for r in light:
        e = r.get("experiment")
        bk = ("development rounds 1-4" if e in rounds else "frozen experiments (all attempts, every label)" if e in ARMS
              else "do-nothing calibration (dev and frozen)" if e in calib else
              "later development queues (v3 r4.1, V5 r5)" if e in later else "everything else")
        exps[bk][e] += 1
    for bk in ("development rounds 1-4", "frozen experiments (all attempts, every label)",
               "do-nothing calibration (dev and frozen)", "later development queues (v3 r4.1, V5 r5)", "everything else"):
        out.append(f"| {bk} | {buckets[bk]:,} | " + "; ".join(f"{e!r} {v}" if e else f"(no experiment name: {e!r}) {v}"
                                                              for e, v in exps[bk].most_common()) + " |")
    out += [f"| **total** | **{sum(buckets.values()):,}** | |", "",
            "How rounds 1-4 were matched: by exact experiment name, one experiment per round: "
            + "; ".join(f"round {v} = {k!r} ({sum(1 for r in light if r.get('experiment') == k)})" for k, v in rounds.items())
            + f". Sum {buckets['development rounds 1-4']:,}, not the paper's 1,807 (239 + 776 + 291 + 501). The paper's "
            "numbers come from Lab exports (union by run id, per the note at the top of paper.tex) taken while rounds were "
            f"still running: round 4 has {len(r4)} runs now, the paper's 501 is the export of 14 Nov "
            "(`results/r4-review-2026-11-14.md`: \"Lab export ..., 501 runs\"); in Firestore the 501st round-4 run by time "
            f"is at {r4[500] if len(r4) > 500 else '-'}, and {sum(1 for t in r4 if t >= '2026-11-14')} round-4 runs are from "
            "14-15 Nov. Rounds 1 and 2 differ by 5 and 1 runs (234 vs 239, 775 vs 776); the export files are not in the "
            "repository, so which runs those are cannot be checked here. Runs with no experiment name (118, mostly 24-26 "
            "Oct and 4-5 Nov) are left in \"everything else\".", ""]
    summ["acct"] = (total, buckets)

    # 6
    sm = collections.Counter(r.get("model_id") for r in rows["F30 STRATUS"])
    smc = collections.Counter(r.get("model_id") for r in cells["F30 STRATUS"].values())
    out += ["## 6. Model of the F30 STRATUS runs", "",
            f"`model_id` in the run records: all attempts {dict(sm)}; counted cells {dict(smc)}. This is the model the Lab "
            "passed to the STRATUS run (the same as every other arm).", ""]
    summ["stratus"] = smc

    s5 = summ[("m", "F30 V5")]
    p19 = summ[("plan19", "A")]
    summary = ("**Summary.** (1) Mitigation vs A, problem level (more : less : ties, sign p, Wilcoxon p, 95% CI in points): "
               + "; ".join(f"{NAMES[x]} {summ[('m', x)]['more']}:{summ[('m', x)]['less']}:{summ[('m', x)]['tie']}, "
                           f"p = {summ[('m', x)]['p_sign']:.3f}, W p = {summ[('m', x)]['wil'][3]:.3f}, "
                           f"[{summ[('m', x)]['ci'][0]:+.1f}, {summ[('m', x)]['ci'][1]:+.1f}]" for x in CONFIGS)
               + f". Plan 19 primary (A vs Base, E2E): cells {p19['b']}:{p19['c']} (p = {p19['p_cell']:.3f}), problems "
               f"{p19['more']}:{p19['less']}:{p19['tie']} (p = {p19['p_sign']:.3f}). (2) E2E under GPT-5.4 vs A, cells: "
               + "; ".join(f"{NAMES[x]} {summ[('e2', x)]['b']}:{summ[('e2', x)]['c']} (p = {summ[('e2', x)]['p_cell']:.3f})" for x in CONFIGS)
               + f". Pooled 2x2: first-judge-pass/GPT-fail {summ['2x2'][0][(True, False)]}, the reverse "
               f"{summ['2x2'][0][(False, True)]}, of {summ['2x2'][1]}. (3) V5 vs A mitigation: earliest {summ[('sens', 'F30 V5')][1]}; "
               f"first-attempt-valid {summ[('sens', 'F30 V5')][2]}; latest {summ[('sens', 'F30 V5')][3]}. (4) same machine as A: "
               + ", ".join(f"{NAMES[x]} {summ[('pair', x)][0]}/90" for x in CONFIGS)
               + f". (5) {int(summ['acct'][0]):,} runs; rounds 1-4 by experiment name "
               f"{summ['acct'][1]['development rounds 1-4']:,} (paper 1,807 from earlier exports). (6) STRATUS model: "
               + ", ".join(f"{k} ({v})" for k, v in summ["stratus"].items()) + ".")
    out[out.index("SUMMARY_PLACEHOLDER")] = summary
    Path(a.out).write_text("\n".join(out) + "\n")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
