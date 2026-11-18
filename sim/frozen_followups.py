"""Frozen-30 follow-ups after all arms are complete (plans 19, 25, 27).

  calibration   plan 19: "mitigation is reported only on problems whose check fails for the do-nothing agent". Reads the
                null-agent calibration runs, lists the problems whose mitigation check passes with no fix, and recomputes
                every mitigation comparison without them. Writes results/frozen30_null_calibration.md.
  draw-labels   plan 19: hand label, blind to both judges, of the diagnoses the two judges dispute (all of them, or a
                random 40 if there are more), each labeled by two team members separately. Writes one blind sheet per
                labeler (results/hand-label-frozen/sheet_<name>.csv) and the key (results/raw/hand-label-frozen/key.json,
                git-ignored until scoring).
  score-labels  reads the filled sheets and the key; writes results/frozen30_hand_label.md.

Run with the Lab's venv on a machine whose Lab reaches Firestore:
  /root/ReliOps-Lab/.venv/bin/python sim/frozen_followups.py calibration
  /root/ReliOps-Lab/.venv/bin/python sim/frozen_followups.py draw-labels --labelers A,B
  /root/ReliOps-Lab/.venv/bin/python sim/frozen_followups.py score-labels
The pure functions (cells, calibration_report, draw, score) take plain lists and are unit-tested in sim/test_frozen_followups.py.
"""
import argparse, collections, csv, json, math, os, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Same arms, infrastructure rule, second judge and tests as sim/frozen_analysis.py (copied, not imported: that module
# connects to Firestore on import).
ARMS = {"Final - Frozen 30 confirmation - first try": ["F30 A", "F30 B2 +FLAT", "F30 STRATUS"],
        "Final - Frozen 30 V3 - first try": ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2"],
        "Final - Frozen 30 V5 - first try": ["F30 V5"]}
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")
JUDGE2 = "openai/gpt-5.4"


def sign_test(b, c):
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
    return agree, (agree - pe) / (1 - pe) if pe < 1 else float("nan")

CAL_PREFIX = "Calibration - null agent - frozen 30"
SEED = 20261118                      # fixed 18 Nov 2026, before the draw; recorded in plan 19
SAMPLE = 40
SHEET_DIR = ROOT / "results" / "hand-label-frozen"
KEY = ROOT / "results" / "raw" / "hand-label-frozen" / "key.json"
ANSWERS = ROOT / "experiments" / "frozen30-reference-answers.json"
SHEET_COLS = ["item", "problem_id", "reference_answer", "diagnosis", "component_right", "cause_right", "correct", "note"]
PRIMARY = {  # every primary test the frozen set has answered (plans 19, 25 x2, 27)
    "plan 19: A vs base, E2E": ("F30 B2 +FLAT", "e"),
    "plan 25: A+cards+T1 vs A, mitigation": ("F30 V3 A +CARDS +T1", "m"),
    "plan 25: A+T1v2 vs A, mitigation": ("F30 V3 A +T1v2", "m"),
    "plan 27: V5 vs A, mitigation": ("F30 V5", "m"),
}


def valid(r: dict) -> bool:
    return not any(k in (r.get("incomplete_reason") or "") for k in INFRA)   # same rule as frozen_analysis.py


def cells(rows: list[dict], rejudges: dict) -> dict:
    """{(arm, problem, repeat): cell}; the earliest valid run of each cell counts (same rule as frozen_analysis.py)."""
    arms = {a for v in ARMS.values() for a in v}
    out = {}
    for r in sorted(rows, key=lambda r: r.get("timestamp_utc") or ""):
        arm = r.get("config_label")
        if arm not in arms or not valid(r):
            continue
        key = (arm, r["problem_id"], r.get("repeat_index"))
        if key in out:
            continue
        row = r.get("row") or {}
        d, m = row.get("Diagnosis.success") == "True", row.get("Mitigation.success") == "True"
        out[key] = {"d": d, "m": m, "e": d and m, "d2": rejudges.get(r["run_id"]), "run_id": r["run_id"],
                    "text": (r.get("diagnosis_text") or "").strip()}
    return out


def _by_arm(c: dict) -> dict:
    by = collections.defaultdict(dict)
    for (arm, p, i), v in c.items():
        by[arm][(p, i)] = v
    return by


def _test(by, arm, ref, k, keep=None):
    common = [x for x in set(by[arm]) & set(by[ref]) if keep is None or x[0] in keep]
    b = sum(by[arm][x][k] and not by[ref][x][k] for x in common)
    c = sum(by[ref][x][k] and not by[arm][x][k] for x in common)
    return b, c, sign_test(b, c), len(common)


def holm(ps: dict) -> dict:
    order = sorted(ps, key=ps.get)
    out, stop = {}, False
    for i, name in enumerate(order):
        thr = 0.05 / (len(order) - i)
        stop = stop or ps[name] > thr
        out[name] = (thr, not stop)
    return out


def calibration_report(null_rows: list[dict], c: dict, problems: list[str]) -> str:
    runs = collections.defaultdict(list)
    for r in null_rows:
        if valid(r):
            runs[r["problem_id"]].append((r.get("row") or {}).get("Mitigation.success") == "True")
    passing = sorted(p for p in problems if any(runs.get(p, [])))
    missing = sorted(p for p in problems if not runs.get(p))
    keep = {p for p in problems if p not in passing}
    by = _by_arm(c)
    arms = [a for v in ARMS.values() for a in v if by.get(a)]
    L = ["# Frozen 30: do-nothing calibration (plan 19)", "",
         f"Null-agent runs: {sum(len(v) for v in runs.values())} valid, on {len(runs)} of {len(problems)} problems.",
         f"Problems whose mitigation check passes with no fix ({len(passing)}): " + (", ".join(passing) or "none") + ".",
         f"Problems with no valid null run ({len(missing)}): " + (", ".join(missing) or "none") +
         (" (not calibrated; kept, and stated)." if missing else "."), "",
         f"## Mitigation on the {len(keep)} calibrated problems (cells: earliest valid run)", "",
         "| Arm | mitigation, all 30 | mitigation, calibrated | vs F30 A, all 30 | vs F30 A, calibrated |", "|---|---|---|---|---|"]
    for arm in arms:
        cs = by[arm]
        allm = sum(v["m"] for v in cs.values())
        kc = {x: v for x, v in cs.items() if x[0] in keep}
        km = sum(v["m"] for v in kc.values())
        if arm == "F30 A":
            t1 = t2 = "--"
        else:
            b, cc, p, _ = _test(by, arm, "F30 A", "m"); t1 = f"{b}:{cc}, p = {p:.4f}"
            b, cc, p, _ = _test(by, arm, "F30 A", "m", keep); t2 = f"{b}:{cc}, p = {p:.4f}"
        L.append(f"| {arm} | {allm}/{len(cs)} ({100*allm/max(1,len(cs)):.0f}%) | {km}/{len(kc)} ({100*km/max(1,len(kc)):.0f}%) | {t1} | {t2} |")
    for label, keepset in (("all 30 problems", None), ("calibrated problems only", keep)):
        ps = {}
        for name, (arm, k) in PRIMARY.items():
            if by.get(arm) and by.get("F30 A"):
                ps[name] = _test(by, arm, "F30 A", k, keepset if k == "m" else None)[2]
        h = holm(ps)
        L += ["", f"## The four primary tests as one family (Holm), {label}", "", "| Test | p | Holm threshold | significant |",
              "|---|---|---|---|"]
        L += [f"| {n} | {ps[n]:.5f} | {h[n][0]:.4f} | {'yes' if h[n][1] else 'no'} |" for n in sorted(ps, key=ps.get)]
    L += ["", "The plan 19 E2E test is not recalibrated (it needs the diagnosis too). Each plan's own verdict is in "
          "results/frozen30_analysis.md; the family view is not pre-registered and is reported as a stricter reading."]
    return "\n".join(L) + "\n"


def draw(c: dict, n: int = SAMPLE, seed: int = SEED) -> list[dict]:
    disputed = sorted(((k, v) for k, v in c.items() if v["d2"] is not None and v["text"] and v["d"] != v["d2"]),
                      key=lambda kv: kv[1]["run_id"])
    rng = random.Random(seed)
    chosen = disputed if len(disputed) <= n else rng.sample(disputed, n)
    items = []
    for i, ((arm, p, rep), v) in enumerate(sorted(chosen, key=lambda kv: kv[1]["run_id"]), 1):
        items.append({"item": f"F{i:02d}", "run_id": v["run_id"], "arm": arm, "problem_id": p, "repeat": rep,
                      "judge1": v["d"], "judge2": v["d2"], "text": v["text"]})
    return items, len(disputed)


def write_sheets(items, labelers, answers, seed=SEED):
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    for j, name in enumerate(labelers):
        order = items[:]
        random.Random(seed + 1 + j).shuffle(order)          # a different order per labeler
        with open(SHEET_DIR / f"sheet_{name}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_COLS)
            w.writeheader()
            for it in order:
                w.writerow({"item": it["item"], "problem_id": it["problem_id"],
                            "reference_answer": answers.get(it["problem_id"], "(missing: ask the coordinator)"),
                            "diagnosis": it["text"], "component_right": "", "cause_right": "", "correct": "", "note": ""})


def _yn(s):
    s = (s or "").strip().lower()
    return True if s in ("y", "yes", "1", "true") else False if s in ("n", "no", "0", "false") else None


def score(key: list[dict], sheets: dict) -> str:
    lab = {name: {r["item"]: _yn(r.get("correct")) for r in rows} for name, rows in sheets.items()}
    names = list(lab)
    L = ["# Frozen 30: hand label of disputed diagnoses (plan 19)", "",
         f"{len(key)} items, each a diagnosis the first judge and gpt-5.4 disagree on; labelers: {', '.join(names)}; "
         "blind to both verdicts, the arm and each other.", ""]
    for n in names:
        got = [it for it in key if lab[n].get(it["item"]) is not None]
        j1 = sum(lab[n][it["item"]] == it["judge1"] for it in got)
        L.append(f"- {n}: {len(got)} labeled; sides with the first judge on {j1}, with gpt-5.4 on {len(got) - j1}.")
    if len(names) >= 2:
        a, b = names[:2]
        both = [it for it in key if lab[a].get(it["item"]) is not None and lab[b].get(it["item"]) is not None]
        ag, kp = kappa([(lab[a][it["item"]], lab[b][it["item"]]) for it in both])
        cons = [it for it in both if lab[a][it["item"]] == lab[b][it["item"]]]
        j1 = sum(lab[a][it["item"]] == it["judge1"] for it in cons)
        L += ["", f"Labelers agree on {len(cons)} of {len(both)} ({100*ag:.0f}%, kappa {kp:.2f}).",
              f"Where they agree, the person sides with the first judge on {j1} and with gpt-5.4 on {len(cons) - j1}."]
        per = collections.Counter((it["judge1"], lab[a][it["item"]] == it["judge1"]) for it in cons)
        L += [f"First judge passed, gpt-5.4 failed: person says correct {per[(True, True)]}, wrong {per[(True, False)]}.",
              f"First judge failed, gpt-5.4 passed: person says wrong {per[(False, True)]}, correct {per[(False, False)]}."]
    return "\n".join(L) + "\n"


# ---- Firestore I/O (only on a machine with the Lab) -------------------------------------------------------------------
def _load():
    sys.path.insert(0, "/root/ReliOps-Lab/backend")
    import firebase_sync, store  # noqa: E402
    from google.cloud.firestore_v1.base_query import FieldFilter  # noqa: E402
    firebase_sync.try_auto_connect()
    cl = firebase_sync._client
    rj = {r["run_id"]: r["success"] for r in store.read("rejudges")
          if r.get("judge_model_id") == JUDGE2 and isinstance(r.get("success"), bool)}
    rows = []
    for exp in ARMS:
        rows += [d.to_dict() for d in cl.collection("runs").where(filter=FieldFilter("experiment", "==", exp)).stream()]
    return cl, FieldFilter, rows, rj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calibration", "draw-labels", "score-labels"])
    ap.add_argument("--labelers", default="")
    a = ap.parse_args()
    problems = [r["problem_id"] for r in csv.DictReader(open(ROOT / "experiments" / "first-30.csv", encoding="utf-8"))]
    if a.cmd == "score-labels":
        key = json.loads(KEY.read_text())["items"]
        sheets = {p.stem[len("sheet_"):]: list(csv.DictReader(open(p, encoding="utf-8-sig"))) for p in sorted(SHEET_DIR.glob("sheet_*.csv"))}
        text = score(key, sheets)
        (ROOT / "results" / "frozen30_hand_label.md").write_text(text)
        print(text)
        return
    cl, FF, rows, rj = _load()
    c = cells(rows, rj)
    if a.cmd == "calibration":
        null = [d.to_dict() for d in cl.collection("runs").where(filter=FF("experiment", ">=", CAL_PREFIX))
                .where(filter=FF("experiment", "<", CAL_PREFIX + "")).stream()]
        null = [r for r in null if r.get("problem_id") in problems]
        text = calibration_report(null, c, problems)
        (ROOT / "results" / "frozen30_null_calibration.md").write_text(text)
        print(text)
    else:
        names = [x.strip() for x in a.labelers.split(",") if x.strip()]
        if len(names) < 2:
            sys.exit("--labelers needs two names (plan 19: two team members, separately)")
        items, n_disputed = draw(c)
        answers = json.loads(ANSWERS.read_text())["answers"]
        write_sheets(items, names, answers)
        KEY.parent.mkdir(parents=True, exist_ok=True)
        KEY.write_text(json.dumps({"seed": SEED, "disputed": n_disputed, "labelers": names, "items": items}, indent=1))
        # Only counts are printed: the sheets are blind, and the key (verdicts, arms) is for the coordinator after labeling.
        print(f"{n_disputed} disputed diagnoses; {len(items)} drawn (seed {SEED}); sheets in {SHEET_DIR}; key in {KEY}")
        print("problems in the sample:", len({it['problem_id'] for it in items}))


if __name__ == "__main__":
    main()
