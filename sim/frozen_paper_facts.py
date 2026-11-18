"""Read-only facts for the AGENT 2027 paper from the frozen 30 (cost per arm, the transactional-fix gate in numbers, one
example cell for a figure, total recorded runs, hand-label status). Writes results/frozen30_paper_facts.md.

Counted cell = earliest valid run per (arm, problem, repeat), same ARMS and INFRA rule as sim/frozen_analysis.py.
Fix-gate events come from each run's shared story (Firestore `stories`, rendered by scripts/replay_trace.py from the agent
transcript), where every driver event is a line `[feature NAME] event (stage S, k=v, ...)` and every agent step is a
`### Step N` block. Firestore reads: the three frozen experiments (one query each, ~800 docs), the stories of the three
transactional-fix arms (~270 docs), a few aggregation counts, the audit collections.

  /root/ReliOps-Lab/.venv/bin/python sim/frozen_paper_facts.py [--cache DIR] [--out results/frozen30_paper_facts.md]
--cache stores/reuses the Firestore pulls as JSON in DIR (no second read when re-run).
"""
import argparse, collections, json, re, statistics, sys, time, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, "/root/ReliOps-Lab/backend")

# Same as sim/frozen_analysis.py (copied: that module connects to Firestore on import).
ARMS = {"Final - Frozen 30 confirmation - first try": ["F30 A", "F30 B2 +FLAT", "F30 STRATUS"],
        "Final - Frozen 30 V3 - first try": ["F30 V3 A +CARDS +T1", "F30 V3 A +T1v2"],
        "Final - Frozen 30 V5 - first try": ["F30 V5"]}
INFRA = ("quota", "RateLimit", "Max retries", "network", "Cluster not ready", "node", "judge model check",
         "before the run started", "key rejected", "ACCOUNT_STATE_INVALID", "failed to deploy")
T1_ARMS = ["F30 V5", "F30 V3 A +T1v2", "F30 V3 A +CARDS +T1"]
ALL_ARMS = [a for v in ARMS.values() for a in v]

FEATURE = re.compile(r"\[feature (\w+)\] (\w+) \(stage (\w+)(?:, ([^)]*))?\)")
STEP = re.compile(r"^### Step (\d+) · `\+\s*([\d.]+)s` · stage `(\w+)`\n(?:(?!^### Step).)*?^\*\*Does:\*\* `([^`]*)` `([^\n]*)`( ⚠ WRITE[^\n]*| ✗[^\n]*)?$", re.M | re.S)
SUBMIT = re.compile(r"^### Step (\d+) · `\+\s*([\d.]+)s` · stage `(\w+)`\n(?:(?!^### Step).)*?^\*\*Submits:\*\*", re.M | re.S)


def client():
    import firebase_sync
    firebase_sync.try_auto_connect()
    return firebase_sync._client


def cached(cache, name, fn):
    if cache:
        p = Path(cache) / name
        if p.is_file():
            return json.loads(p.read_text())
    data = fn()
    if cache:
        Path(cache).mkdir(parents=True, exist_ok=True)
        (Path(cache) / name).write_text(json.dumps(data, default=str))
    return data


def pull_runs(cl):
    from google.cloud.firestore_v1.base_query import FieldFilter
    return {exp: [d.to_dict() for d in cl.collection("runs").where(filter=FieldFilter("experiment", "==", exp)).stream()]
            for exp in ARMS}


def is_infra(r):
    return any(k in (r.get("incomplete_reason") or "") for k in INFRA)


