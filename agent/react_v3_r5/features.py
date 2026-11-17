"""Feature switches for react-v3 (react-v2 plus plan 22 switches). Every switch is OFF by default; with all of them off the agent behaves exactly
like react-v1 (tests/test_off_equals_v1.py checks the prompts and the action list are identical).

Each switch is an environment variable REACT_V1_<NAME>=on (the prefix is shared with v1 so SREGym's env whitelist
logic stays one pattern). A run records which ones were on in the transcript `meta` record.
"""

from __future__ import annotations

import os

# name -> (what it is, ladder id from docs/plan/02-agent.md)
SWITCHES = {
    "TOKEN_LOG": "F12 - write token totals, cost and call counts into the transcript end record (logging only)",
    "EMPTY_SUBMIT_GUARD": "G0 - reject an empty diagnosis (twice at most) instead of submitting it",
    "OPTIONAL_ARGS": "B1 - pass optional action arguments (previous logs, container, tail) through and list them in the prompt",
    "BUDGET_AWARE": "F7 - show actions used and seconds left after every observation",
    "FAULT_EXISTS": "P1 - tell the agent that a fault exists, so a healthy-looking cluster is not evidence of no fault",
    "SURVEY": "F14 - survey-first instruction plus one read action that lists the main object kinds of the namespace",
    "LEDGER": "F2 - hypothesis ledger in each THOUGHT, with step numbers on observations so claims can cite them",
    "SELFCHECK": "F3 - one generic evidence-closure question before the first diagnosis is accepted",
    "SOAK": "F6 - after a fix, wait and re-read the cluster before the mitigation submit is accepted",
    "CATALOGUE_V2": "A4b - typed actions for field patches, deleting an object and running a command in a pod",
    "K8S_KNOWLEDGE": "F13 - append reviewed general Kubernetes notes (knowledge/k8s_notes.md) to the prompt",
    # Round 2 (docs/plan/14-plan-review-after-research.md): generic; content comes from the cluster or from k8sgpt, not from us.
    "HEALTH_SWEEP": "R2 - read action running the rules of k8sgpt's 14 core analyzers over the cluster (inspect_tools.py)",
    "CHANGE_DIFF": "R2 - read action listing every object changed after creation, objects created in the window, pod-template diffs",
    "OUTPUT_TRIM": "R2 - merge repeated lines in long observations and keep head and tail",
    "VERIFY_UNDO": "R2 - record objects before each mitigation write; on submit, wait, re-run the health checks, undo if worse or no effect",
    # Round 3 (owner approved 8 Nov 2026, change C-014): workflow change, not a prompt line. Content from kubernetes.io.
    "ROUTING": "R3 - triage, choose a problem category, load its general procedure (knowledge/procedures.md); writes and the diagnosis wait until one is loaded",
    "ROUTE_REVIEW": "R3 - needs ROUTING: before the diagnosis is accepted, check it against the loaded procedure's own conclusion test and the triage symptoms; if it does not hold, load another category",
    "FLAT_ARGS": "C-019 - accept action arguments written next to \"action\" (or under arguments/parameters/input) instead of only under \"args\"; format tolerance only",
    "PROC_V2": "C-020 - needs ROUTING: load knowledge/procedures_v2.md (rule-out step 0, IF branches, EXIT, known noise, ready commands) with a scope header, and add an event-age rule to triage",
    "ROUTE_MULTI": "R3 - needs ROUTING: load one procedure when the abnormal things are in one place, up to two (never more than three) when they are in unrelated places or nothing looks abnormal",
    # Plan 18 (owner approved 9 Nov 2026): knowledge, reasoning examples and context flow, each its own switch.
    "REF": "C-023 - needs ROUTING and PROC_V2: read action load_reference; a loaded procedure lists its reference entries (knowledge/reference.md); at most 3 entries per run",
    "EXCAP": "C-024 - three fixed capability examples in the prompt (start-up noise vs fault, EXIT with a rule-out, evidence before a write)",
    "FLOW": "C-025 - per-tool output caps with the full text kept by step, older observations shown as one-line digests (read action reopen), the loaded procedure pinned, mitigation starts from a hand-off; context sizes logged",
    # Plan 22 (owner approved 14 Nov 2026): agent react_v3 only; react_v2 and the frozen-30 arms are untouched.
    "EVIDENCE_FIRST": "C-027 - a fixed read-only collector runs before the first diagnosis turn and its output is added to the first message; follow-up reads stay allowed. View from REACT_V1_EVIDENCE_MODE: cards (C-027, G1 round r2) or bykind (C-028, every object compact, no finding rules)",
    "TRANSACTIONAL_FIX": "C-029 (T1) - mitigation submit is refused until the fix is proven: the driver records objects before each write, asks for the read that showed the fault, re-runs it after a wait with a pod-status read, and restores the objects and asks for a different fix family if the model says the fault is still there",
    "T1_DRIVER": "C-033 (T1 v2, plan 24) - needs TRANSACTIONAL_FIX: the driver records the namespace health findings at the start of the mitigation stage; at the submit after a change it waits and checks again, and if the result is worse or has no effect it restores the changed objects and asks for a different fix family without asking the model (2 rounds); otherwise the T1 proof step follows",
    "D1_PREDICT": "C-036 (r5, plan 27): before the diagnosis is submitted, the model states one prediction that must hold if its diagnosis is right and names one read that checks it; the driver runs that read and shows the output; the model keeps or revises the diagnosis (one round, then the submit goes through)",
    "FIX_FAMILIES": "C-037 (r5, plan 27) - needs TRANSACTIONAL_FIX: every restore message names the ordered fix families of the routed procedure and asks for the next untried family (procedure-guided TNR)",
    "ADAPTIVE_WAIT": "C-038 (r5, plan 27) - with TRANSACTIONAL_FIX: before a proof read or a T1 v2 verdict, wait until the namespace's rollouts have settled (30 s to 180 s) instead of a fixed 60 s",
    "FINAL_MODEL": "C-030 (M1, exploratory: changes the small-model claim) - at the diagnosis submit, one call to REACT_V1_FINAL_MODEL (default gemini/gemini-3.5-flash) writes the final diagnosis from the whole conversation",
    "DIAG_VOTE": "C-031 (S1) - at the diagnosis submit, three independent drafts from the agent's model, then one call picks the best supported; with FINAL_MODEL the pick is made by the final model",
    # Calibration only (plan 14, step M1): reads nothing, changes nothing, submits at once. A problem this agent passes has a
    # check that passes without a fix.
    "NULL_AGENT": "M1 - do-nothing agent: no model call, submits a fixed non-diagnosis and an empty fix",
}


def enabled() -> dict[str, bool]:
    return {name: os.environ.get(f"REACT_V1_{name}", "off").strip().lower() == "on" for name in SWITCHES}


def active_names() -> list[str]:
    return [n for n, on in enabled().items() if on]
