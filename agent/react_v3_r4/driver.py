"""react-v3 agent driver for SREGym (react-v2 plus plan 22: EVIDENCE_FIRST, TRANSACTIONAL_FIX) (react-v1 plus opt-in switches, see features.py; all off = v1) — ReAct loop with a swappable action space.

Harness structure (stage polling, deadlines, transcript, submission detection) follows the
pattern in clients/mini_sre/driver.py, which is SREGym's own reference harness. The one real
difference: actions come from a fixed catalogue (agent/react_v1/actions.py), parsed as a JSON
object, not free-text bash. REACT_V1_ACTION_SPACE=typed (default) restricts the model to a fixed
typed menu; =typed+shell adds one escape-hatch action routed through SREGym's own guarded kubectl
MCP tool (the same mechanism STRATUS uses), for the test-matrix.md action_space comparison.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

sregym_root = Path(__file__).resolve()
# Walk up until we find main.py (the sregym repo root), robust to being reached via a symlink
# (clients/reliops_v1 -> agent/react_v1) where parents[N] arithmetic would be wrong.
_candidate = sregym_root.parent
while _candidate != _candidate.parent and not (_candidate / "main.py").exists():
    _candidate = _candidate.parent
if str(_candidate) not in sys.path:
    sys.path.insert(0, str(_candidate))

from logger import init_logger  # noqa: E402

init_logger()

from clients.harness.problem_id import resolve_problem_id  # noqa: E402
from clients.harness.token_usage import aggregate_usage  # noqa: E402
from clients.mini_sre.backends import ApiBackend  # noqa: E402

from . import features  # noqa: E402
from . import inspect_tools  # noqa: E402
from . import actions as actions_mod  # noqa: E402
from .actions import OPTIONAL_ARGS, PROCEDURES_FILE, WRITE_ACTIONS, actions_for, before_conclude  # noqa: E402
from .pricing import cost_usd, price_note  # noqa: E402
from . import evidence  # noqa: E402
from .prompts import EVIDENCE_TEXT, T1_PROOF_TEXT, T1_REFUSED_TEXT, T1_RESTORED_TEXT, T1_VERDICT_TEXT  # noqa: E402
from .prompts import FINAL_DIAGNOSIS_TEXT, VOTE_PICK_TEXT  # noqa: E402
from .prompts import (  # noqa: E402
    ACTION_OBSERVATION_TEMPLATE,
    EMPTY_DIAGNOSIS_TEXT,
    FLOW_HANDOFF_TEXT,
    FORMAT_ERROR_TEXT,
    ROUTE_REVIEW_TEXT,
    ROUTING_GATE_TEXT,
    MISSING_ARGS_TEXT,
    SELFCHECK_TEXT,
    SELFCHECK_FORMAT_TEXT,
    SOAK_TEXT,
    VERIFY_PARTIAL_TEXT,
    VERIFY_UNDO_FAIL_TEXT,
    UNKNOWN_ACTION_TEXT,
    instance_text,
    system_text,
)

logger = logging.getLogger("all.react_v1.driver")

FEATURES = features.enabled()
SOAK_S = int(os.environ.get("REACT_V1_SOAK_S", "60"))
VERIFY_WAIT_S = int(os.environ.get("REACT_V1_VERIFY_WAIT_S", "60"))
MAX_UNDO_ROUNDS = int(os.environ.get("REACT_V1_MAX_UNDO_ROUNDS", "2"))
EVIDENCE_MODE = os.environ.get("REACT_V1_EVIDENCE_MODE", "cards").strip().lower()       # C-027 cards | C-028 bykind
T1_WAIT_S = int(os.environ.get("REACT_V1_T1_WAIT_S", "60"))
T1_MAX_ROUNDS = int(os.environ.get("REACT_V1_T1_MAX_ROUNDS", "2"))      # restores before the driver stops asking
FINAL_MODEL_ID = os.environ.get("REACT_V1_FINAL_MODEL", "gemini/gemini-3.5-flash")
VOTE_N = 3
T1_MAX_REFUSALS = 2                                                     # refused submits without a proof read, then let through
NULL_DIAGNOSIS = "No diagnosis: this is the do-nothing calibration agent; it observed nothing and changed nothing."
EMPTY_DIAGNOSIS_RETRIES = 2
_writes_total = 0  # valid write actions so far in this run (both stages); the soak check only applies after a write
_procedures_loaded: list[str] = []  # ROUTING: categories loaded so far in this run (both stages)
ROUTING_GATED = WRITE_ACTIONS - {"exec_kubectl_guarded", "exec_in_pod"}  # these two also serve reads, so triage may use them
ROUTING_GATE_MAX = 2  # refusals per stage before the gate lets the action through, so a stuck model cannot stall

# FLOW (C-025): the full text of every observation is kept by step; the model sees the last FLOW_KEEP in full, older ones
# as one-line digests, and can ask for any of them again with the read action reopen.
FLOW_KEEP = int(os.environ.get("REACT_V1_FLOW_KEEP", "3"))
FLOW_CAPS = {"get_pod_status": 60, "get_events": 30, "get_logs": 80, "describe": 80, "get_resource": 120,
             "exec_kubectl_guarded": 80, "exec_in_pod": 60, "survey": 80, "health_sweep": 40, "recent_changes": 40}
FLOW_DEFAULT_CAP = 80
FLOW_REOPEN_LINES = 80
FLOW_UNCAPPED = {"load_procedure", "load_reference", "reopen", "inspect_tls_secret"}
_ERROR_WORDS = re.compile(r"error|fail|fatal|exception|refused|denied|forbidden|timeout|timed out|invalid|warn|backoff|unhealthy|expired|x509|oom|killed|not found|panic", re.I)
_flow_raw: dict[int, str] = {}      # step -> full observation body (before caps)
_flow_digest: dict[int, str] = {}   # step -> one-line digest
_flow_step = 0
_diagnosis_text = ""                # the accepted diagnosis, for the mitigation hand-off
_ref_loads: list[str] = []          # REF: entries loaded so far in this run
_PLACEHOLDER_RE = re.compile(r"<(namespace|pod|name|service|deployment|secret|ingress|node|claim|configmap|container|port|address|time)[^<>]*>", re.I)

API_HOSTNAME = os.getenv("API_HOSTNAME", "localhost")
API_PORT = os.getenv("API_PORT", "8000")
CONDUCTOR_URL = f"http://{API_HOSTNAME}:{API_PORT}"

AGENT_LOGS_DIR = os.environ.get("AGENT_LOGS_DIR", "./logs/react-v1")
MODEL = os.environ.get("AGENT_MODEL_ID", "")
REASONING_EFFORT = os.environ.get("AGENT_REASONING_EFFORT")

HARD_CAP = int(os.environ.get("REACT_V1_HARD_CAP", "40"))
WRAP_UP_CALLS = int(os.environ.get("REACT_V1_WRAP_UP_CALLS", "3"))
RETRY_WAIT_S = float(os.environ.get("REACT_V1_RETRY_WAIT_S", "30"))
# Consecutive unusable model replies (empty, errors) before the stage gives up. v1 gave up after 2; round 1 lost 46 of 239
# attempts that way, most by the fifth call. v2.0 gave up after 4 (waits 30, 60, 90 s, about 4 minutes in all); the second blank
# smoke (6 Nov) lost a run to a provider window longer than that. v2.2 (C-013): give up after 7, waits grow RETRY_WAIT_S x n and
# are capped at RETRY_WAIT_MAX_S, so 30, 60, 90, 120, 120, 120 s (about 9 minutes of waiting in all).
MAX_MODEL_FAILURES = int(os.environ.get("REACT_V1_MAX_MODEL_FAILURES", "7"))
RETRY_WAIT_MAX_S = float(os.environ.get("REACT_V1_RETRY_WAIT_MAX_S", "120"))


def retry_wait(consecutive_failures: int) -> float:
    return min(RETRY_WAIT_S * consecutive_failures, RETRY_WAIT_MAX_S)


MAX_FORMAT_ERRORS = 3

# Blank-reply recovery (approved 5 Nov 2026, experiments/proposals/blank-reply-recovery.md, C-012). On some conversations
# `gemini-3.5-flash-lite` answers with nothing, every time, when the agent's earlier replies are sent as assistant turns; sent as
# user notes the same conversation gets a normal answer (replays: blank 8/8 + 5/6 as saved, normal 6/6 as notes). So after the
# first blank reply the stage retries at once with the earlier replies as user notes and stays in that form. Only a blank reply
# triggers it; a run without one sends exactly the messages it sent before. Set REACT_V1_BLANK_RECOVERY=off for the old behaviour.
BLANK_RECOVERY = os.environ.get("REACT_V1_BLANK_RECOVERY", "on").strip().lower() not in ("off", "0", "false", "no")
NOTE_PREFIX = "[your previous reply]\n"


def as_notes(messages: list[dict]) -> list[dict]:
    """The conversation with every assistant turn re-sent as a user message (the original list is not changed)."""
    return [{"role": "user", "content": NOTE_PREFIX + str(m.get("content") or "")} if m.get("role") == "assistant" else m for m in messages]


def is_blank_reply(error) -> bool:
    """True for the provider's "said nothing" case, not for a reply cut off at the token limit or any other error."""
    text = str(error or "")
    return text.startswith("empty model reply") and "truncated" not in text