def counted(data):
    cells, dups, att = {}, collections.Counter(), collections.Counter()
    infra = collections.defaultdict(collections.Counter)
    other_incomplete = collections.Counter()
    for exp, arms in ARMS.items():
        for r in sorted(data[exp], key=lambda r: r.get("timestamp_utc") or ""):
            arm = r.get("config_label")
            if arm not in arms:
                continue
            att[arm] += 1
            if is_infra(r):
                reason = r.get("incomplete_reason") or ""
                key = next(k for k in INFRA if k in reason)
                infra[arm][f"{r.get('incomplete_kind') or '?'}: {key}"] += 1
                continue
            k = (arm, r["problem_id"], r.get("repeat_index"))
            if k in cells:
                dups[arm] += 1
                continue
            cells[k] = r
            if r.get("incomplete_reason"):
                other_incomplete[arm] += 1
    return cells, dups, att, infra, other_incomplete


def pct(xs, q):
    """Linear-interpolation percentile (same as numpy's default)."""
    xs = sorted(xs)
    if not xs:
        return float("nan")
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mit(r):
    return (r.get("row") or {}).get("Mitigation.success") == "True"


def kv(s):
    return dict(x.split("=", 1) for x in (s or "").split(", ") if "=" in x)


def timeline(story):
    """Ordered list of ('step', n, t, stage, action, args, write) and ('feature', name, event, stage, extras)."""
    items = []
    for m in STEP.finditer(story):
        items.append((m.start(), ("step", int(m.group(1)), float(m.group(2)), m.group(3), m.group(4), m.group(5),
                                   "WRITE" in (m.group(6) or ""))))
    for m in SUBMIT.finditer(story):
        items.append((m.start(), ("step", int(m.group(1)), float(m.group(2)), m.group(3), "submit", "", False)))
    for m in FEATURE.finditer(story):
        items.append((m.start(), ("feature", m.group(1), m.group(2), m.group(3), kv(m.group(4)))))
    return [x for _, x in sorted(items)]


def gate(story):
    tl = timeline(story)
    feats = [x for x in tl if x[0] == "feature"]
    restores = [x for x in feats if x[2] == "restored" and x[1] in ("T1_DRIVER", "TRANSACTIONAL_FIX")]
    verdicts = [x[4].get("verdict") for x in feats if x[1] == "T1_DRIVER" and x[2] == "verdict"]
    return {"restores": len(restores), "by_driver": sum(1 for x in restores if x[1] == "T1_DRIVER"),
            "by_model": sum(1 for x in restores if x[1] == "TRANSACTIONAL_FIX"), "verdicts": verdicts,
            "exhausted": any(x[1] == "TRANSACTIONAL_FIX" and x[2] == "rounds_exhausted" for x in feats),
            "mit_writes": sum(1 for x in tl if x[0] == "step" and x[3] == "mitigation" and x[6]),
            "steps": sum(1 for x in tl if x[0] == "step"), "tl": tl}


def thinks(story, n):
    m = re.search(rf"^### Step {n} [^\n]*\n\*\*Thinks:\*\*([^\n]*)", story, re.M)
    return m.group(1).strip() if m else ""


