"""Typed action catalogue for react-v1 (action_space=typed).

Every action here maps to exactly one kubectl invocation, built from argument lists (never shell
string interpolation), so the model can only ever reach this fixed menu — it cannot express an
arbitrary kubectl command. This is the "typed" arm of the test-matrix.md action_space axis; the
"typed+shell" arm (a later build) adds one more action that accepts a free kubectl command string
behind the same guard SREGym's own exec_kubectl_cmd_safely uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


def _run(args: list[str], timeout: int = 60) -> ActionResult:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return ActionResult(proc.stdout, proc.stderr, proc.returncode)
    except subprocess.TimeoutExpired as e:
        return ActionResult(e.stdout or "", (e.stderr or "") + f"\n[timed out after {timeout}s]", 124, timed_out=True)
    except FileNotFoundError as e:
        return ActionResult("", str(e), 127)


# ---- read actions ----


def get_pod_status(namespace: str) -> ActionResult:
    return _run(["kubectl", "get", "pods", "-n", namespace, "-o", "wide"])


def get_logs(namespace: str, pod: str, container: str | None = None, tail: int = 200, previous: bool = False) -> ActionResult:
    args = ["kubectl", "logs", pod, "-n", namespace, f"--tail={tail}"]
    if container:
        args += ["-c", container]
    if previous:
        args += ["--previous"]
    return _run(args)


def describe(namespace: str, kind: str, name: str) -> ActionResult:
    return _run(["kubectl", "describe", kind, name, "-n", namespace])


def get_events(namespace: str) -> ActionResult:
    return _run(["kubectl", "get", "events", "-n", namespace, "--sort-by=.lastTimestamp"])


def get_resource(namespace: str, kind: str, name: str, output: str = "yaml") -> ActionResult:
    return _run(["kubectl", "get", kind, name, "-n", namespace, "-o", output])


# ---- write actions (bounded) ----


def restart_deployment(namespace: str, name: str) -> ActionResult:
    return _run(["kubectl", "rollout", "restart", f"deployment/{name}", "-n", namespace])


def scale_deployment(namespace: str, name: str, replicas: int) -> ActionResult:
    return _run(["kubectl", "scale", f"deployment/{name}", "-n", namespace, f"--replicas={int(replicas)}"])


def rollback_deployment(namespace: str, name: str) -> ActionResult:
    return _run(["kubectl", "rollout", "undo", f"deployment/{name}", "-n", namespace])


def set_env(namespace: str, deployment: str, key: str, value: str, container: str | None = None) -> ActionResult:
    args = ["kubectl", "set", "env", f"deployment/{deployment}", "-n", namespace, f"{key}={value}"]
    if container:
        args += ["-c", container]
    return _run(args)


def patch_configmap_key(namespace: str, configmap: str, key: str, value: str) -> ActionResult:
    patch = json.dumps({"data": {key: value}})
    return _run(["kubectl", "patch", "configmap", configmap, "-n", namespace, "--type", "merge", "-p", patch])


def delete_pod(namespace: str, pod: str) -> ActionResult:
    """Force recreation of one pod (its controller will replace it). Scoped to a single named pod."""
    return _run(["kubectl", "delete", "pod", pod, "-n", namespace])


# ---- survey (switch SURVEY) ----

_SURVEY_SKIP = {"events", "events.events.k8s.io", "endpoints", "endpointslices.discovery.k8s.io", "leases.coordination.k8s.io"}


def survey(namespace: str) -> ActionResult:
    """One read-only overview: the name of every object, of every namespaced kind the cluster reports, in the
    namespace (so no kind is chosen by us), plus the nodes. Events, endpoints and leases are left out as noise."""
    kinds_out = _run(["kubectl", "api-resources", "--verbs=list", "--namespaced=true", "-o", "name"])
    kinds = [k for k in kinds_out.stdout.split() if k not in _SURVEY_SKIP]
    parts = []
    if kinds:
        objs = _run(["kubectl", "get", ",".join(kinds), "-n", namespace, "-o", "name", "--ignore-not-found"], timeout=90)
        parts.append(f"## objects in namespace {namespace}\n{objs.stdout}")
    else:
        parts.append(f"## could not list resource kinds\n{kinds_out.stderr}")
    nodes = _run(["kubectl", "get", "nodes", "-o", "wide"])
    parts.append(f"## nodes\n{nodes.stdout}{(chr(10) + nodes.stderr) if nodes.stderr else ''}")
    return ActionResult("\n".join(parts), "", 0)


# ---- catalogue v2 (switch CATALOGUE_V2): generic typed actions for what the v1 menu cannot express ----


def patch_resource(namespace: str, kind: str, name: str, patch, patch_type: str | None = None) -> ActionResult:
    """kubectl patch. patch: a JSON string, or the object/list itself. patch_type: strategic | merge | json; when it is
    not given, a list (a JSON patch) uses json and an object uses strategic."""
    if isinstance(patch, (list, dict)):
        body = patch
        patch = json.dumps(patch)
    else:
        try:
            body = json.loads(patch)
        except (json.JSONDecodeError, TypeError) as e:
            return ActionResult("", f"patch is not valid JSON: {e}", 2)
    if patch_type is None:
        patch_type = "json" if isinstance(body, list) else "strategic"
    if patch_type not in ("strategic", "merge", "json"):
        return ActionResult("", f"patch_type must be strategic, merge or json, got {patch_type!r}", 2)
    if isinstance(body, list) != (patch_type == "json"):
        return ActionResult("", "a JSON patch (a list of operations) needs patch_type json; strategic and merge take an object", 2)
    return _run(["kubectl", "patch", kind, name, "-n", namespace, "--type", patch_type, "-p", patch])


def delete_resource(namespace: str, kind: str, name: str) -> ActionResult:
    """Delete one named object (any kind except namespace). The controller recreates it if there is one."""
    if kind.lower() in ("namespace", "namespaces", "ns", "node", "nodes"):
        return ActionResult("", f"deleting a {kind} is not allowed", 2)
    return _run(["kubectl", "delete", kind, name, "-n", namespace])


def exec_in_pod(namespace: str, pod: str, command: str, container: str | None = None) -> ActionResult:
    """Run one command inside a pod (no shell: the command string is split into words)."""
    import shlex

    try:
        words = shlex.split(command)
    except ValueError as e:
        return ActionResult("", f"cannot parse command: {e}", 2)
    args = ["kubectl", "exec", pod, "-n", namespace]
    if container:
        args += ["-c", container]
    return _run(args + ["--"] + words, timeout=90)


# ---- procedures (switch ROUTING) ----

_PROC_V2 = os.environ.get("REACT_V1_PROC_V2", "").strip().lower() == "on"   # same rule as features.FEATURES
PROCEDURES_FILE = Path(__file__).resolve().parent / "knowledge" / ("procedures_v2.md" if _PROC_V2 else "procedures.md")
PROC_V2_SCOPE = (
    "Scope: you loaded this because triage pointed at {cat}. This is a hypothesis, not a finding; it may be wrong.\n"
    "For now check only {cat}. Follow the steps in order and say which step you are on. Write any other abnormal thing "
    "you see in one line and leave it for later.\n"
    "When a step says EXIT, this category is ruled out: say which observation ruled it out and load the next most likely one.\n"
)


def procedures() -> dict[str, str]:
    """category id -> procedure text, from the "## <id>" sections of knowledge/procedures.md (HTML comments removed)."""
    text = re.sub(r"<!--.*?-->", "", PROCEDURES_FILE.read_text(encoding="utf-8"), flags=re.S)
    out: dict[str, str] = {}
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        out[head.strip().lower()] = body.strip()
    return out


def procedure_hints() -> list[tuple[str, str]]:
    """(category, its "Points here when" line) for the prompt's category list."""
    hints = []
    for cat, body in procedures().items():
        first = next((l for l in body.splitlines() if l.startswith("Points here when:")), "")
        hint = first.removeprefix("Points here when:").strip()
        not_when = next((l for l in body.splitlines() if l.startswith("Does not point here when:")), "")
        if not_when:
            hint += " Not when: " + not_when.removeprefix("Does not point here when:").strip()
        hints.append((cat, hint))
    return hints


