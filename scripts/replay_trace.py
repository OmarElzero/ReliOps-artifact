#!/usr/bin/env python3
"""Turn a react-v1 run into a readable step-by-step story.

    python3 scripts/replay_trace.py TRANSCRIPT.jsonl [--cluster cluster.jsonl] [--out story.md]

Inputs
  TRANSCRIPT.jsonl   react_v1_transcript.jsonl from the run's logs dir (written by agent/react_v1/driver.py).
                     Run the agent with REACT_V1_LOG_OBS=on to also get what each command returned;
                     without it the story shows thoughts + actions but not the observations.
  --cluster FILE     optional output of scripts/cluster_recorder.py for the same run; its pod / event /
                     object changes are interleaved by timestamp, so you see the system break, the agent
                     react, and the fix land.

Output: Markdown with a header (problem, model, action space, totals), then one timeline mixing
`[cluster]` lines (what happened to the system) and `Step N` blocks (what the agent thought, did and saw).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
OBS_LINES = 80  # max observation lines shown per step (the agent sees up to 8,000 characters of each)


def load(path: str | None) -> list[dict]:
    if not path:
        return []
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def t(rec: dict) -> datetime:
    return datetime.fromisoformat(rec["ts"])


def split_thought(content: str) -> tuple[str, str]:
    """(free-text reasoning before the action, the raw action json) from a model reply."""
    m = JSON_BLOCK_RE.search(content or "")
    if not m:
        return (content or "").strip(), ""
    return (content[: m.start()]).strip(), m.group(1).strip()


MUTATING_VERBS = {"apply", "create", "delete", "patch", "replace", "scale", "set", "label", "annotate", "edit", "cordon",
                  "uncordon", "drain", "taint", "expose", "autoscale", "run", "exec", "cp", "rollout-restart",
                  "rollout-undo", "rollout-pause", "rollout-resume"}
_FLAGS_WITH_VALUE = {"-n", "--namespace", "-c", "--container", "--context", "--kubeconfig", "-o", "--output", "-l", "--selector"}


def kubectl_verb(cmd: str) -> str:
    """The verb of a kubectl command line (`kubectl -n x get pods` -> `get`; `rollout restart` -> `rollout-restart`)."""
    import shlex

    try:
        words = shlex.split(cmd or "")
    except ValueError:
        words = (cmd or "").split()
    rest, skip = [], False
    for w in words:
        if skip:
            skip = False
        elif w == "kubectl":
            continue
        elif w in _FLAGS_WITH_VALUE:
            skip = True
        elif not w.startswith("-"):
            rest.append(w)
    if not rest:
        return ""
    return f"rollout-{rest[1]}" if rest[0] == "rollout" and len(rest) > 1 else rest[0]


def is_real_write(action: str, args: dict) -> bool:
    """The driver logs every `exec_kubectl_guarded` call as a write; only the mutating kubectl verbs change the cluster."""
    if action == "exec_kubectl_guarded":
        return kubectl_verb((args or {}).get("cmd", "")) in MUTATING_VERBS
    return True


def tokens(usage: dict | None, kind: str) -> int:
    """Token count from a usage block in either format: input/output (SREGym v2, what the agent writes) or prompt/completion."""
    u = usage or {}
    names = ("input_tokens", "prompt_tokens") if kind == "in" else ("output_tokens", "completion_tokens")
    for n in names:
        if isinstance(u.get(n), int):
            return u[n]
    return 0


def clip(text: str, n: int = OBS_LINES) -> str:
    """The observation as the agent saw it, up to n lines. The agent gets the whole command output (up to 8,000 characters,
    ending in </output>); a recorded copy without that ending was cut when it was saved (older runs saved 3,000
    characters), so the agent saw more than the story can show, and the story says so."""
    lines = text.splitlines()
    cut_note = ""
    if text.lstrip().startswith("<exit_code>") and "</output>" not in text:
        cut_note = f"\n... [the saved copy ends here ({len(text)} characters); the agent saw more of this output]"
    if len(lines) <= n:
        return text + cut_note
    return "\n".join(lines[:n]) + f"\n... [{len(lines) - n} more lines the agent also saw]" + cut_note


def cluster_line(c: dict) -> str:
    k = c["type"]
    if k == "snapshot":
        pods = c.get("pods", [])
        bad = [p for p in pods if p["ready"].split("/")[0] != p["ready"].split("/")[1] or p["phase"] != "Running"]
        names = ", ".join(sorted(o["name"] for o in c.get("objects", []) if o["kind"] == "Deployment"))
        return (
            f"SNAPSHOT of `{c['namespace']}`: {len(pods)} pods ({len(bad)} not ready), "
            f"{len(c.get('objects', []))} objects. Deployments: {names or 'none'}"
        )
    if k == "pod":
        extra = f" — {c['reason']}" if c.get("reason") else ""
        return f"pod `{c['name']}` → {c['phase']} ready {c['ready']} restarts {c['restarts']}{extra}"
    if k == "event":
        return f"WARNING event {c['reason']} on `{c['object']}`: {c['message']}"
    if k == "object":
        gen = f" (generation {c.get('previousGeneration')} → {c.get('generation')})" if c.get("generation") else ""
        return f"`{c['kind']}/{c['name']}` was modified{gen}"
    return json.dumps(c)[:200]


def render_story(transcript_path: str, cluster_path: str | None = None) -> str:
    """Markdown story of one run. Importable (the ReliOps Lab calls this) and used by the CLI below.
    Raises ValueError for an empty transcript."""
    tr = load(transcript_path)
    cl = load(cluster_path)
    if not tr:
        raise ValueError("empty transcript")

    meta = next((r for r in tr if r["type"] == "meta"), {})
    calls = [r for r in tr if r["type"] == "model_call"]
    writes = [r for r in tr if r["type"] == "write_action" and is_real_write(r.get("action", ""), r.get("args", {}))]
    submits = [r for r in tr if r["type"] == "submit"]
    prompt_tok = sum(tokens(r.get("usage"), "in") for r in calls)
    compl_tok = sum(tokens(r.get("usage"), "out") for r in calls)
    t0 = min([t(r) for r in tr] + [t(r) for r in cl])

    def rel(r: dict) -> str:
        return f"+{(t(r) - t0).total_seconds():6.1f}s"

    out: list[str] = []
    out.append(f"# Run replay — `{meta.get('artifact_id', '?')}`\n")
    out.append(
        f"- model: `{meta.get('model', '?')}` · action space: `{meta.get('action_space', '?')}` · "
        f"flow: `{meta.get('flow_variant', '?')}`"
    )
    out.append(
        f"- {len(calls)} model calls · {len(writes)} write action(s) · tokens: {prompt_tok} in / {compl_tok} out"
    )
    if meta.get("features") or meta.get("variant"):
        out.append(f"- agent variant: `{meta.get('variant') or '-'}` · switches on: {', '.join(meta.get('features') or []) or 'none'}")
    for s in submits:
        out.append(f"- submitted **{s['stage']}** (received by the grader: {'yes' if s['accepted'] else 'no'}; this says nothing about whether it was correct, see the log or the results table for the grade)")
    if not any("observation" in r for r in tr if r["type"] == "action"):
        out.append(
            "- note: this transcript has no observations (run with `REACT_V1_LOG_OBS=on` to record what each "
            "command returned)"
        )
    n_claims = sum(1 for r in tr if r["type"] == "claim")
    n_critic = sum(1 for r in tr if r["type"] == "critic")
    if n_claims or n_critic:
        out.append(f"- claim ledger: {n_claims} claim(s) · {n_critic} critic verdict(s)")
    out.append("\nLegend: `[cluster]` = what happened to the system · `Step N` = what the agent did · "
               "`[claim]` / `[critic]` = the reasoning ledger, when the agent records one.\n")

    # Build a merged, time-ordered event list. Agent steps are grouped: model_call + its action/submit.
    items: list[tuple[datetime, str, dict]] = []
    for c in cl:
        items.append((t(c), "cluster", c))
    step_no = 0
    pending: dict | None = None
    for r in tr:
        if r["type"] == "model_call":
            pending = r
        elif r["type"] in ("action", "submit") and pending is not None:
            step_no += 1
            items.append((t(pending), "step", {"n": step_no, "call": pending, "result": r}))
            pending = None
        elif r["type"] in ("claim", "critic"):
            items.append((t(r), "ledger", r))
        elif r["type"] == "feature":
            extra = ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("ts", "type", "name", "stage", "event"))
            items.append((t(r), "note", {"text": f"[feature {r.get('name')}] {r.get('event')} (stage {r.get('stage')}{', ' + extra if extra else ''})"}))
        elif r["type"] == "wrap_up":
            items.append((t(r), "note", {"text": f"wrap-up forced ({r['reason']}) — told to submit now"}))
        elif r["type"] == "end":
            items.append((t(r), "note", {"text": f"run ended, return code {r['return_code']}"}))
    items.sort(key=lambda x: x[0])

    out.append("## Timeline\n")
    for ts, kind, d in items:
        stamp = f"+{(ts - t0).total_seconds():6.1f}s"
        if kind == "cluster":
            out.append(f"`{stamp}` **[cluster]** {cluster_line(d)}\n")
        elif kind == "note":
            out.append(f"`{stamp}` _{d['text']}_\n")
        elif kind == "ledger":
            out.append(f"`{stamp}` {ledger_line(d)}\n")
        else:
            call, res = d["call"], d["result"]
            thought, raw = split_thought(call.get("content", ""))
            out.append(f"### Step {d['n']} · `{stamp}` · stage `{res.get('stage')}`")
            if thought:
                out.append("**Thinks:** " + thought.replace("\n", " ")[:900])
            if res["type"] == "submit":
                out.append(f"**Submits:** {res.get('solution', '')[:1500]}  \n(received by the grader: {'yes' if res.get('accepted') else 'no'}; not the grade)")
            else:
                tag = " ⚠ WRITE (changes the cluster)" if res.get("action") in {w["action"] for w in writes} and any(
                    w["action"] == res["action"] and w["args"] == res["args"] for w in writes
                ) else ""
                valid = "" if res.get("valid", True) else " ✗ invalid action"
                out.append(f"**Does:** `{res.get('action')}` `{json.dumps(res.get('args', {}))}`{tag}{valid}")
                if "observation" in res:
                    out.append("**Sees:**\n```\n" + clip(res["observation"]) + "\n```")
            usage = call.get("usage") or {}
            if tokens(usage, "out"):
                out.append(f"_tokens: {tokens(usage, 'in')} in / {tokens(usage, 'out')} out_")
            out.append("")

    return "\n".join(out)


def ledger_line(r: dict) -> str:
    """Claim-ledger and critic records (proposal R1, docs/plan/02-agent.md). The agent does not emit them
    yet; the schema is fixed here so the viewer is ready when it does:
      {"type": "claim",  "claim": str, "evidence": [step numbers], "confidence": 0-1}
      {"type": "critic", "verdict": "ok" | "not_ok", "flagged": [claim strings], "note": str}"""
    if r["type"] == "claim":
        ev = ", ".join(str(e) for e in (r.get("evidence") or [])) or "none cited"
        conf = f" · confidence {r['confidence']}" if r.get("confidence") is not None else ""
        warn = " ⚠ no evidence cited" if not r.get("evidence") else ""
        return f"**[claim]** {r.get('claim', '')} — evidence: steps {ev}{conf}{warn}"
    verdict = str(r.get("verdict", "?")).upper().replace("_", " ")
    flagged = r.get("flagged") or []
    extra = f" — flagged: {'; '.join(flagged)}" if flagged else ""
    note = f" — {r['note']}" if r.get("note") else ""
    return f"**[critic]** {verdict}{extra}{note}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript")
    ap.add_argument("--cluster")
    ap.add_argument("--out")
    args = ap.parse_args()
    try:
        text = render_story(args.transcript, args.cluster)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