_CHECKLIST_RE = re.compile(r"claims? and support|supporting observation|alternative explanation", re.IGNORECASE)


def looks_like_checklist(text) -> bool:
    """True when a re-submitted diagnosis is the self-check's own checklist (seen in 9 round-1 runs) instead of a diagnosis.
    Matches only the wording of SELFCHECK_TEXT, nothing about any fault."""
    return bool(_CHECKLIST_RE.search(str(text or "")))

# F7 (docs/plan/02-agent.md §3): off by default so baseline-v1 behaviour (frozen 24 Oct 2026) is
# unchanged unless a run explicitly opts in — this flag is itself the thing Phase C's OFAT
# ablation measures, so it must never silently become the new default.
BUDGET_AWARE = os.environ.get("REACT_V1_BUDGET_AWARE", "off") == "on"

# Logging-only flag (does not change what the model sees or does): when on, each `action` record in
# the transcript also stores the observation text returned to the model, so a run can be replayed
# step by step (scripts/replay_trace.py). Off by default so baseline-v1 transcripts stay identical.
LOG_OBS = os.environ.get("REACT_V1_LOG_OBS", "off") == "on"
LOG_OBS_MAX = int(os.environ.get("REACT_V1_LOG_OBS_MAX", "3000"))

JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
FLAT_ARGS_RESERVED = {"action", "args", "arguments", "parameters", "input", "thought", "thoughts", "reasoning"}

EXIT_OK = 0
EXIT_INFRA = 1
EXIT_MODEL_FAILURE = 2
EXIT_NO_SUBMISSION = 4


def conductor_status() -> dict | None:
    try:
        resp = requests.get(f"{CONDUCTOR_URL}/status", timeout=10)
        resp.raise_for_status()
        status = resp.json()
        return status if isinstance(status, dict) else None
    except Exception as e:
        logger.debug(f"status poll error: {e}")
        return None


def current_stage() -> str | None:
    status = conductor_status()
    return status.get("stage") if status else None


def wait_for_stage(target_stages: set[str], timeout: int = 300) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        stage = current_stage()
        if stage in target_stages:
            return stage
        time.sleep(2)
    raise TimeoutError(f"conductor did not reach {target_stages} within {timeout}s")


def get_app_info(max_retries: int = 6, backoff: int = 5) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(f"{CONDUCTOR_URL}/get_app", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"get_app attempt {attempt}/{max_retries} failed: {e}")
                time.sleep(backoff)
            else:
                raise


def run_deadline(status: dict | None) -> float | None:
    left = (status or {}).get("agent_remaining_seconds")
    if isinstance(left, bool) or not isinstance(left, (int, float)):
        return None
    return time.monotonic() + float(left)


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def write(self, record: dict) -> None:
        record = {"ts": datetime.now().astimezone().isoformat(), **record}
        self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


@dataclass
class Session:
    messages: list[dict] = field(default_factory=list)
    tags: list = field(default_factory=list)   # FLOW: per message, None or {"kind": "obs", "step", "digest", "pinned"}

    def open(self, system: dict, first_turn: str) -> None:
        self.messages = [system, {"role": "user", "content": first_turn}]
        self.tags = [None, None]

    def add_user(self, text: str, tag: dict | None = None) -> None:
        self.messages.append({"role": "user", "content": text})
        self.tags.append(tag)

    def add_assistant(self, reply) -> None:
        self.messages.append(reply.as_message(pass_reasoning=True))
        self.tags.append(None)


def _tag(session: Session, i: int):
    return session.tags[i] if i < len(session.tags) else None