def before_conclude(category: str) -> str:
    """The "Before you conclude:" line of one procedure (empty if unknown)."""
    body = procedures().get(str(category).strip().lower(), "")
    return next((l.removeprefix("Before you conclude:").strip() for l in body.splitlines() if l.startswith("Before you conclude:")), "")


def load_procedure(category: str = "") -> ActionResult:
    """Read-only: the general investigation procedure for one problem category.
    With no category it returns the menu (id and "Points here when" line) instead of an error."""
    procs = procedures()
    key = str(category or "").strip().lower()
    if not key:
        menu = "\n".join(f"- {c}: {h}" for c, h in procedure_hints())
        return ActionResult("## procedure menu (nothing loaded yet)\n" + menu +
                            "\nCall load_procedure again and set category to the one id from this list that best explains what you saw.", "", 0)
    if key not in procs:
        return ActionResult("", f"unknown category {category!r}; choose one of: {', '.join(procs)}", 2)
    body = (PROC_V2_SCOPE.format(cat=key) + procs[key]) if _PROC_V2 else procs[key]
    return ActionResult(f"## procedure: {key}\n{body}", "", 0)


ROUTING_ACTIONS = {
    "load_procedure": (load_procedure, ["category"]),
}


# ---- shell escape hatch (action_space=typed+shell only) ----

_MCP_SESSION_ID = str(uuid.uuid4())


