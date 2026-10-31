"""Feature switches for react-v2. Every switch is OFF by default; with all of them off the agent behaves exactly
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
}


def enabled() -> dict[str, bool]:
    return {name: os.environ.get(f"REACT_V1_{name}", "off").strip().lower() == "on" for name in SWITCHES}


def active_names() -> list[str]:
    return [n for n, on in enabled().items() if on]