def flow_view(session: Session) -> list[dict]:
    """FLOW: what the model is sent. Observations older than the last FLOW_KEEP become their one-line digest, except the
    procedure loaded last, which stays in full. Replies and driver messages are kept. session.messages is not changed."""
    obs = [i for i in range(len(session.messages)) if (_tag(session, i) or {}).get("kind") == "obs"]
    keep = set(obs[-FLOW_KEEP:]) if FLOW_KEEP > 0 else set()
    pins = [i for i in obs if _tag(session, i).get("pinned")]
    if pins:
        keep.add(pins[-1])
    return [{**m, "content": _tag(session, i)["digest"]} if i in obs and i not in keep else m
            for i, m in enumerate(session.messages)]


def context_sizes(session: Session, sent: list[dict]) -> dict:
    """FLOW logging: characters by part of what was sent (fixed prefix, full observations, digests, replies, other)."""
    sizes = {"fixed": 0, "obs_full": 0, "digests": 0, "replies": 0, "other": 0}
    for i, m in enumerate(sent):
        n = len(str(m.get("content") or ""))
        t = _tag(session, i) or {}
        if i < 2:
            sizes["fixed"] += n
        elif t.get("kind") == "obs":
            sizes["digests" if m.get("content") == t.get("digest") and str(session.messages[i].get("content")) != t.get("digest") else "obs_full"] += n
        elif m.get("role") == "assistant":
            sizes["replies"] += n
        else:
            sizes["other"] += n
    sizes["total"] = sum(sizes.values())
    return sizes


def _arg_summary(args: dict) -> str:
    shown = {k: v for k, v in (args or {}).items() if k != "namespace"}
    text = json.dumps(shown, ensure_ascii=False) if shown else ""
    return text if len(text) <= 100 else text[:97] + "..."


def flow_digest(step: int, action: str, args: dict, body: str) -> str:
    lines = body.splitlines()
    errs = sum(1 for l in lines if _ERROR_WORDS.search(l))
    return (f"[S{step}] {action} {_arg_summary(args)}: {len(lines)} lines, {errs} with error or warning words. "
            f"reopen(step={step}) shows it again.").replace("  ", " ")


def _strip_noise(body: str) -> str:
    """get_resource: drop managedFields and the last-applied annotation (bookkeeping, often longer than the object)."""
    out, skip = [], None
    for line in body.splitlines():
        indent = len(line) - len(line.lstrip())
        if skip is not None:
            if line.strip() and (indent < skip or (indent == skip and not line.lstrip().startswith("- "))):
                skip = None
            else:
                continue
        if line.strip().startswith("managedFields:"):
            skip = indent
            continue
        if "kubectl.kubernetes.io/last-applied-configuration" in line:
            skip = indent
            continue
        out.append(line)
    return "\n".join(out)