async def _call_kubectl_mcp_tool(tool_name: str, arguments: dict | None = None) -> str:
    """Call SREGym's own kubectl MCP guard (dry-run + unsafe-command filter + rollback stack) —
    the same mechanism STRATUS uses (clients/stratus/stratus_utils/str_to_tool.py), so the
    typed-vs-shell comparison isn't confounded by a different, home-grown guard."""
    from fastmcp import Client
    from fastmcp.client import SSETransport

    api_hostname = os.getenv("API_HOSTNAME", "localhost")
    mcp_server_port = os.getenv("MCP_SERVER_PORT", "9954")
    mcp_base_url = os.getenv("MCP_SERVER_URL", f"http://{api_hostname}:{mcp_server_port}")
    transport = SSETransport(
        url=f"{mcp_base_url}/kubectl/sse",
        headers={"sregym_ssid": _MCP_SESSION_ID},
        sse_read_timeout=120,
    )
    client = Client(transport)
    async with client:
        result = await client.call_tool(tool_name, arguments=arguments or {})
        return "\n".join(part.text for part in result if hasattr(part, "text"))


def exec_kubectl_guarded(cmd: str, namespace: str | None = None) -> ActionResult:
    """Free-form kubectl command, routed through SREGym's own guarded MCP tool (dry-run first,
    unsafe-command filter, rollback stack). `namespace` is accepted but unused — the command
    string must name its own namespace with -n, same as the real exec_kubectl_cmd_safely tool."""
    del namespace
    try:
        text = asyncio.run(_call_kubectl_mcp_tool("exec_kubectl_cmd_safely", {"cmd": cmd}))
        return ActionResult(text, "", 0)
    except Exception as e:
        return ActionResult("", f"MCP call failed: {e}", 1)


def rollback_last_guarded_command() -> ActionResult:
    """Roll back the last command run via exec_kubectl_guarded, via SREGym's own rollback_command tool."""
    try:
        text = asyncio.run(_call_kubectl_mcp_tool("rollback_command"))
        return ActionResult(text, "", 0)
    except Exception as e:
        return ActionResult("", f"MCP call failed: {e}", 1)


# name -> (callable, required arg names) for the driver's dispatcher + prompt text
TYPED_ACTIONS = {
    "get_pod_status": (get_pod_status, ["namespace"]),
    "get_logs": (get_logs, ["namespace", "pod"]),
    "describe": (describe, ["namespace", "kind", "name"]),
    "get_events": (get_events, ["namespace"]),
    "get_resource": (get_resource, ["namespace", "kind", "name"]),
    "restart_deployment": (restart_deployment, ["namespace", "name"]),
    "scale_deployment": (scale_deployment, ["namespace", "name", "replicas"]),
    "rollback_deployment": (rollback_deployment, ["namespace", "name"]),
    "set_env": (set_env, ["namespace", "deployment", "key", "value"]),
    "patch_configmap_key": (patch_configmap_key, ["namespace", "configmap", "key", "value"]),
    "delete_pod": (delete_pod, ["namespace", "pod"]),
}

SHELL_ACTIONS = {
    "exec_kubectl_guarded": (exec_kubectl_guarded, ["cmd"]),
    "rollback_last_guarded_command": (rollback_last_guarded_command, []),
}

SURVEY_ACTIONS = {
    "survey": (survey, ["namespace"]),
}

CATALOGUE_V2_ACTIONS = {
    "patch_resource": (patch_resource, ["namespace", "kind", "name", "patch"]),
    "delete_resource": (delete_resource, ["namespace", "kind", "name"]),
    "exec_in_pod": (exec_in_pod, ["namespace", "pod", "command"]),
}

# Optional arguments each action accepts (v1 dropped these: the dispatcher only passed the required ones).
OPTIONAL_ARGS = {
    "get_logs": ["container", "tail", "previous"],
    "get_resource": ["output"],
    "set_env": ["container"],
    "patch_resource": ["patch_type"],
    "exec_in_pod": ["container"],
}

WRITE_ACTIONS = {
    "patch_resource",
    "delete_resource",
    "exec_in_pod",
    "restart_deployment",
    "scale_deployment",
    "rollback_deployment",
    "set_env",
    "patch_configmap_key",
    "delete_pod",
    "exec_kubectl_guarded",
}


def actions_for(action_space: str, *, survey_tool: bool = False, catalogue_v2: bool = False,
                health_sweep: bool = False, change_diff: bool = False, routing: bool = False) -> dict:
    """action_space: 'typed' or 'typed+shell'. The keyword switches add actions; all off = the v1 menu."""
    actions = {**TYPED_ACTIONS, **SHELL_ACTIONS} if action_space == "typed+shell" else dict(TYPED_ACTIONS)
    if survey_tool:
        actions.update(SURVEY_ACTIONS)
    if catalogue_v2:
        actions.update(CATALOGUE_V2_ACTIONS)
    if routing:
        actions.update(ROUTING_ACTIONS)
    if health_sweep or change_diff:
        from . import inspect_tools  # imported here: inspect_tools imports this module
        if health_sweep:
            actions["health_sweep"] = (inspect_tools.health_sweep, ["namespace"])
        if change_diff:
            actions["recent_changes"] = (inspect_tools.recent_changes, ["namespace"])
    return actions


# Backward-compatible default (typed-only) for anything importing ACTIONS directly.
ACTIONS = TYPED_ACTIONS