def example_lines(story, r):
    """Compact timeline copied from the story: routing, diagnosis submit, every mitigation write and submit, every driver
    verdict / restore / proof read. Commands are shortened, never reworded."""
    tl, out, seen_restore = timeline(story), [], False
    loaded = [x[4].get("category") for x in tl if x[0] == "feature" and x[1] == "ROUTING" and x[2] == "loaded"]
    wait = None
    for x in tl:
        if x[0] == "step" and x[3] == "diagnosis" and x[4] == "submit":
            out.append(f"| {x[1]} | +{x[2]:.0f}s | diagnosis submitted (procedures loaded: {', '.join(loaded)}) | | |")
        elif x[0] == "step" and x[3] == "mitigation" and (x[6] or x[4] == "submit"):
            what = "submit" if x[4] == "submit" else f"WRITE `{x[5][:260]}{'...' if len(x[5]) > 260 else ''}`"
            note = ""
            if x[6] and seen_restore:
                note = f" -- agent's stated reason: \"{thinks(story, x[1])[:200]}\""
            out.append(f"| {x[1]} | +{x[2]:.0f}s | {what}{note} | | |")
        elif x[0] == "feature" and x[1] == "ADAPTIVE_WAIT":
            wait = f"waited {x[4].get('seconds')} s, settled={x[4].get('settled')}"
        elif x[0] == "feature" and x[1] == "T1_DRIVER" and x[2] == "baseline":
            out.append(f"| | | driver baseline: {x[4].get('findings')} health findings in the namespace | | |")
        elif x[0] == "feature" and x[1] == "T1_DRIVER" and x[2] == "verdict":
            out.append(f"| | | driver check on the submit ({wait}) | **{x[4].get('verdict')}** (round {x[4].get('round')}) | |")
            wait = None
        elif x[0] == "feature" and x[2] == "restored":
            seen_restore = True
            out[-1] = out[-1][:-3] + f"| **yes**: {x[4].get('objects')} object(s) restored, submit refused, round {x[4].get('round')} |"
        elif x[0] == "feature" and x[1] == "TRANSACTIONAL_FIX" and x[2] == "proof_run":
            out.append(f"| | | gate asks for one proof read; agent runs `{x[4].get('action')}` ({wait}) | | |")
            wait = None
        elif x[0] == "feature" and x[1] == "TRANSACTIONAL_FIX" and x[2] == "proven":
            out.append(f"| | | submit accepted (`proven`) | | no |")
    row = r.get("row") or {}
    out.append(f"| | | **graded:** mitigation {row.get('Mitigation.success')}, diagnosis {row.get('Diagnosis.success')} | | |")
    return ["| Step | time | action (copied from the story, shortened) | driver check | restore |", "|---|---|---|---|---|"] + out