def flow_cap(action: str, body: str, step: int, args: dict | None = None) -> str:
    """FLOW: per-tool line cap. Events keep the newest lines (kubectl sorts oldest first); logs keep error lines and the
    newest lines; others keep the first lines. A note says what was cut and how to see it."""
    if action == "get_resource":
        body = _strip_noise(body)
    lines = body.splitlines()
    cap = FLOW_CAPS.get(action, FLOW_DEFAULT_CAP)
    if len(lines) <= cap:
        return body
    is_log = action == "get_logs" or (action == "exec_kubectl_guarded" and "kubectl logs" in str((args or {}).get("cmd", "")))
    if action == "get_events":
        kept = lines[:1] + lines[-(cap - 1):]
    elif is_log:
        tail = set(range(len(lines) - cap // 2, len(lines)))
        errs = [i for i in range(len(lines)) if i not in tail and _ERROR_WORDS.search(lines[i])][-(cap - cap // 2):]
        kept = [lines[i] for i in sorted(set(errs) | tail)]
    else:
        kept = lines[:cap]
    return "\n".join(kept) + (f"\n[cut: showing {len(kept)} of {len(lines)} lines. reopen(step={step}, grep=<text>) shows the "
                               f"lines that contain a text.]")


def flow_reopen(args: dict) -> str:
    raw_step = str((args or {}).get("step", "")).strip().upper().lstrip("S")
    try:
        step = int(raw_step)
    except ValueError:
        return ACTION_OBSERVATION_TEMPLATE.format(code=2, body=f"reopen needs step=<number>; known steps: 1 to {_flow_step - 1}")
    body = _flow_raw.get(step)
    if body is None:
        return ACTION_OBSERVATION_TEMPLATE.format(code=2, body=f"no stored output for step {step} (procedures and reference entries are not stored; load them again)")
    lines = body.splitlines()
    grep = str((args or {}).get("grep") or "").strip()
    if grep:
        hits = [f"{i + 1}: {l}" for i, l in enumerate(lines) if grep.lower() in l.lower()]
        text = "\n".join(hits[:FLOW_REOPEN_LINES]) or f"no line of step {step} contains {grep!r}"
        if len(hits) > FLOW_REOPEN_LINES:
            text += f"\n[{len(hits) - FLOW_REOPEN_LINES} more lines contain it; use a longer text]"
    else:
        text = "\n".join(lines[:FLOW_REOPEN_LINES])
        if len(lines) > FLOW_REOPEN_LINES:
            text += f"\n[showing the first {FLOW_REOPEN_LINES} of {len(lines)} lines; add grep=<text> to find the rest]"
    return ACTION_OBSERVATION_TEMPLATE.format(code=0, body=f"(full text of step {step})\n{text}"[:8000])


def flow_handoff(session: Session) -> None:
    """FLOW: the mitigation stage starts from the fixed prompt plus a hand-off, not the whole diagnosis trail."""
    procs = list(dict.fromkeys(_procedures_loaded))
    fix = ""
    if procs:
        body = actions_mod.procedures().get(procs[-1], "")
        fix = next((l for l in body.splitlines() if l.startswith("Fix families:")), "")
    digests = "\n".join(_flow_digest[k] for k in sorted(_flow_digest)) or "(none)"
    text = FLOW_HANDOFF_TEXT.format(diagnosis=_diagnosis_text or "(not recorded)",
                                    procedures=(", ".join(procs) or "none") + (f"\n{fix}" if fix else ""), digests=digests)
    session.messages = session.messages[:2] + [{"role": "user", "content": text}]
    session.tags = [None, None, None]


def ref_shadow_rank(recent: list[str], top: int = 3) -> list[str]:
    """REF: a keyword match of recent observations against each entry's Signals line. Logged only, never shown."""
    text = " ".join(recent).lower()
    scored = []
    for key, body in actions_mod.references().items():
        words = {w for w in re.findall(r"[a-z][a-z0-9]{3,}", actions_mod.reference_signals(body).lower())}
        hits = sum(1 for w in words if w in text)
        if hits:
            scored.append((hits, key))
    return [k for _, k in sorted(scored, key=lambda x: (-x[0], x[1]))[:top]]


@dataclass
class StageOutcome:
    stage: str
    termination_reason: str
    actions_used: int
    model_calls: int
    usage_records: list[dict] = field(default_factory=list)
    wall_seconds: float = 0.0

    def summary(self, model_id: str) -> dict:
        usage = aggregate_usage(self.usage_records)
        return {
            "actions_used": self.actions_used,
            "model_calls": self.model_calls,
            "termination_reason": self.termination_reason,
            "wall_seconds": self.wall_seconds,
            "usage_metrics": usage,
            "cost_usd": cost_usd(model_id, usage),
        }


def parse_action(content: str) -> dict | None:
    blocks = JSON_BLOCK_RE.findall(content or "")
    if len(blocks) != 1:
        return None
    try:
        obj = json.loads(blocks[0])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "action" not in obj:
        return None
    if FEATURES["FLAT_ARGS"]:
        # The model sometimes writes the arguments next to "action" instead of inside "args". Accept that layout and
        # the common alternative container names. An explicit args dict wins; flat keys only fill what is missing.
        args = obj.get("args")
        args = dict(args) if isinstance(args, dict) else {}
        for alt in ("arguments", "parameters", "input"):
            if isinstance(obj.get(alt), dict):
                for k, v in obj[alt].items():
                    args.setdefault(k, v)
        for k, v in obj.items():
            if k not in FLAT_ARGS_RESERVED:
                args.setdefault(k, v)
        obj["args"] = args
    obj.setdefault("args", {})
    return obj


def dispatch_action(action_name: str, args: dict, namespace: str, actions: dict, flow_step: int | None = None) -> tuple[str, bool]:
    """Returns (observation_text, is_valid_action)."""
    args = dict(args)
    args.setdefault("namespace", namespace)
    if action_name == "load_procedure":
        args.setdefault("category", "")   # an empty call returns the menu instead of an error
    if action_name not in actions:
        return UNKNOWN_ACTION_TEXT.format(name=action_name), False
    fn, required = actions[action_name]
    missing = [a for a in required if a not in args]
    if missing:
        return MISSING_ARGS_TEXT.format(name=action_name, missing=missing), False
    allowed = list(required) + (OPTIONAL_ARGS.get(action_name, []) if FEATURES["OPTIONAL_ARGS"] else [])
    call_args = {k: v for k, v in args.items() if k in allowed}
    if isinstance(call_args.get("previous"), str):
        call_args["previous"] = call_args["previous"].strip().lower() == "true"
    if "tail" in call_args:
        try:
            call_args["tail"] = max(1, min(int(call_args["tail"]), 2000))
        except (TypeError, ValueError):
            del call_args["tail"]
    try:
        result = fn(**call_args)
    except TypeError as e:
        return f"Bad arguments for {action_name!r}: {e}", False
    body = result.stdout + (("\n" + result.stderr) if result.stderr else "")
    flow = FEATURES["FLOW"] and flow_step is not None
    if flow:
        _flow_raw[flow_step] = body
    if FEATURES["OUTPUT_TRIM"]:
        body = inspect_tools.trim_output(body)
    if flow and action_name not in FLOW_UNCAPPED:
        body = flow_cap(action_name, body, flow_step, args)
    return ACTION_OBSERVATION_TEMPLATE.format(code=result.exit_code, body=body[:8000]), True


def final_diagnosis(backend, session: "Session", drafted: str, feature_event) -> str:
    """C-030 / C-031: rewrite the submitted diagnosis. Earlier replies are sent as user notes (blank-reply rule, C-012).
    Any failure keeps the agent's own diagnosis."""
    base = as_notes(session.messages)
    ask = base + [{"role": "user", "content": FINAL_DIAGNOSIS_TEXT}]
    try:
        picker = ApiBackend(FINAL_MODEL_ID, None) if FEATURES["FINAL_MODEL"] else backend
        if FEATURES["DIAG_VOTE"]:
            drafts = [drafted]
            for i in range(VOTE_N - 1):
                r = backend.complete(ask, step_dir=Path(AGENT_LOGS_DIR) / "steps" / f"vote_{i + 1:02d}")
                if not r.error and (r.content or "").strip():
                    drafts.append(r.content.strip())
            cands = "\n\n".join(f"Candidate {i + 1}:\n{d}" for i, d in enumerate(drafts))
            r = picker.complete(base + [{"role": "user", "content": VOTE_PICK_TEXT.format(candidates=cands)}],
                                step_dir=Path(AGENT_LOGS_DIR) / "steps" / "vote_pick")
            feature_event("DIAG_VOTE", "picked", drafts=len(drafts), error=r.error)
        else:
            r = picker.complete(ask, step_dir=Path(AGENT_LOGS_DIR) / "steps" / "final_model")
            feature_event("FINAL_MODEL", "written", model=FINAL_MODEL_ID, error=r.error)
        text = (r.content or "").strip()
        return text if text and not r.error else drafted
    except Exception as e:  # noqa: BLE001
        feature_event("FINAL_MODEL" if FEATURES["FINAL_MODEL"] else "DIAG_VOTE", "failed", error=str(e)[:300])
        return drafted


def run_stage(
    backend: ApiBackend,
    session: Session,
    transcript: Transcript,
    namespace: str,
    actions: dict,
    *,
    stage: str,
    run_ends: float,
    call_offset: int = 0,
) -> StageOutcome:
    global _writes_total, _flow_step, _diagnosis_text
    started = time.monotonic()
    usage_records: list[dict] = []
    model_calls = 0
    used = 0
    format_errors = 0
    consecutive_failures = 0
    note_mode = False              # blank-reply recovery: earlier agent replies are sent as user notes (see as_notes)
    wrap_up_sent = False
    wrap_up_calls = 0
    empty_rejections = 0
    review_asked = False
    review_loaded_at_ask = 0
    selfcheck_format_asked = False
    selfcheck_first: str | None = None  # the diagnosis as first submitted, when the self-check asked about it
    soak_done = False
    undo_snaps: dict = {}          # VERIFY_UNDO: (kind, name, namespace) -> snapshot taken before the first change to it
    undo_baseline: set | None = None
    undo_rounds = 0
    partial_told = False
    writes_since_verify = 0
    gate_refusals = 0
    t1_snaps: dict = {}             # TRANSACTIONAL_FIX: (kind, name, namespace) -> snapshot before the first change in this round
    t1_writes = 0
    t1_phase = None                 # None | "await_proof" | "await_verdict" | "proven"
    t1_rounds = 0
    t1_refusals = 0

    def feature_event(name: str, event: str, **extra) -> None:
        transcript.write({"type": "feature", "name": name, "stage": stage, "event": event, **extra})

    def outcome(reason: str) -> StageOutcome:
        return StageOutcome(stage, reason, used, model_calls, usage_records, round(time.monotonic() - started, 3))

    if FEATURES["NULL_AGENT"]:
        solution = NULL_DIAGNOSIS if stage == "diagnosis" else ""
        try:
            resp = requests.post(f"{CONDUCTOR_URL}/submit", json={"stage": stage, "solution": solution}, timeout=120)
            accepted = resp.status_code == 200 and resp.json().get("stage") == stage
        except Exception as e:
            accepted = False
            logger.warning(f"submit failed: {e}")
        transcript.write({"type": "submit", "stage": stage, "solution": solution, "accepted": accepted})
        feature_event("NULL_AGENT", "submitted")
        session.add_user(f"Submission accepted for stage '{stage}'.")
        return outcome("submitted" if accepted else "null_submit_failed")

    if FEATURES["EVIDENCE_FIRST"] and stage == "diagnosis":
        t_ev = time.monotonic()
        try:
            text = evidence.evidence_text(evidence.live_snapshot(namespace), EVIDENCE_MODE)
        except Exception as e:  # noqa: BLE001 - the run goes on without the evidence, and the transcript says so
            text = None
            feature_event("EVIDENCE_FIRST", "failed", error=str(e)[:300])
        if text:
            block = EVIDENCE_TEXT.format(evidence=text)
            if session.messages and session.messages[-1].get("role") == "user":
                session.messages[-1] = {**session.messages[-1], "content": str(session.messages[-1].get("content") or "") + block}
            else:
                session.add_user(block)
            feature_event("EVIDENCE_FIRST", "shown", mode=EVIDENCE_MODE, chars=len(text), seconds=round(time.monotonic() - t_ev, 1))

    while True:
        seconds_left = run_ends - time.monotonic()
        limit = None
        if seconds_left <= 0:
            limit = "deadline"
        elif used >= HARD_CAP:
            limit = "hard_cap"
        if limit:
            if not wrap_up_sent:
                wrap_up_sent = True
                transcript.write({"type": "wrap_up", "stage": stage, "reason": limit})
                session.add_user(f"You have hit the {limit} limit for this stage. Submit your best answer now via the submit action.")
            if wrap_up_calls >= WRAP_UP_CALLS:
                return outcome(f"{limit}_no_submission")
            wrap_up_calls += 1

        model_calls += 1
        sent = flow_view(session) if FEATURES["FLOW"] else session.messages
        reply = backend.complete(as_notes(sent) if note_mode else sent,
                                 step_dir=Path(AGENT_LOGS_DIR) / "steps" / f"{stage}_{call_offset + model_calls:02d}")
        usage_records.append(reply.usage)
        transcript.write(
            {
                "type": "model_call",
                "stage": stage,
                "call": call_offset + model_calls,
                "content": (reply.content or "")[:20000],
                "usage": reply.usage,
                "error": reply.error,
                **({"blank_recovery": True} if note_mode else {}),
                **({"context": context_sizes(session, sent)} if FEATURES["FLOW"] else {}),
            }
        )
        if reply.error:
            consecutive_failures += 1
            logger.warning(f"model call unusable: {reply.error}")
            if consecutive_failures >= MAX_MODEL_FAILURES:
                return outcome("model_failure")
            if BLANK_RECOVERY and not note_mode and is_blank_reply(reply.error):
                note_mode = True
                transcript.write({"type": "blank_recovery", "stage": stage, "call": call_offset + model_calls})
                logger.warning("blank reply: retrying at once with earlier replies sent as user notes")
                continue
            time.sleep(retry_wait(consecutive_failures))
            continue
        consecutive_failures = 0
        session.add_assistant(reply)

        parsed = parse_action(reply.content)
        if parsed is None:
            format_errors += 1
            if format_errors >= MAX_FORMAT_ERRORS:
                return outcome("repeated_format_error")
            session.add_user(FORMAT_ERROR_TEXT)
            continue
        format_errors = 0

        action_name = parsed.get("action")
        args = parsed.get("args", {})

        if FEATURES["TRANSACTIONAL_FIX"] and stage == "mitigation":
            if action_name == "not_fixed":
                if t1_phase != "await_verdict":
                    session.add_user("not_fixed is only an answer to a proof run. Continue with your fix.")
                    continue
                if t1_rounds >= T1_MAX_ROUNDS:
                    t1_phase = "proven"
                    feature_event("TRANSACTIONAL_FIX", "rounds_exhausted", rounds=t1_rounds)
                    session.add_user("No restore rounds are left. Make your best fix, then submit (empty solution).")
                    continue
                undone = [inspect_tools.restore(snap) for snap in reversed(list(t1_snaps.values()))]
                t1_rounds += 1
                feature_event("TRANSACTIONAL_FIX", "restored", objects=len(undone), round=t1_rounds)
                t1_snaps.clear(); t1_writes = 0; t1_phase = None
                session.add_user(T1_RESTORED_TEXT.format(undone="\n".join(f"- {u}" for u in undone) or "- nothing was recorded",
                                                         left=T1_MAX_ROUNDS - t1_rounds))
                continue
            if action_name == "submit" and t1_writes > 0 and t1_phase != "proven":
                if t1_phase == "await_verdict":
                    t1_phase = "proven"
                    feature_event("TRANSACTIONAL_FIX", "proven", round=t1_rounds)
                elif t1_refusals < T1_MAX_REFUSALS:
                    if t1_phase is None:
                        t1_phase = "await_proof"
                        feature_event("TRANSACTIONAL_FIX", "proof_asked", writes=t1_writes)
                        session.add_user(T1_PROOF_TEXT.format(seconds=T1_WAIT_S))
                    else:
                        t1_refusals += 1
                        feature_event("TRANSACTIONAL_FIX", "refused", count=t1_refusals)
                        session.add_user(T1_REFUSED_TEXT)
                    continue
                else:
                    feature_event("TRANSACTIONAL_FIX", "let_through", refusals=t1_refusals)
            elif t1_phase == "await_proof" and action_name in actions and action_name not in WRITE_ACTIONS and action_name != "submit":
                time.sleep(T1_WAIT_S)
                proof, valid = dispatch_action(action_name, args, namespace, actions)
                status, _ = dispatch_action("get_pod_status", {}, namespace, actions)
                if valid:
                    used += 1
                t1_phase = "await_verdict"
                feature_event("TRANSACTIONAL_FIX", "proof_run", action=action_name, valid=valid)
                session.add_user(T1_VERDICT_TEXT.format(seconds=T1_WAIT_S, action=f"{action_name} {json.dumps(args, ensure_ascii=False)}",
                                                        proof=proof, status=status))
                continue
            elif action_name in WRITE_ACTIONS and action_name in actions:
                for kind, name, ns in inspect_tools.write_targets(action_name, args, namespace):
                    key = (kind.lower(), name, ns)
                    if key not in t1_snaps:
                        snap = inspect_tools.snapshot(kind, name, ns)
                        if snap is not None:
                            t1_snaps[key] = snap
                            feature_event("TRANSACTIONAL_FIX", "recorded", kind=kind, object=name, absent=snap.get("absent", False))
                t1_writes += 1
                if t1_phase is not None:
                    feature_event("TRANSACTIONAL_FIX", "new_write_resets_proof", phase=t1_phase)
                    t1_phase = None

        if FEATURES["ROUTING"] and not _procedures_loaded and gate_refusals < ROUTING_GATE_MAX and (
                (action_name == "submit" and stage == "diagnosis") or (action_name in ROUTING_GATED and action_name in actions)):
            gate_refusals += 1
            feature_event("ROUTING", "refused", action=action_name, count=gate_refusals)
            session.add_user(ROUTING_GATE_TEXT.format(what="The diagnosis submission" if action_name == "submit" else f"The write action {action_name!r}"))
            continue

        if action_name == "submit":
            solution = args.get("solution", "")
            if FEATURES["EMPTY_SUBMIT_GUARD"] and stage == "diagnosis" and not str(solution or "").strip() \
                    and empty_rejections < EMPTY_DIAGNOSIS_RETRIES:
                empty_rejections += 1
                feature_event("EMPTY_SUBMIT_GUARD", "rejected_empty_diagnosis", count=empty_rejections)
                session.add_user(EMPTY_DIAGNOSIS_TEXT)
                continue
            if FEATURES["ROUTE_REVIEW"] and FEATURES["ROUTING"] and stage == "diagnosis" and str(solution or "").strip() \
                    and _procedures_loaded:
                if not review_asked:
                    review_asked = True
                    review_loaded_at_ask = len(_procedures_loaded)
                    feature_event("ROUTE_REVIEW", "asked", loaded=",".join(_procedures_loaded))
                    done = list(dict.fromkeys(_procedures_loaded))
                    tests = "\n".join(f"   - {c}: {before_conclude(c)}" for c in done)
                    session.add_user(ROUTE_REVIEW_TEXT.format(loaded=", ".join(done), tests=tests))
                    continue
                if review_loaded_at_ask is not None:
                    feature_event("ROUTE_REVIEW", "answered", rerouted=len(_procedures_loaded) > review_loaded_at_ask)
                    review_loaded_at_ask = None
            if FEATURES["SELFCHECK"] and stage == "diagnosis" and str(solution or "").strip():
                if selfcheck_first is None:
                    selfcheck_first = str(solution)
                    feature_event("SELFCHECK", "asked")
                    session.add_user(SELFCHECK_TEXT)
                    continue
                if selfcheck_first is not False and looks_like_checklist(solution) and not selfcheck_format_asked:
                    selfcheck_format_asked = True
                    feature_event("SELFCHECK", "checklist_submitted")
                    session.add_user(SELFCHECK_FORMAT_TEXT)
                    continue
                if selfcheck_first is not False:
                    feature_event("SELFCHECK", "answered", changed=str(solution).strip() != selfcheck_first.strip())
                    selfcheck_first = False
            if FEATURES["VERIFY_UNDO"] and stage == "mitigation" and writes_since_verify > 0:
                writes_since_verify = 0
                time.sleep(VERIFY_WAIT_S)
                after_f = inspect_tools.scoped(inspect_tools.sweep_findings(), namespace)
                after = inspect_tools.finding_keys(after_f)
                v = inspect_tools.verdict(undo_baseline or set(), after)
                feature_event("VERIFY_UNDO", "verified", verdict=v, before=len(undo_baseline or ()), after=len(after))
                listed = "\n".join(f"- {k} {key}: {t}" for k, key, t in after_f[:15]) or "- nothing"
                if v in ("worse", "no_effect") and undo_snaps and undo_rounds < MAX_UNDO_ROUNDS:
                    undone = [inspect_tools.restore(snap) for snap in reversed(list(undo_snaps.values()))]
                    undo_rounds += 1
                    undo_snaps.clear()
                    feature_event("VERIFY_UNDO", "undone", objects=len(undone), round=undo_rounds)
                    why = ("a problem appeared that was not there before your changes" if v == "worse"
                           else "the problems seen before your changes are all still there")
                    session.add_user(VERIFY_UNDO_FAIL_TEXT.format(seconds=VERIFY_WAIT_S, why=why, findings=listed,
                                                                  undone="\n".join(f"- {u}" for u in undone)))
                    continue
                if v == "partial" and not partial_told:
                    partial_told = True
                    session.add_user(VERIFY_PARTIAL_TEXT.format(seconds=VERIFY_WAIT_S, findings=listed))
                    continue
            if FEATURES["SOAK"] and stage == "mitigation" and not soak_done and _writes_total > 0:
                soak_done = True
                feature_event("SOAK", "waiting", seconds=SOAK_S)
                time.sleep(SOAK_S)
                status_obs, _ = dispatch_action("get_pod_status", {}, namespace, actions)
                events_obs, _ = dispatch_action("get_events", {}, namespace, actions)
                session.add_user(SOAK_TEXT.format(seconds=SOAK_S, status=status_obs, events=events_obs))
                feature_event("SOAK", "shown")
                continue
            if stage == "diagnosis" and str(solution or "").strip() and (FEATURES["FINAL_MODEL"] or FEATURES["DIAG_VOTE"]):
                solution = final_diagnosis(backend, session, str(solution), feature_event)
            try:
                resp = requests.post(f"{CONDUCTOR_URL}/submit", json={"stage": stage, "solution": solution}, timeout=120)
                accepted = resp.status_code == 200 and resp.json().get("stage") == stage
            except Exception as e:
                accepted = False
                logger.warning(f"submit failed: {e}")
            transcript.write({"type": "submit", "stage": stage, "solution": solution, "accepted": accepted})
            if accepted and stage == "diagnosis":
                _diagnosis_text = str(solution or "")
            if accepted:
                # Always close the turn with a user-role message before returning: some providers
                # (seen with gemini/* via Vertex) reject the next stage's first request if the
                # conversation we resume from ends on an assistant turn.
                session.add_user(f"Submission accepted for stage '{stage}'.")
                return outcome("submitted")
            session.add_user("Submission was not accepted by the conductor. Check the stage is still active and retry.")
            continue

        if FEATURES["VERIFY_UNDO"] and stage == "mitigation" and action_name in WRITE_ACTIONS and action_name in actions:
            if undo_baseline is None:
                undo_baseline = inspect_tools.finding_keys(inspect_tools.scoped(inspect_tools.sweep_findings(), namespace))
                feature_event("VERIFY_UNDO", "baseline", findings=len(undo_baseline))
            for kind, name, ns in inspect_tools.write_targets(action_name, args, namespace):
                key = (kind.lower(), name, ns)
                if key not in undo_snaps:
                    snap = inspect_tools.snapshot(kind, name, ns)
                    if snap is not None:
                        undo_snaps[key] = snap
                        feature_event("VERIFY_UNDO", "recorded", kind=kind, object=name, absent=snap.get("absent", False))
        step_n = None
        if FEATURES["FLOW"]:
            _flow_step += 1
            step_n = _flow_step
        if (FEATURES["REF"] or FEATURES["EXCAP"]) and _PLACEHOLDER_RE.search(json.dumps(args, ensure_ascii=False)):
            feature_event("REF" if FEATURES["REF"] else "EXCAP", "placeholder_in_action", action=action_name)
        if FEATURES["FLOW"] and action_name == "reopen":
            obs, valid = flow_reopen(args), True
            feature_event("FLOW", "reopen", step=str(args.get("step", "")), grep=bool(args.get("grep")))
        elif FEATURES["REF"] and action_name == "load_reference" and action_name in actions \
                and str(args.get("entry") or "").strip().lower() in actions_mod.references() \
                and len(_ref_loads) >= actions_mod.REF_MAX_LOADS:
            obs, valid = ACTION_OBSERVATION_TEMPLATE.format(
                code=0, body=f"You have loaded {actions_mod.REF_MAX_LOADS} reference entries; that is the limit. Continue with the evidence you have."), True
            feature_event("REF", "limit", entry=str(args.get("entry")))
        else:
            obs, valid = dispatch_action(action_name, args, namespace, actions, flow_step=step_n)
        if FEATURES["REF"] and action_name == "load_reference" and valid:
            entry = str(args.get("entry") or "").strip().lower()
            path = "entry" if "## reference: " in obs else ("menu" if "## reference entries" in obs else ("limit" if "the limit" in obs else "unknown"))
            if path == "entry":
                _ref_loads.append(entry)
            recent = [str(m.get("content") or "") for m in session.messages[-6:] if m.get("role") == "user"]
            feature_event("REF", "load", path=path, entry=entry, order=len(_ref_loads), shadow_top3=ref_shadow_rank(recent))
        if valid:
            used += 1
            if action_name == "load_procedure" and obs.startswith("<exit_code>0<") and "## procedure: " in obs:
                _procedures_loaded.append(str(args.get("category", "")).strip().lower())
                feature_event("ROUTING", "loaded", category=_procedures_loaded[-1], order=len(_procedures_loaded))
            if action_name in WRITE_ACTIONS:
                _writes_total += 1
                writes_since_verify += 1
                transcript.write({"type": "write_action", "stage": stage, "action": action_name, "args": args})
        action_record = {"type": "action", "stage": stage, "action": action_name, "args": args, "valid": valid}
        if LOG_OBS:
            action_record["observation"] = obs[:LOG_OBS_MAX]
        transcript.write(action_record)
        if FEATURES["LEDGER"]:
            obs = f"[step {call_offset + model_calls}]\n" + obs
        if BUDGET_AWARE:
            seconds_left_now = max(0, int(run_ends - time.monotonic()))
            obs += (
                f"\n\n[budget: {used}/{HARD_CAP} actions used this stage, "
                f"~{seconds_left_now}s left before you must submit]"
            )
        if FEATURES["FLOW"]:
            pinned = action_name == "load_procedure" and valid and "## procedure: " in obs
            digest = flow_digest(step_n, action_name, args, _flow_raw.get(step_n, obs))
            if action_name in ("load_procedure", "load_reference"):
                digest = f"[S{step_n}] {action_name} {_arg_summary(args)}: loaded earlier; call it again to read it."
            if action_name != "reopen":
                _flow_digest[step_n] = digest
            session.add_user(f"[S{step_n}]\n" + obs, {"kind": "obs", "step": step_n, "digest": digest, "pinned": pinned})
        else:
            session.add_user(obs)

        status = conductor_status()
        run_ends = run_deadline(status) or run_ends
        observed = status.get("stage") if status else None
        if observed not in {stage, None}:
            return outcome("submitted_by_external_check")


def save_results(path: Path, problem_id: str, return_code: int, usage: dict, model_id: str, meta: dict) -> None:
    payload = {
        "problem_id": problem_id,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "return_code": return_code,
        "success": return_code == EXIT_OK,
        "usage_metrics": usage,
        "cost_usd": cost_usd(model_id, usage),
        "price_note": price_note(model_id),
        "react_v1": meta,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ReliOps react-v1 agent")
    parser.add_argument("--logs-dir", default=AGENT_LOGS_DIR)
    parser.add_argument("--problem-id", default=None)
    args = parser.parse_args()

    if not MODEL:
        logger.error("AGENT_MODEL_ID is not set")
        sys.exit(EXIT_INFRA)

    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    problem_id = resolve_problem_id(cli_problem_id=args.problem_id)
    transcript = Transcript(logs_dir / "react_v1_transcript.jsonl")
    results_path = logs_dir / f"react_v1_results_{problem_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    action_space = os.environ.get("REACT_V1_ACTION_SPACE", "typed")
    if action_space not in ("typed", "typed+shell"):
        logger.warning(f"unknown REACT_V1_ACTION_SPACE {action_space!r}; defaulting to 'typed'")
        action_space = "typed"
    actions = actions_for(action_space, survey_tool=FEATURES["SURVEY"], catalogue_v2=FEATURES["CATALOGUE_V2"],
                          health_sweep=FEATURES["HEALTH_SWEEP"], change_diff=FEATURES["CHANGE_DIFF"], routing=FEATURES["ROUTING"],
                          ref=FEATURES["REF"], flow=FEATURES["FLOW"])
    if FEATURES["REF"] and not (FEATURES["ROUTING"] and FEATURES["PROC_V2"]):
        logger.error("REACT_V1_REF needs REACT_V1_ROUTING=on and REACT_V1_PROC_V2=on")
        sys.exit(EXIT_INFRA)
    if FEATURES["REF"] and not actions_mod.references():
        logger.error("REACT_V1_REF is on but %s is missing or empty", actions_mod.REFERENCE_FILE)
        sys.exit(EXIT_INFRA)
    if FEATURES["EXCAP"] and not FEATURES["ROUTING"]:
        logger.error("REACT_V1_EXCAP needs REACT_V1_ROUTING=on (its examples use load_procedure)")
        sys.exit(EXIT_INFRA)
    if (FEATURES["ROUTE_REVIEW"] or FEATURES["ROUTE_MULTI"] or FEATURES["PROC_V2"]) and not FEATURES["ROUTING"]:
        logger.error("REACT_V1_ROUTE_REVIEW, REACT_V1_ROUTE_MULTI and REACT_V1_PROC_V2 need REACT_V1_ROUTING=on")
        sys.exit(EXIT_INFRA)
    if FEATURES["ROUTING"] and not PROCEDURES_FILE.is_file():
        logger.error("REACT_V1_ROUTING is on but %s does not exist", PROCEDURES_FILE)
        sys.exit(EXIT_INFRA)
    knowledge = ""
    if FEATURES["K8S_KNOWLEDGE"]:
        notes = Path(__file__).resolve().parent / "knowledge" / "k8s_notes.md"
        if not notes.is_file():
            logger.error("REACT_V1_K8S_KNOWLEDGE is on but knowledge/k8s_notes.md does not exist (it must be written and reviewed first)")
            sys.exit(EXIT_INFRA)
        knowledge = notes.read_text(encoding="utf-8")

    backend = ApiBackend(MODEL, REASONING_EFFORT)
    meta: dict = {
        "model": MODEL,
        "action_space": action_space,
        "flow_variant": "react-v1",
        "artifact_id": problem_id,
        "hard_cap": HARD_CAP,
        "stages": {},
    }
    if features.active_names() or BUDGET_AWARE:
        meta["features"] = sorted(set(features.active_names()) | ({"BUDGET_AWARE"} if BUDGET_AWARE else set()))
        meta["variant"] = os.environ.get("REACT_V1_VARIANT", "")

    try:
        stage = wait_for_stage({"diagnosis", "mitigation"}, timeout=300)
    except TimeoutError:
        logger.error("timed out waiting for conductor stage")
        sys.exit(EXIT_INFRA)

    try:
        app_info = get_app_info()
    except Exception as e:
        logger.error(f"failed to get app info: {e}")
        sys.exit(EXIT_INFRA)

    namespace = app_info.get("namespace", "default")
    session = Session()
    session.open(
        {"role": "system", "content": system_text(action_space, survey_tool=FEATURES["SURVEY"], catalogue_v2=FEATURES["CATALOGUE_V2"],
                                                     optional_args=FEATURES["OPTIONAL_ARGS"], knowledge=knowledge,
                                                     health_sweep=FEATURES["HEALTH_SWEEP"], change_diff=FEATURES["CHANGE_DIFF"],
                                                     routing=FEATURES["ROUTING"], ref=FEATURES["REF"], flow=FEATURES["FLOW"])},
        instance_text(app_info, fault_exists=FEATURES["FAULT_EXISTS"], survey_first=FEATURES["SURVEY"], ledger=FEATURES["LEDGER"],
                      health_sweep=FEATURES["HEALTH_SWEEP"], change_diff=FEATURES["CHANGE_DIFF"], verify_undo=FEATURES["VERIFY_UNDO"],
                      routing=FEATURES["ROUTING"], route_multi=FEATURES["ROUTE_MULTI"], ref=FEATURES["REF"],
                      excap=FEATURES["EXCAP"], flow=FEATURES["FLOW"]),
    )
    transcript.write({"type": "meta", **meta, "conductor_url": CONDUCTOR_URL})

    run_ends = run_deadline(conductor_status()) or (time.monotonic() + 1800)

    return_code = EXIT_OK
    usage_records: list[dict] = []
    submitted_stages: list[str] = []
    calls = 0

    def record(outcome: StageOutcome) -> None:
        nonlocal return_code
        usage_records.extend(outcome.usage_records)
        meta["stages"][outcome.stage] = outcome.summary(MODEL)
        if outcome.termination_reason in ("submitted", "submitted_by_external_check"):
            submitted_stages.append(outcome.stage)
        else:
            logger.warning(f"{outcome.stage} ended without submission: {outcome.termination_reason}")
            if return_code == EXIT_OK:
                return_code = EXIT_MODEL_FAILURE if outcome.termination_reason == "model_failure" else EXIT_NO_SUBMISSION
        meta["submitted_stages"] = list(submitted_stages)
        save_results(results_path, problem_id, return_code, aggregate_usage(usage_records), MODEL, meta)

    if stage == "diagnosis":
        outcome = run_stage(backend, session, transcript, namespace, actions, stage="diagnosis", run_ends=run_ends)
        calls = outcome.model_calls
        record(outcome)
        if "diagnosis" in submitted_stages:
            try:
                stage = wait_for_stage({"mitigation", "tearing_down", "done"}, timeout=600)
            except TimeoutError:
                stage = None
        else:
            stage = None

    if stage == "mitigation":
        if FEATURES["FLOW"] and "diagnosis" in submitted_stages:
            flow_handoff(session)
            transcript.write({"type": "feature", "name": "FLOW", "stage": "mitigation", "event": "handoff",
                              "digests": len(_flow_digest), "chars": len(session.messages[-1]["content"])})
        run_ends = run_deadline(conductor_status()) or run_ends
        record(
            run_stage(
                backend, session, transcript, namespace, actions, stage="mitigation", run_ends=run_ends, call_offset=calls
            )
        )

    end_record = {"type": "end", "return_code": return_code}
    if FEATURES["TOKEN_LOG"]:
        usage_total = aggregate_usage(usage_records)
        end_record.update({"usage": usage_total, "cost_usd": cost_usd(MODEL, usage_total), "model_calls": len(usage_records)})
    transcript.write(end_record)
    transcript.close()
    logger.info(f"react-v1 finished with return code {return_code}")
    sys.exit(return_code)


if __name__ == "__main__":
    main()
