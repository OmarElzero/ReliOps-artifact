"""Prompt text for react-v1."""

from __future__ import annotations

from .actions import OPTIONAL_ARGS, WRITE_ACTIONS, actions_for

MARKER = "SUBMIT"

SYSTEM_TEMPLATE = """You are an SRE agent diagnosing and fixing a problem in a Kubernetes application.

You act ONLY by replying with exactly one JSON object in a ```json fenced block, choosing one action
from the fixed list below.{shell_note}

Format:
```json
{{"action": "<action_name>", "args": {{...}}}}
```

Include a short THOUGHT before the JSON block explaining what you currently believe and why this
action will help confirm or refute it.

Available actions:
{action_list}

Special action "submit": use {{"action": "submit", "args": {{"solution": "<text>"}}}} to submit your
answer for the current stage, exactly as the task instructions describe (natural-language diagnosis
for the diagnosis stage, empty string for the mitigation stage after you've applied your fix).

Reply with exactly ONE JSON block per turn. Nothing else outside the THOUGHT text and the JSON block."""

SHELL_NOTE = """ You also have "exec_kubectl_guarded", a free-form kubectl command passed through a
safety guard (dry-run first, unsafe commands rejected). Prefer a typed action when one fits; use
exec_kubectl_guarded only for what no typed action covers."""


def _action_list_text(action_space: str, *, survey_tool: bool = False, catalogue_v2: bool = False,
                      optional_args: bool = False, health_sweep: bool = False, change_diff: bool = False) -> str:
    lines = []
    for name, (_, arg_names) in actions_for(action_space, survey_tool=survey_tool, catalogue_v2=catalogue_v2,
                                            health_sweep=health_sweep, change_diff=change_diff).items():
        kind = "write" if name in WRITE_ACTIONS else "read"
        shown = list(arg_names)
        if optional_args:
            shown += [f"[{a}]" for a in OPTIONAL_ARGS.get(name, [])]
        lines.append(f"- {name}({', '.join(shown)})  [{kind}]")
    return "\n".join(lines)


def system_text(action_space: str = "typed", *, survey_tool: bool = False, catalogue_v2: bool = False,
                optional_args: bool = False, knowledge: str = "", health_sweep: bool = False, change_diff: bool = False) -> str:
    shell_note = SHELL_NOTE if action_space == "typed+shell" else " You cannot run arbitrary shell commands — only these typed actions exist."
    text = SYSTEM_TEMPLATE.format(
        action_list=_action_list_text(action_space, survey_tool=survey_tool, catalogue_v2=catalogue_v2, optional_args=optional_args,
                                      health_sweep=health_sweep, change_diff=change_diff),
        shell_note=shell_note)
    if optional_args:
        text += "\n\nArguments in [brackets] are optional."
    if knowledge:
        text += "\n\n## General Kubernetes notes\n\n" + knowledge.strip()
    return text


WORKFLOW_TEXT = """

## How to work

1. Before each action, say what you currently think is wrong and what this action would tell you or fix.
2. Read the result before asking for more; say what it rules in and what it rules out.
3. Survey broadly (get_pod_status, get_events) before going deep into one component's logs.
4. Only use a write action once you have evidence for the specific fix; a write action you cannot
   justify from prior output is not worth taking.
5. Stop and submit as soon as your evidence answers the task."""


FAULT_EXISTS_TEXT = """
6. The task says there is a problem, so there is one. If everything looks healthy, that does not mean there
   is no fault: the fault may be in configuration, environment, resource settings, scheduling, networking or
   storage, or the symptom may have settled after restarts. Look at what you have not yet looked at before
   you conclude."""

SURVEY_TEXT = """
7. Start with the "survey" action: it lists the main object kinds of the namespace in one call. Read it
   before going deep into any one component, and say which objects you have not yet inspected."""

LEDGER_TEXT = """
8. In every THOUGHT, keep a short hypothesis list, one line each: "H<n> [open|supported|ruled out] <claim>
   (evidence: step numbers)". Observations are numbered [step N]. Do not drop a hypothesis until an
   observation rules it out, and do not call one supported without citing the step that supports it."""