def fmt(x, d=0):
    return "n/a" if x != x else (f"{x:,.{d}f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="")
    ap.add_argument("--out", default="results/frozen30_paper_facts.md")
    a = ap.parse_args()
    cl = client()
    data = cached(a.cache, "frozen_runs.json", lambda: pull_runs(cl))
    cells, dups, att, infra, other_inc = counted(data)
    by = {arm: {(p, i): r for (x, p, i), r in cells.items() if x == arm} for arm in ALL_ARMS}
    out = ["# Frozen 30: facts for the AGENT 2027 paper", "",
           f"Written by `sim/frozen_paper_facts.py` on {time.strftime('%d %b %Y %H:%M %Z')}. Read-only. Counted cell = earliest "
           "valid run per (arm, problem, repeat); infrastructure rule and arms as in `sim/frozen_analysis.py`.", ""]

    # 1. cost
    out += ["## 1. Cost per arm (counted cells)", "",
            "Median and 90th percentile (linear interpolation). `num_llm_calls` and `total_tokens` are the agent's own model "
            "calls and tokens as the Lab records them (judge calls excluded); `duration_s` is the whole run (deploy, fault, "
            "both stages, judge, cleanup).", "",
            "| Arm | n | LLM calls median / p90 | total tokens median / p90 | duration s median / p90 |", "|---|---|---|---|---|"]
    for arm in ALL_ARMS:
        rs = list(by[arm].values())
        row = [arm, str(len(rs))]
        for f, d in (("num_llm_calls", 0), ("total_tokens", 0), ("duration_s", 0)):
            xs = [v for v in (num(r.get(f)) for r in rs) if v is not None]
            miss = len(rs) - len(xs)
            row.append(f"{fmt(statistics.median(xs) if xs else float('nan'), d)} / {fmt(pct(xs, 0.9), d)}"
                       + (f" (missing {miss})" if miss else ""))
        out.append("| " + " | ".join(row) + " |")
    out += ["", "STRATUS: none of its 90 counted run records has `num_llm_calls` or `total_tokens` (the Lab fills them from our "
            "agent's transcript (`runner.py` token totals), which STRATUS does not write), so only its duration is given here.",
            "", "Attempts per arm (every stored run of the arm in its frozen experiment):", "",
            "| Arm | attempts | lost to infrastructure | duplicates (later valid runs of a counted cell) | counted | of which incomplete, not infrastructure (counted as fail) |",
            "|---|---|---|---|---|---|"]
    for arm in ALL_ARMS:
        out.append(f"| {arm} | {att[arm]} | {sum(infra[arm].values())} | {dups[arm]} | {len(by[arm])} | {other_inc[arm]} |")
    out += ["", "Infrastructure losses by kind and matched INFRA keyword:", ""]
    for arm in ALL_ARMS:
        out.append(f"- {arm}: " + (", ".join(f"{k} {v}" for k, v in infra[arm].most_common()) or "none"))

    # 2. fix gate
    ids = [r["run_id"] for arm in T1_ARMS for r in by[arm].values()]

    def pull_stories():
        refs = [cl.collection("stories").document(x) for x in ids]
        got = {}
        for k in range(0, len(refs), 100):
            for d in cl.get_all(refs[k:k + 100]):
                if d.exists:
                    got[d.id] = (d.to_dict() or {}).get("text") or ""
        return got
    stories = cached(a.cache, "stories.json", pull_stories)
    out += ["", "## 2. The transactional-fix gate in numbers", "",
            "How the events appear (agent/react_v3_r5/driver.py; agent/react_v3_r4 writes the same names, minus `rebaseline`):",
            "- `T1_DRIVER baseline`: health findings of the namespace before any mitigation change.",
            "- `TRANSACTIONAL_FIX recorded`: an object is snapshotted before the agent's first write to it.",
            "- On the agent's first `submit` after a change (T1 v2 arms, `T1_DRIVER` on): the driver waits (`ADAPTIVE_WAIT waited` "
            "in V5), re-reads the findings and logs `T1_DRIVER verdict` = clear / partial / unknown / no_effect / worse. On "
            "worse or no_effect, with rounds left, it restores every recorded object (`T1_DRIVER restored`, round n), "
            "re-baselines (V5: `T1_DRIVER rebaseline`), refuses the submit and tells the agent to try a different fix "
            "(V5 adds the routed procedure's next untried fix family, FIX_FAMILIES).",
            "- Otherwise (and in A +CARDS +T1, which has no driver check) the gate asks the agent for one proof read "
            "(`TRANSACTIONAL_FIX proof_asked` / `proof_run`); the agent answers `not_fixed`, which restores "
            "(`TRANSACTIONAL_FIX restored`), or submits again (`proven`). `rounds_exhausted` = no restore rounds left "
            "(3 in V5, 2 in the v3 arms).", "",
            "Counted per cell from its shared story. \"Passed on the first fix\" = mitigation pass with no restore.", "",
            "| Arm | cells with story | >= 1 restore | of those, mitigation pass | median restore rounds (cells with >= 1) | restores by driver / by agent's not_fixed | rounds exhausted | mitigation pass with no restore | mitigation pass, all cells |",
            "|---|---|---|---|---|---|---|---|---|"]
    per_cell = {}
    for arm in T1_ARMS:
        rs = list(by[arm].values())
        g = {r["run_id"]: gate(stories[r["run_id"]]) for r in rs if stories.get(r["run_id"])}
        per_cell.update({k: (arm, v) for k, v in g.items()})
        withr = [r for r in rs if r["run_id"] in g and g[r["run_id"]]["restores"] > 0]
        nor = [r for r in rs if r["run_id"] in g and g[r["run_id"]]["restores"] == 0]
        rounds = [g[r["run_id"]]["restores"] for r in withr]
        out.append(f"| {arm} | {len(g)}/{len(rs)} | {len(withr)} | {sum(mit(r) for r in withr)} | "
                   f"{statistics.median(rounds) if rounds else 'n/a'} (max {max(rounds) if rounds else 0}) | "
                   f"{sum(g[r['run_id']]['by_driver'] for r in withr)} / {sum(g[r['run_id']]['by_model'] for r in withr)} | "
                   f"{sum(g[r['run_id']]['exhausted'] for r in rs if r['run_id'] in g)} | {sum(mit(r) for r in nor)} of {len(nor)} | "
                   f"{sum(mit(r) for r in rs)}/{len(rs)} |")
    out += ["", "First driver verdict per cell (T1 v2 arms; cells where the driver judged at least once):", ""]
    for arm in ("F30 V5", "F30 V3 A +T1v2"):
        c = collections.Counter(v["verdicts"][0] for k, (x, v) in per_cell.items() if x == arm and v["verdicts"])
        passed = collections.Counter(v["verdicts"][0] for k, (x, v) in per_cell.items()
                                     if x == arm and v["verdicts"] and mit(next(r for r in by[arm].values() if r["run_id"] == k)))
        out.append(f"- {arm}: " + ", ".join(f"{k} {n} (mitigation pass {passed[k]})" for k, n in c.most_common()))
    missing = [r["run_id"] for arm in T1_ARMS for r in by[arm].values() if not stories.get(r["run_id"])]
    if missing:
        out.append(f"\nCells with no shared story (left out of this section): {len(missing)} ({', '.join(missing)}).")

    # 3. example candidates (selection rule fixed before looking at problems)
    cands = []
    for r in by["F30 V5"].values():
        v = per_cell.get(r["run_id"], (None, None))[1]
        if not v or not mit(r) or v["by_driver"] < 1 or not v["verdicts"] or v["verdicts"][0] not in ("worse", "no_effect"):
            continue
        tl = v["tl"]
        first_restore = next(i for i, x in enumerate(tl) if x[0] == "feature" and x[1] == "T1_DRIVER" and x[2] == "restored")
        before = [x for x in tl[:first_restore] if x[0] == "step" and x[3] == "mitigation" and x[6]]
        after = [x for x in tl[first_restore:] if x[0] == "step" and x[3] == "mitigation" and x[6]]
        if before and after:
            cands.append((v["steps"], r["problem_id"], r["run_id"], len(before), len(after), v["verdicts"]))
    cands.sort()
    out += ["", "## 3. Example cell for a figure", "",
            "Selection rule (fixed before reading any candidate): counted F30 V5 cells whose first driver verdict was worse "
            "or no_effect, whose cluster was restored by the driver, with at least one mitigation write before and after "
            "the restore, and mitigation pass; take the one with the fewest agent steps (shortest story). Candidates "
            f"meeting the rule: {len(cands)}.", ""]
    for s, p, rid, nb, na, vs in cands:
        out.append(f"- {s} steps · `{p}` · `{rid}` · writes before/after restore {nb}/{na} · verdicts {vs}")
    runs_by_id = {r["run_id"]: r for r in by["F30 V5"].values()}
    for k, (s_, p, rid, nb, na, vs) in enumerate(cands[:2]):
        out += ["", f"### {'Pick by the rule' if k == 0 else 'Next by the rule'}: `{p}`, run `{rid}` ({s_} steps)", ""]
        out += example_lines(stories[rid], runs_by_id[rid])
    out += ["", "**Read before using the pick.** The restore message lists the routed procedure's fix families and asks "
            "for the next untried one (FIX_FAMILIES). In the pick, the last procedure loaded was `network` (families: 1 "
            "Service selector, port or targetPort; 2 pod labels and endpoints; 3 NetworkPolicy; ...). After the restore the "
            "agent says it uses \"family 2\" but describes a family of its own (remove the conflicting sidecar), which is "
            "not the listed family 2. The second fix is a different change from the first (remove the whole sidecar "
            "container instead of only its ports), and it passed; but it is not a clean example of a switch between "
            "listed families. In the next cell by the rule (`probes` procedure), the first fix is the probe port "
            "(listed family 1) and the second removes the probe (listed family 5, \"relax or remove the faulty probe\"; "
            "the agent names families 2 and 5). If the figure must show a switch between listed families, the second "
            "cell is the first one that does; that is a criterion of the request, not a choice by outcome (both "
            "passed). Restore messages themselves are not in the story (the story shows agent steps and driver events, "
            "not the driver's text to the model); their wording is `T1_DRIVER_FAIL_TEXT` + `FIX_FAMILIES_TEXT` in "
            "`agent/react_v3_r5/prompts.py`. In both cells the driver's first check came after the 180 s cap of ADAPTIVE_WAIT with "
            "the rollout not settled, so the first fix was judged before its rollout had finished; whether that first fix "
            "would have passed is not known."]

    # 4. total runs
    from google.cloud.firestore_v1.base_query import FieldFilter

    def counts():
        res = {"total": cl.collection("runs").count().get()[0][0].value,
               "marks": cl.collection("marks").count().get()[0][0].value}
        for v in ("experiment", "dev", "final"):                       # ReliOps-Lab dashboard.PURPOSES
            res[v] = cl.collection("marks").where(filter=FieldFilter("purpose", "==", v)).count().get()[0][0].value
        return res
    cnt = counts()
    out += ["", "## 4. Total recorded runs", "",
            f"Aggregation count of the Firestore `runs` collection on {time.strftime('%d %b %Y %H:%M %Z')}: **{int(cnt['total']):,}** "
            "(every run any team machine recorded through the Lab, including incomplete and infrastructure-failed attempts "
            "and the do-nothing calibration).", "",
            "By purpose: the purpose is not a field of the run; the Lab stores it as a `marks` record when a run is started "
            "with one (a run can be re-marked, so these are mark records, not distinct runs). Mark records by purpose: "
            + ", ".join(f"{v} {int(cnt[v]):,}" for v in ("experiment", "dev", "final"))
            + f" (all mark records {int(cnt['marks']):,}). Runs started without a purpose have no mark."]

    # 5. hand label
    plans = [d.to_dict() for d in cl.collection("audit_plans").stream()]
    nlab = cl.collection("audit_labels").count().get()[0][0].value
    frozen = [p for p in plans if "frozen" in (p.get("name") or "").lower() or "F30" in json.dumps(p.get("groups") or "")]
    out += ["", "## 5. Hand label (plan 19)", ""]
    if not frozen:
        out.append(f"No frozen hand-label audit exists yet. Firestore `audit_plans` holds {len(plans)} audits ("
                   + ", ".join(f"{p.get('name')} [{p.get('created_at', '')[:10]}]" for p in plans)
                   + f"), none on the frozen arms; `audit_labels` holds {int(nlab)} labels. The draw described in plan 19's "
                   "18 Nov addendum (group `F30 | pooled | 40`, seed 20261118, everyone labels every item) has not been made; "
                   "the fallback sheets of `sim/frozen_followups.py draw-labels` do not exist either. So: 0 items labeled by "
                   "either labeler, no score.")
    else:
        for p in frozen:
            out.append(f"- {p.get('name')}: labelers {p.get('labelers')}, items {len(p.get('items') or [])}")
    v5 = next(l for l in out if l.startswith("| F30 V5 | 90/"))
    out[3:3] = ["Summary: (1) cost table below; V5 is the most expensive arm (median 25 model calls, 344k tokens). "
                "(2) fix gate, F30 V5: {2} of 90 counted cells had at least one restore and {3} of those passed mitigation; median "
                "{4} restore rounds; {7} cells passed with no restore.".format(*[c.strip() for c in v5.split("|")][1:]) +
                f" (3) example: see section 3. (4) runs collection: {int(cnt['total']):,} on "
                f"{time.strftime('%d %b %Y')}. (5) hand label: not drawn yet.", ""]
    text = "\n".join(out) + "\n"
    Path(a.out).write_text(text)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