HEALTH_SWEEP_TEXT = """
9. "health_sweep" runs the standard per-kind health checks of the open-source k8sgpt tool over the cluster (pods,
   deployments, replica sets, services, ingresses, volume claims, stateful sets, daemon sets, jobs, cron jobs, nodes,
   webhooks, config maps) and lists every problem they report. An empty result means those checks found nothing, not
   that nothing is wrong."""

CHANGE_DIFF_TEXT = """
10. "recent_changes" lists every object changed after it was created (newest first), the objects created around the time
    the application was deployed, and what differs between each Deployment's previous and current pod template. A
    change is not a cause by itself: check whether it explains what you observe."""

VERIFY_UNDO_TEXT = """
11. In the mitigation stage, the objects you change are recorded first. When you submit, the standard health checks run
    again after a short wait; if your change made things worse or changed nothing they can see, it is undone and you are
    told why, so you can try a different fix."""


def instance_text(app_info: dict, *, fault_exists: bool = False, survey_first: bool = False, ledger: bool = False,
                  health_sweep: bool = False, change_diff: bool = False, verify_undo: bool = False) -> str:
    app_name = app_info.get("app_name", "unknown")
    namespace = app_info.get("namespace", "default")
    descriptions = app_info.get("descriptions", "")
    extra = (FAULT_EXISTS_TEXT if fault_exists else "") + (SURVEY_TEXT if survey_first else "") + (LEDGER_TEXT if ledger else "") \
        + (HEALTH_SWEEP_TEXT if health_sweep else "") + (CHANGE_DIFF_TEXT if change_diff else "") + (VERIFY_UNDO_TEXT if verify_undo else "")
    return f"""You are diagnosing and fixing an issue in the '{app_name}' application, namespace '{namespace}'.

{descriptions}

WORKFLOW:
TASK 1 (diagnosis): investigate, then submit a natural-language description of the root cause.
TASK 2 (mitigation): apply a fix using the available write actions, then submit an empty string
("solution": "") to trigger validation. Submitting is mandatory even after a successful fix.

CRITICAL: you are fully autonomous. Do not ask for confirmation; act on your best analysis.
{WORKFLOW_TEXT}{extra}"""


ACTION_OBSERVATION_TEMPLATE = "<exit_code>{code}</exit_code>\n<output>\n{body}\n</output>"

FORMAT_ERROR_TEXT = """Your reply did not contain exactly one ```json block with a valid action.
Reply with a THOUGHT, then exactly one ```json block choosing one action from the list, e.g.:
```json
{"action": "get_pod_status", "args": {"namespace": "hotel-reservation"}}
```"""

UNKNOWN_ACTION_TEXT = "Unknown action {name!r}. Choose one from the action list in the system prompt."

MISSING_ARGS_TEXT = "Action {name!r} is missing required args: {missing}."


# ---- messages the driver sends for the guard, self-check and soak switches (no problem-specific content) ----

EMPTY_DIAGNOSIS_TEXT = """Your submission for the diagnosis stage was empty. Task 1 needs a natural-language
description of the root cause: what is wrong, where, and the evidence you saw. Write it and submit again."""

SELFCHECK_TEXT = """Before the diagnosis is accepted, check it against what you observed:
1. List each claim in your diagnosis and the step number of the observation that supports it.
2. Name one alternative explanation you considered and the observation that rules it out.
3. If any claim has no supporting observation, run an action to get one now.
Then submit again. The submission must be the diagnosis itself (what is wrong, where, and the key evidence), not this
checklist: unchanged if it holds, corrected if it does not."""

SELFCHECK_FORMAT_TEXT = """That submission is the checklist, not the diagnosis. Submit only the diagnosis: what is wrong, where, and the
key evidence, in a few sentences."""

SOAK_TEXT = """Soak check: {seconds}s after your last change, this is the current state.

{status}

{events}

If anything is still unhealthy, or a pod restarted since your change, keep working on it. If it is healthy
and stable, submit again."""

VERIFY_UNDO_FAIL_TEXT = """Check {seconds}s after your changes: {why}. The standard health checks now report:
{findings}

Your changes were undone, so the cluster is back where it was before them:
{undone}

Work out why the fix did not work and try a different one, then submit again."""

VERIFY_PARTIAL_TEXT = """Check {seconds}s after your changes: some problems seen before them are gone, but these remain:
{findings}

If they belong to the incident, fix them too; then submit again."""
