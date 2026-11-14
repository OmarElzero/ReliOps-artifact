"""Generic inspection, verification and undo helpers for react-v2 (switches HEALTH_SWEEP, CHANGE_DIFF, OUTPUT_TRIM,
VERIFY_UNDO; docs/plan/14-plan-review-after-research.md).

Rule for everything in this file: no fault, problem or object name from our problem sets appears here, and no check is
chosen by us. HEALTH_SWEEP ports the rules of k8sgpt's 14 default ("core") analyzers as they are written upstream
(github.com/k8sgpt-ai/k8sgpt, pkg/analyzer/*.go, commit c2dc667, 3 Nov 2026); where k8sgpt has no rule, there is none
here either. CHANGE_DIFF lists every change in a time window, not a selection. OUTPUT_TRIM only merges repeated lines.
"""

from __future__ import annotations

import datetime as _dt
import difflib
import json
import re
import shlex
import subprocess

from .actions import ActionResult, _run

K8SGPT_SOURCE = "k8sgpt core analyzers (pkg/analyzer, commit c2dc667)"


# ---------------------------------------------------------------- kubectl helpers

def _kjson(args: list[str], timeout: int = 60) -> dict:
    r = _run(["kubectl", *args, "-o", "json"], timeout=timeout)
    if r.exit_code != 0:
        return {"items": [], "_error": (r.stderr or r.stdout)[:300]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"items": [], "_error": "unparseable kubectl output"}


def _items(kind: str, all_ns: bool = True, namespace: str | None = None) -> list[dict]:
    args = ["get", kind] + (["-A"] if all_ns else (["-n", namespace] if namespace else []))
    return _kjson(args).get("items", [])


def _md(o: dict) -> dict:
    return o.get("metadata", {}) or {}


def _key(o: dict) -> str:
    m = _md(o)
    return f"{m.get('namespace')}/{m.get('name')}" if m.get("namespace") else str(m.get("name"))


def _ts(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


class _Events:
    """Latest event per involved object, like k8sgpt's util.FetchLatestEvent."""

    def __init__(self, events: list[dict]):
        self.by_obj: dict[tuple, list[dict]] = {}
        for e in events:
            io = e.get("involvedObject", {}) or {}
            self.by_obj.setdefault((io.get("kind"), io.get("namespace"), io.get("name")), []).append(e)

    @staticmethod
    def _when(e: dict) -> str:
        return e.get("lastTimestamp") or e.get("eventTime") or e.get("firstTimestamp") or _md(e).get("creationTimestamp") or ""

    def latest(self, kind: str, o: dict) -> dict | None:
        evs = self.by_obj.get((kind, _md(o).get("namespace"), _md(o).get("name")), [])
        return max(evs, key=self._when) if evs else None

    def all_for(self, kind: str, ns: str, name: str) -> list[dict]:
        return self.by_obj.get((kind, ns, name), [])


# ---------------------------------------------------------------- HEALTH_SWEEP: k8sgpt core analyzer rules

_POD_ERROR_REASONS = {"CrashLoopBackOff", "ImagePullBackOff", "CreateContainerConfigError", "PreCreateHookError",
                      "CreateContainerError", "PreStartHookError", "RunContainerError", "ImageInspectError", "ErrImagePull",
                      "ErrImageNeverPull", "InvalidImageName"}                       # pod.go isErrorReason
_POD_EVENT_ERROR_REASONS = {"FailedCreatePodSandBox", "FailedMount"}                 # pod.go isEvtErrorReason
_NODE_TRUE = {"Ready", "AcceleratedHardwareReady", "ContainerRuntimeReady", "KernelReady", "NetworkingReady", "StorageReady"}
_NODE_FALSE = {"MemoryPressure", "DiskPressure", "PIDPressure", "NetworkUnavailable", "ContainerRuntimeUnhealthy",
               "CorruptDockerOverlay2", "CperHardwareErrorFatal", "DiskBadBlock", "FrequentContainerdRestart",
               "FrequentDockerRestart", "FrequentKubeletRestart", "FrequentUnregisterNetDevice", "KernelDeadlock",
               "KubeProxyUnhealthy", "ReadonlyFilesystem"}                            # node.go healthyNodeConditionStatus


def _pod_findings(pods: list[dict], ev: _Events) -> list[tuple]:
    out = []
    for p in pods:
        st, f = p.get("status", {}) or {}, []
        phase = st.get("phase", "")
        if phase == "Pending":
            for c in st.get("conditions", []) or []:
                if c.get("type") == "PodScheduled" and c.get("reason") == "Unschedulable" and c.get("message"):
                    f.append(c["message"])
                if c.get("type") == "PodScheduled" and c.get("reason") == "SchedulingGated":
                    f.append(c.get("message") or f"Pod {_key(p)} is in a SchedulingGated state and is blocked from scheduling due to non-empty scheduling gates")
        if st.get("reason") == "Evicted":
            f.append(st.get("message") or f"Pod {_md(p).get('name')} has been evicted")
        for cs in (st.get("initContainerStatuses") or []) + (st.get("containerStatuses") or []):
            state = cs.get("state", {}) or {}
            w, t = state.get("waiting"), state.get("terminated")
            if w:
                if w.get("reason") == "ContainerCreating" and phase == "Pending":
                    e = ev.latest("Pod", p)
                    if e and e.get("reason") in _POD_EVENT_ERROR_REASONS and e.get("message"):
                        f.append(e["message"])
                elif w.get("reason") == "CrashLoopBackOff" and (cs.get("lastState", {}) or {}).get("terminated"):
                    f.append(f"the last termination reason is {cs['lastState']['terminated'].get('reason')} container={cs.get('name')} pod={_md(p).get('name')}")
                elif w.get("reason") in _POD_ERROR_REASONS and w.get("message"):
                    f.append(w["message"])
            elif t:
                if t.get("exitCode", 0) != 0:
                    f.append(f"the termination reason is {t.get('reason') or 'Unknown'} exitCode={t.get('exitCode')} container={cs.get('name')} pod={_md(p).get('name')}")
            elif not cs.get("ready") and phase == "Running":
                e = ev.latest("Pod", p)
                if e and e.get("reason") == "Unhealthy" and e.get("message"):
                    f.append(e["message"])
        out += [("Pod", _key(p), x) for x in f]
    return out


def _deployment_findings(deps: list[dict]) -> list[tuple]:
    out = []
    for d in deps:
        spec, st, md = d.get("spec", {}) or {}, d.get("status", {}) or {}, _md(d)
        want, ready = spec.get("replicas"), st.get("readyReplicas", 0) or 0
        conds = {c.get("type"): c for c in st.get("conditions", []) or []}
        healthy_progress = (conds.get("Progressing", {}).get("status") == "True" and conds.get("Available", {}).get("status") == "True")
        if want is not None and want != ready and (st.get("observedGeneration", 0) or 0) >= (md.get("generation", 0) or 0) and not healthy_progress:
            if (st.get("replicas", 0) or 0) > want:
                out.append(("Deployment", _key(d), f"Deployment {_key(d)} has {want} replicas in spec but {st.get('replicas')} replicas in status because status field is not updated yet after scaling and {ready} replicas are available with status running"))
            else:
                out.append(("Deployment", _key(d), f"Deployment {_key(d)} has {want} replicas but {ready} are available with status running"))
        for c in st.get("conditions", []) or []:
            if c.get("type") == "Progressing" and c.get("status") == "False":
                out.append(("Deployment", _key(d), f"Deployment {_key(d)} has condition {c.get('type')}={c.get('status')}, reason {c.get('reason')}: {c.get('message')}"))
    return out


def _replicaset_findings(rss: list[dict]) -> list[tuple]:
    return [("ReplicaSet", _key(r), c.get("message", "")) for r in rss for c in (r.get("status", {}) or {}).get("conditions", []) or []
            if c.get("type") == "ReplicaFailure" and c.get("reason") == "FailedCreate"]


def _service_findings(endpoints: list[dict], services: list[dict], ev: _Events) -> list[tuple]:
    svc = {_key(s): s for s in services}
    out = []
    for ep in endpoints:
        md = _md(ep)
        if not ep.get("subsets"):
            if "control-plane.alpha.kubernetes.io/leader" in (md.get("annotations") or {}):
                continue
            s = svc.get(_key(ep))
            if s is None:
                continue
            for k, v in ((s.get("spec", {}) or {}).get("selector") or {}).items():
                out.append(("Service", _key(ep), f"Service has no endpoints, expected label {k}={v}"))
        else:
            pods = [f"{a['targetRef'].get('kind')}/{a['targetRef'].get('name')}" for sub in ep["subsets"] for a in sub.get("notReadyAddresses", []) or [] if a.get("targetRef")]
            count = sum(len(sub.get("notReadyAddresses", []) or []) for sub in ep["subsets"])
            if count:
                out.append(("Service", _key(ep), f"Service has not ready endpoints, pods: {pods}, expected {count}"))
        for e in ev.all_for("Endpoints", md.get("namespace"), md.get("name")):
            if e.get("type") != "Normal":
                out.append(("Service", _key(ep), f"Service {_key(ep)} has event {e.get('message')}"))
    return out


def _ingress_findings(ings: list[dict], services: list[dict], secret_names: set, classes: set) -> list[tuple]:
    svc = {_key(s) for s in services}
    out = []
    for i in ings:
        md, spec = _md(i), i.get("spec", {}) or {}
        ns, key = md.get("namespace"), _key(i)
        cls = spec.get("ingressClassName") or (md.get("annotations") or {}).get("kubernetes.io/ingress.class")
        if not cls:
            out.append(("Ingress", key, f"Ingress {key} does not specify an Ingress class."))
        elif cls not in classes:
            out.append(("Ingress", key, f"Ingress uses the ingress class {cls} which does not exist."))
        db = ((spec.get("defaultBackend") or {}).get("service") or {}).get("name")
        if db and f"{ns}/{db}" not in svc:
            out.append(("Ingress", key, f"Ingress uses the default backend service {ns}/{db} which does not exist."))
        for rule in spec.get("rules", []) or []:
            for path in ((rule.get("http") or {}).get("paths") or []):
                name = ((path.get("backend") or {}).get("service") or {}).get("name")
                if name and f"{ns}/{name}" not in svc:
                    out.append(("Ingress", key, f"Ingress uses the service {ns}/{name} which does not exist."))
        for tls in spec.get("tls", []) or []:
            if tls.get("secretName") and f"{ns}/{tls['secretName']}" not in secret_names:
                out.append(("Ingress", key, f"Ingress uses the secret {ns}/{tls['secretName']} as a TLS certificate which does not exist."))
    return out


def _pvc_findings(pvcs: list[dict], ev: _Events) -> list[tuple]:
    out = []
    for p in pvcs:
        if (p.get("status", {}) or {}).get("phase") == "Pending":
            e = ev.latest("PersistentVolumeClaim", p)
            if e and e.get("reason") in ("ProvisioningFailed", "FailedBinding") and e.get("message"):
                out.append(("PersistentVolumeClaim", _key(p), e["message"]))
    return out


def _statefulset_findings(stss: list[dict], services: list[dict], storage_classes: set, pods: list[dict], ev: _Events) -> list[tuple]:
    svc, pod_by = {_key(s) for s in services}, {_key(p): p for p in pods}
    out = []
    for s in stss:
        md, spec, st = _md(s), s.get("spec", {}) or {}, s.get("status", {}) or {}
        ns, key = md.get("namespace"), _key(s)
        if f"{ns}/{spec.get('serviceName')}" not in svc:
            out.append(("StatefulSet", key, f"StatefulSet uses the service {ns}/{spec.get('serviceName')} which does not exist."))
        for vct in spec.get("volumeClaimTemplates", []) or []:
            sc = (vct.get("spec") or {}).get("storageClassName")
            if sc and sc not in storage_classes:
                out.append(("StatefulSet", key, f"StatefulSet uses the storage class {sc} which does not exist."))
        want = spec.get("replicas")
        if want is not None and want != (st.get("availableReplicas", 0) or 0):
            start = ((spec.get("ordinals") or {}).get("start")) or 0
            for i in range(start, start + want):
                pod = pod_by.get(f"{ns}/{md.get('name')}-{i}")
                if pod is None:
                    if i == start:
                        e = ev.latest("StatefulSet", s)
                        if e and e.get("type") != "Normal":
                            out.append(("StatefulSet", key, e.get("message", "")))
                    break
                if (pod.get("status", {}) or {}).get("phase") != "Running":
                    out.append(("StatefulSet", key, f"Statefulset pod {_md(pod).get('name')} in the namespace {ns} is not in running state."))
    return out


def _daemonset_findings(dss: list[dict], secret_names: set) -> list[tuple]:
    out = []
    for d in dss:
        st, key, ns = d.get("status", {}) or {}, _key(d), _md(d).get("namespace")
        if (st.get("numberReady", 0) or 0) < (st.get("desiredNumberScheduled", 0) or 0):
            out.append(("DaemonSet", key, f"DaemonSet {key} has {st.get('numberReady', 0)} ready replicas out of {st.get('desiredNumberScheduled')} scheduled"))
        for ips in (((d.get("spec") or {}).get("template") or {}).get("spec") or {}).get("imagePullSecrets", []) or []:
            if f"{ns}/{ips.get('name')}" not in secret_names:
                out.append(("DaemonSet", key, f"DaemonSet {key} references non-existent ImagePullSecret {ips.get('name')}"))
    return out


def _job_findings(jobs: list[dict], ev: _Events) -> list[tuple]:
    out = []
    for j in jobs:
        spec, st, name = j.get("spec", {}) or {}, j.get("status", {}) or {}, _md(j).get("name")
        if spec.get("suspend"):
            out.append(("Job", _key(j), f"Job {name} is suspended"))
        conds = st.get("conditions", []) or []
        failed = next((c for c in conds if c.get("type") == "Failed" and c.get("status") == "True"), None)
        succeeded = any(c.get("type") in ("Complete", "SuccessCriteriaMet") and c.get("status") == "True" for c in conds)
        if (failed or (st.get("failed", 0) or 0) > 0) and not succeeded:
            text = (failed or {}).get("message") or f"Job {name} has failed"
            e = ev.latest("Job", j)
            if e and e.get("reason") in ("BackoffLimitExceeded", "DeadlineExceeded") and e.get("message"):
                text = e["message"]
            out.append(("Job", _key(j), text))
    return out


_CRON_DESCRIPTORS = {"@yearly", "@annually", "@monthly", "@weekly", "@daily", "@midnight", "@hourly"}


def _cron_ok(expr: str) -> bool:
    e = (expr or "").strip()
    if e in _CRON_DESCRIPTORS or e.startswith("@every "):
        return True
    return len(e.split()) == 5 and all(re.fullmatch(r"[\d*/,\-?A-Za-z]+", f) for f in e.split())


def _cronjob_findings(cjs: list[dict]) -> list[tuple]:
    out = []
    for c in cjs:
        spec, name = c.get("spec", {}) or {}, _md(c).get("name")
        if spec.get("suspend"):
            out.append(("CronJob", _key(c), f"CronJob {name} is suspended"))
        if not _cron_ok(spec.get("schedule", "")):
            out.append(("CronJob", _key(c), f"CronJob {name} has an invalid schedule: {spec.get('schedule')}"))
        if (spec.get("startingDeadlineSeconds") or 0) < 0:
            out.append(("CronJob", _key(c), f"CronJob {name} has a negative starting deadline"))
    return out


def _node_findings(nodes: list[dict]) -> list[tuple]:
    out = []
    for n in nodes:
        name = _md(n).get("name")
        for c in (n.get("status", {}) or {}).get("conditions", []) or []:
            t = c.get("type")
            if t == "EtcdIsVoter":
                continue
            healthy = "True" if t in _NODE_TRUE else ("False" if t in _NODE_FALSE else None)
            if healthy is None or c.get("status") != healthy:
                out.append(("Node", name, f"{name} has condition of type {t}, reason {c.get('reason')}: {c.get('message')}"))
    return out


def _webhook_findings(configs: list[dict], label: str, services: list[dict], pods: list[dict]) -> list[tuple]:
    svc = {_key(s): s for s in services}
    out = []
    for cfg in configs:
        for wh in cfg.get("webhooks", []) or []:
            ref = ((wh.get("clientConfig") or {}).get("service")) or None
            if not ref:
                continue
            key = f"{ref.get('namespace')}/{ref.get('name')}"
            s = svc.get(key)
            if s is None:
                out.append((f"{label}WebhookConfiguration", _md(cfg).get("name"), f"Service {ref.get('name')} not found as mapped to by {label} Webhook {wh.get('name')}"))
                continue
            sel = (s.get("spec", {}) or {}).get("selector") or {}
            matched = [p for p in pods if _md(p).get("namespace") == ref.get("namespace") and sel and all((_md(p).get("labels") or {}).get(k) == v for k, v in sel.items())]
            if not matched:
                out.append((f"{label}WebhookConfiguration", _md(cfg).get("name"), f"No active pods found within service {ref.get('name')} as mapped to by {label} Webhook {wh.get('name')}"))
            for p in matched:
                if (p.get("status", {}) or {}).get("phase") != "Running":
                    out.append((f"{label}WebhookConfiguration", _md(cfg).get("name"), f"{label} Webhook ({wh.get('name')}) is pointing to an inactive receiver pod ({_md(p).get('name')})"))
    return out


def _configmap_findings(cms: list[dict], pods: list[dict]) -> list[tuple]:
    used = set()
    for p in pods:
        ns, spec = _md(p).get("namespace"), p.get("spec", {}) or {}
        for v in spec.get("volumes", []) or []:
            if v.get("configMap"):
                used.add(f"{ns}/{v['configMap'].get('name')}")
            for src in ((v.get("projected") or {}).get("sources") or []):
                if src.get("configMap"):
                    used.add(f"{ns}/{src['configMap'].get('name')}")
        for c in (spec.get("containers", []) or []) + (spec.get("initContainers", []) or []):
            for e in c.get("envFrom", []) or []:
                if e.get("configMapRef"):
                    used.add(f"{ns}/{e['configMapRef'].get('name')}")
            for e in c.get("env", []) or []:
                ref = ((e.get("valueFrom") or {}).get("configMapKeyRef")) or {}
                if ref.get("name"):
                    used.add(f"{ns}/{ref['name']}")
    sidecar_labels = ("grafana_dashboard", "grafana_datasource", "prometheus_rule", "fluentd_config")
    out = []
    for cm in cms:
        md, key = _md(cm), _key(cm)
        labels, ann = md.get("labels") or {}, md.get("annotations") or {}
        if any(l in labels for l in sidecar_labels) or labels.get("k8sgpt.ai/dynamically-loaded") == "true":
            continue
        if ann.get("k8sgpt.ai/skip-usage-check") == "true":
            continue
        if key not in used:
            out.append(("ConfigMap", key, f"ConfigMap {md.get('name')} is not used by any pods in the namespace"))
        if not cm.get("data") and not cm.get("binaryData"):
            out.append(("ConfigMap", key, f"ConfigMap {md.get('name')} is empty"))
        size = sum(len(v or "") for v in (cm.get("data") or {}).values()) + sum(len(v or "") for v in (cm.get("binaryData") or {}).values())
        if size > 1024 * 1024:
            out.append(("ConfigMap", key, f"ConfigMap {md.get('name')} is larger than 1MB ({size} bytes)"))
    return out


def sweep_findings() -> list[tuple]:
    """(kind, namespace/name, text) for every finding of the ported k8sgpt core analyzers, across all namespaces."""
    pods, events = _items("pods"), _Events(_items("events"))
    services = _items("services")
    sec = _run(["kubectl", "get", "secrets", "-A", "-o", "custom-columns=NS:.metadata.namespace,NAME:.metadata.name", "--no-headers"])
    secret_names = {"/".join(l.split()[:2]) for l in sec.stdout.splitlines() if len(l.split()) >= 2}
    classes = {_md(c).get("name") for c in _items("ingressclasses", all_ns=False)}
    storage_classes = {_md(c).get("name") for c in _items("storageclasses", all_ns=False)}
    f = []
    f += _pod_findings(pods, events)
    f += _deployment_findings(_items("deployments"))
    f += _replicaset_findings(_items("replicasets"))
    f += _service_findings(_items("endpoints"), services, events)
    f += _ingress_findings(_items("ingresses"), services, secret_names, classes)
    f += _pvc_findings(_items("persistentvolumeclaims"), events)
    f += _statefulset_findings(_items("statefulsets"), services, storage_classes, pods, events)
    f += _daemonset_findings(_items("daemonsets"), secret_names)
    f += _job_findings(_items("jobs"), events)
    f += _cronjob_findings(_items("cronjobs"))
    f += _node_findings(_items("nodes", all_ns=False))
    f += _webhook_findings(_items("validatingwebhookconfigurations", all_ns=False), "Validating", services, pods)
    f += _webhook_findings(_items("mutatingwebhookconfigurations", all_ns=False), "Mutating", services, pods)
    f += _configmap_findings(_items("configmaps"), pods)
    return f


def format_sweep(findings: list[tuple], namespace: str, other_ns_cap: int = 25) -> str:
    """The application's namespace in full, nodes and webhooks, then other namespaces up to a cap."""
    if not findings:
        return f"No problems found by the standard checks ({K8SGPT_SOURCE}) in any namespace."
    def ns_of(key: str) -> str | None:
        return key.split("/", 1)[0] if "/" in key else None
    mine = [x for x in findings if ns_of(x[1]) == namespace]
    cluster = [x for x in findings if ns_of(x[1]) is None]
    other = [x for x in findings if ns_of(x[1]) not in (namespace, None)]
    lines = [f"Standard health checks ({K8SGPT_SOURCE}): {len(findings)} finding(s)."]
    for title, group, cap in ((f"namespace {namespace}", mine, None), ("cluster-scoped objects", cluster, None), ("other namespaces", other, other_ns_cap)):
        lines.append(f"## {title}: {len(group)}")
        for kind, key, text in (group if cap is None else group[:cap]):
            lines.append(f"- {kind} {key}: {text}")
        if cap is not None and len(group) > cap:
            lines.append(f"- ... {len(group) - cap} more in other namespaces")
    return "\n".join(lines)


def health_sweep(namespace: str) -> ActionResult:
    return ActionResult(format_sweep(sweep_findings(), namespace), "", 0)


# ---------------------------------------------------------------- CHANGE_DIFF: every change in a window

_NOISY_KINDS = {"events", "events.events.k8s.io", "endpoints", "endpointslices.discovery.k8s.io", "leases.coordination.k8s.io",
                "componentstatuses", "tokenreviews.authentication.k8s.io", "subjectaccessreviews.authorization.k8s.io",
                "selfsubjectreviews.authentication.k8s.io", "selfsubjectaccessreviews.authorization.k8s.io",
                "selfsubjectrulesreviews.authorization.k8s.io", "localsubjectaccessreviews.authorization.k8s.io",
                "bindings", "podtemplates"}


def _change_times(o: dict) -> list[tuple]:
    """(time, manager, operation) of every managedFields entry that is not a status update."""
    out = []
    for mf in _md(o).get("managedFields", []) or []:
        if mf.get("subresource"):
            continue
        t = _ts(mf.get("time"))
        if t:
            out.append((t, mf.get("manager", "?"), mf.get("operation", "?")))
    return sorted(out)


def _template_diffs(namespace: str, max_lines: int = 40) -> list[str]:
    rss = _items("replicasets", all_ns=False, namespace=namespace)
    by_dep: dict[str, list[dict]] = {}
    for r in rss:
        owner = next((o.get("name") for o in _md(r).get("ownerReferences", []) or [] if o.get("kind") == "Deployment"), None)
        if owner:
            by_dep.setdefault(owner, []).append(r)
    lines = []
    for dep, rs in sorted(by_dep.items()):
        rs = sorted(rs, key=lambda r: int((_md(r).get("annotations") or {}).get("deployment.kubernetes.io/revision", "0") or 0))
        if len(rs) < 2:
            continue
        def tmpl(r):
            t = json.loads(json.dumps((r.get("spec") or {}).get("template") or {}))
            (t.get("metadata", {}).get("labels") or {}).pop("pod-template-hash", None)
            return json.dumps(t, indent=1, sort_keys=True).splitlines()
        prev, cur = rs[-2], rs[-1]
        diff = list(difflib.unified_diff(tmpl(prev), tmpl(cur), lineterm="", n=1))[2:]
        rev = lambda r: (_md(r).get("annotations") or {}).get("deployment.kubernetes.io/revision")
        lines.append(f"### deployment/{dep}: revision {rev(prev)} -> {rev(cur)}")
        lines += diff[:max_lines] + ([f"... {len(diff) - max_lines} more diff lines"] if len(diff) > max_lines else [])
    return lines


def recent_changes(namespace: str) -> ActionResult:
    ns_obj = _kjson(["get", "namespace", namespace])
    start = _ts(_md(ns_obj).get("creationTimestamp"))
    window_start = (start - _dt.timedelta(minutes=30)) if start else None
    now = _dt.datetime.now(_dt.timezone.utc)
    kinds_ns = [k for k in _run(["kubectl", "api-resources", "--verbs=list", "--namespaced=true", "-o", "name"]).stdout.split() if k not in _NOISY_KINDS]
    kinds_cl = [k for k in _run(["kubectl", "api-resources", "--verbs=list", "--namespaced=false", "-o", "name"]).stdout.split() if k not in _NOISY_KINDS]
    objs = []
    if kinds_ns:
        objs += [(o, True) for o in _kjson(["get", ",".join(kinds_ns), "-n", namespace], timeout=90).get("items", [])]
    if kinds_cl:
        objs += [(o, False) for o in _kjson(["get", ",".join(kinds_cl)], timeout=90).get("items", [])]
    modified, created = [], {}
    for o, _ in objs:
        md = _md(o)
        created_at = _ts(md.get("creationTimestamp"))
        changes = _change_times(o)
        label = f"{o.get('kind')}/{md.get('name')}" + (f" (ns {md['namespace']})" if md.get("namespace") else "")
        if created_at and (window_start is None or created_at >= window_start):
            created.setdefault(o.get("kind"), []).append(md.get("name"))
        later = [c for c in changes if created_at and (c[0] - created_at).total_seconds() > 10 and (window_start is None or c[0] >= window_start)]
        if later:
            t, mgr, op = later[-1]
            modified.append((t, f"- {label}: created {_ago(created_at, now)}, last changed {_ago(t, now)} by {mgr} ({op}), {len(later)} change(s) after creation"))
    lines = [f"Changes since {window_start.isoformat() if window_start else 'the start'} (30 min before namespace {namespace} was created), "
             f"from object metadata; status updates are not counted. Every change is listed, not a selection."]
    lines.append(f"## Objects changed after they were created, newest first: {len(modified)}")
    lines += [x for _, x in sorted(modified, key=lambda x: x[0], reverse=True)[:60]]
    lines.append(f"## Objects created in the window, by kind: {sum(len(v) for v in created.values())}")
    for kind, names in sorted(created.items()):
        lines.append(f"- {kind} ({len(names)}): {', '.join(sorted(names)[:15])}{' ...' if len(names) > 15 else ''}")
    diffs = _template_diffs(namespace)
    lines.append(f"## Pod-template differences between each Deployment's previous and current revision: {sum(1 for l in diffs if l.startswith('### '))}")
    lines += diffs
    return ActionResult("\n".join(lines), "", 0)


def _ago(t: _dt.datetime | None, now: _dt.datetime) -> str:
    if not t:
        return "?"
    s = int((now - t).total_seconds())
    return f"{s // 60}m{s % 60:02d}s ago" if s >= 60 else f"{s}s ago"


# ---------------------------------------------------------------- OUTPUT_TRIM

_VARIABLE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b0x[0-9a-f]+\b|\d+", re.IGNORECASE)


def trim_output(text: str, min_lines: int = 40, head: int = 100, tail: int = 50) -> str:
    """Merge lines that differ only in numbers or ids (kept once, with a count), then keep head and tail. Short outputs
    are returned unchanged."""
    lines = text.splitlines()
    if len(lines) <= min_lines:
        return text
    order, count, first = [], {}, {}
    for line in lines:
        k = _VARIABLE.sub("#", line.strip())
        if k not in count:
            order.append(k); count[k] = 0; first[k] = line
        count[k] += 1
    merged = [first[k] + (f"   [x{count[k]} similar lines]" if count[k] > 1 else "") for k in order]
    note = f"[output trimmed: {len(lines)} lines, {len(lines) - len(merged)} repeats merged"
    if len(merged) > head + tail:
        merged = merged[:head] + [f"[... {len(merged) - head - tail} distinct lines omitted ...]"] + merged[-tail:]
        note += ", middle omitted"
    return note + "]\n" + "\n".join(merged)


# ---------------------------------------------------------------- VERIFY_UNDO: what a write touches, snapshots, restore

_VALUE_FLAGS = {"-n", "--namespace", "-p", "--patch", "--type", "-l", "--selector", "-c", "--container", "-o", "--output",
                "-f", "--filename", "--field-manager", "--timeout", "--grace-period", "--replicas", "--image", "--from-literal",
                "--from-file", "--overrides", "--context", "-k", "--kustomize", "--to-revision", "--patch-file", "--subresource"}
_RESOURCE_VERBS = {"patch", "scale", "label", "annotate", "edit", "delete", "autoscale", "expose", "taint", "cordon", "uncordon", "drain"}
_SUB_VERBS = {"set", "rollout"}


def _heredoc_manifests(cmd: str) -> list[tuple]:
    m = re.search(r"<<-?\s*'?\"?(\w+)'?\"?\s*\n(.*?)\n\s*\1\s*$", cmd, re.S)
    body = m.group(2) if m else ""
    out = []
    for doc in re.split(r"\n---\s*\n", body):
        kind = re.search(r"^kind:\s*(\S+)", doc, re.M)
        meta = re.search(r"^metadata:\s*\n((?:[ \t]+.*\n?)+)", doc, re.M)
        name = re.search(r"^\s+name:\s*(\S+)", meta.group(1), re.M) if meta else None
        ns = re.search(r"^\s+namespace:\s*(\S+)", meta.group(1), re.M) if meta else None
        if kind and name:
            out.append((kind.group(1), name.group(1).strip("'\""), ns.group(1).strip("'\"") if ns else None))
    return out


def write_targets(action: str, args: dict, namespace: str) -> list[tuple]:
    """(kind, name, namespace or None) of the objects a write action changes. Pods and in-container commands have no
    restorable object and give nothing."""
    a = args or {}
    ns = a.get("namespace") or namespace
    typed = {"restart_deployment": ("deployment", "name"), "scale_deployment": ("deployment", "name"),
             "rollback_deployment": ("deployment", "name"), "set_env": ("deployment", "deployment"),
             "patch_configmap_key": ("configmap", "configmap")}
    if action in typed:
        kind, field = typed[action]
        return [(kind, str(a.get(field)), ns)] if a.get(field) else []
    if action in ("patch_resource", "delete_resource"):
        return [(str(a.get("kind")), str(a.get("name")), ns)] if a.get("kind") and a.get("name") else []
    if action != "exec_kubectl_guarded":
        return []
    cmd = str(a.get("cmd") or "")
    first = cmd.split("<<", 1)[0]
    try:
        tok = shlex.split(first)
    except ValueError:
        return []
    if len(tok) < 2 or tok[0] != "kubectl":
        return []
    cmd_ns = None
    for i, t in enumerate(tok):
        if t in ("-n", "--namespace") and i + 1 < len(tok):
            cmd_ns = tok[i + 1]
        elif t.startswith("--namespace="):
            cmd_ns = t.split("=", 1)[1]
    verb = tok[1]
    if verb in ("apply", "create", "replace"):
        return [(k, n, mns or cmd_ns or ns) for k, n, mns in _heredoc_manifests(cmd)] if "<<" in cmd else []
    rest = tok[2:]
    if verb in _SUB_VERBS:
        rest = rest[1:]
    elif verb not in _RESOURCE_VERBS:
        return []
    positional, skip = [], False
    for t in rest:
        if skip:
            skip = False; continue
        if t.startswith("-"):
            skip = t in _VALUE_FLAGS
            continue
        positional.append(t)
    if not positional:
        return []
    if "/" in positional[0]:
        return [(p.split("/", 1)[0], p.split("/", 1)[1], cmd_ns or ns) for p in positional if "/" in p]
    kind = positional[0]
    if "," in kind:
        return []
    if verb in ("cordon", "uncordon", "drain"):
        return [("node", positional[0], None)]
    return [(kind, n, cmd_ns or ns) for n in positional[1:]]


_UNRESTORABLE = {"pod", "pods", "po", "event", "events"}
_DROP_META = ("resourceVersion", "uid", "creationTimestamp", "managedFields", "generation", "selfLink", "deletionTimestamp")


def snapshot(kind: str, name: str, ns: str | None) -> dict | None:
    """The object as it is now, ready to restore, or {'absent': True} when it does not exist. None for kinds with no
    restorable state."""
    if kind.lower() in _UNRESTORABLE:
        return None
    args = ["kubectl", "get", kind, name, "-o", "json"] + (["-n", ns] if ns else [])
    r = _run(args)
    if r.exit_code != 0:
        return {"absent": True, "kind": kind, "name": name, "namespace": ns} if "NotFound" in (r.stderr or "") else None
    try:
        obj = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None
    obj.pop("status", None)
    for k in _DROP_META:
        obj.get("metadata", {}).pop(k, None)
    (obj.get("metadata", {}).get("annotations") or {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    return {"absent": False, "kind": kind, "name": name, "namespace": ns, "object": obj}


def _stdin_run(args: list[str], data: str, timeout: int = 60) -> ActionResult:
    try:
        p = subprocess.run(args, input=data, capture_output=True, text=True, timeout=timeout)
        return ActionResult(p.stdout, p.stderr, p.returncode)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return ActionResult("", str(e), 1)


def restore(snap: dict) -> str:
    """Put one object back the way the snapshot saw it. Returns a one-line report."""
    kind, name, ns = snap["kind"], snap["name"], snap.get("namespace")
    nsargs = ["-n", ns] if ns else []
    exists = _run(["kubectl", "get", kind, name, "-o", "name", *nsargs]).exit_code == 0
    if snap.get("absent"):
        if not exists:
            return f"{kind}/{name}: was absent, still absent"
        r = _run(["kubectl", "delete", kind, name, *nsargs])
        return f"{kind}/{name}: created by the fix, deleted again ({'ok' if r.exit_code == 0 else (r.stderr or '').strip()[:120]})"
    body = json.dumps(snap["object"])
    r = _stdin_run(["kubectl", "replace" if exists else "create", "-f", "-"], body)
    return f"{kind}/{name}: {'restored' if exists else 'recreated (its data, if any, is not recovered)'} ({'ok' if r.exit_code == 0 else (r.stderr or '').strip()[:120]})"


_HASHY = re.compile(r"-[a-z0-9]{8,10}(-[a-z0-9]{5})?$|-[a-z0-9]{5}$")


def scoped(findings: list[tuple], namespace: str) -> list[tuple]:
    """Only the application's namespace and cluster-scoped objects: other namespaces change for reasons unrelated to a fix."""
    return [f for f in findings if f[1].startswith(namespace + "/") or "/" not in f[1]]


def finding_keys(findings: list[tuple]) -> set:
    """Findings keyed by kind and owning object, so a replacement pod with a new name counts as the same problem."""
    return {(kind, _HASHY.sub("", key)) for kind, key, _ in findings}


def verdict(before: set, after: set) -> str:
    """worse: a new problem appeared. no_effect: problems existed and none went away. partial: some went away, some
    remain. clear: none remain. unknown: no problem was visible before or after (the checks cannot judge this fix)."""
    if after - before:
        return "worse"
    if before and after == before:
        return "no_effect"
    if before and after:
        return "partial"
    if before and not after:
        return "clear"
    return "unknown"


# ---- TLS secret reader (C-021, with PROC_V2): read-only, standard library only -------------------------------------
# kubectl alone cannot show a certificate's dates (it can only print the base64 PEM) and the agent image has no openssl,
# so this decodes the X.509 DER directly: subject and issuer common names, DNS names, validity window. The private key is
# never printed.

_CN_OID = b"\x55\x04\x03"        # 2.5.4.3 commonName
_SAN_OID = b"\x55\x1d\x11"       # 2.5.29.17 subjectAltName


def _tlv(b: bytes, i: int) -> tuple[int, int, int]:
    """(tag, content start, content end) of the DER element at offset i."""
    tag, ln = b[i], b[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(b[i:i + n], "big")
        i += n
    return tag, i, i + ln


def _children(b: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    out, i = [], start
    while i < end:
        t, s, e = _tlv(b, i)
        out.append((t, s, e))
        i = e
    return out


def _der_time(tag: int, raw: bytes) -> _dt.datetime:
    s = raw.decode("ascii").rstrip("Z")
    if tag == 0x17:                                   # UTCTime YYMMDDHHMM[SS]
        yy = int(s[:2])
        s = ("19" if yy >= 50 else "20") + s
    fmt = "%Y%m%d%H%M%S" if len(s) >= 14 else "%Y%m%d%H%M"
    return _dt.datetime.strptime(s[:14] if len(s) >= 14 else s[:12], fmt).replace(tzinfo=_dt.timezone.utc)


def _common_name(b: bytes, s: int, e: int) -> str:
    for _, rs, re_ in _children(b, s, e):                 # SET
        for _, as_, ae in _children(b, rs, re_):          # SEQUENCE {OID, value}
            parts = _children(b, as_, ae)
            if len(parts) >= 2 and parts[0][0] == 0x06 and b[parts[0][1]:parts[0][2]] == _CN_OID:
                return b[parts[1][1]:parts[1][2]].decode("utf-8", "replace")
    return ""


def _dns_names(b: bytes, s: int, e: int) -> list[str]:
    names: list[str] = []
    for _, xs, xe in _children(b, s, e):                  # [3] -> SEQUENCE of extensions
        for _, es, ee in _children(b, xs, xe):
            parts = _children(b, es, ee)
            if parts and parts[0][0] == 0x06 and b[parts[0][1]:parts[0][2]] == _SAN_OID:
                t, os_, oe = parts[-1]                    # OCTET STRING holding GeneralNames
                if t == 0x04:
                    _, gs, ge = _tlv(b, os_)
                    names += [b[ns:ne].decode("ascii", "replace") for nt, ns, ne in _children(b, gs, ge) if nt == 0x82]
    return names


def parse_certificate(der: bytes) -> dict:
    """subject_cn, issuer_cn, dns_names, not_before, not_after of one DER certificate."""
    _, cs, ce = _tlv(der, 0)
    _, ts, te = _children(der, cs, ce)[0]                 # tbsCertificate
    tbs = _children(der, ts, te)
    if tbs and tbs[0][0] == 0xA0:                         # explicit version
        tbs = tbs[1:]
    issuer, validity, subject = tbs[2], tbs[3], tbs[4]
    nb, na = _children(der, validity[1], validity[2])[:2]
    ext = next((x for x in tbs[5:] if x[0] == 0xA3), None)
    return {
        "subject_cn": _common_name(der, subject[1], subject[2]),
        "issuer_cn": _common_name(der, issuer[1], issuer[2]),
        "dns_names": _dns_names(der, ext[1], ext[2]) if ext else [],
        "not_before": _der_time(nb[0], der[nb[1]:nb[2]]),
        "not_after": _der_time(na[0], der[na[1]:na[2]]),
    }


def describe_pem(pem: str, now: _dt.datetime | None = None) -> str:
    import base64
    now = now or _dt.datetime.now(_dt.timezone.utc)
    blocks = re.findall(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", pem, re.S)
    if not blocks:
        return "no certificate found in the data"
    lines = []
    for k, blk in enumerate(blocks, 1):
        try:
            c = parse_certificate(base64.b64decode("".join(blk.split())))
        except Exception as e:  # noqa: BLE001  a malformed certificate is itself the observation
            lines.append(f"certificate {k} of {len(blocks)}: could not be decoded ({type(e).__name__})")
            continue
        if now > c["not_after"]:
            state = f"EXPIRED {(now - c['not_after']).days} day(s) ago"
        elif now < c["not_before"]:
            state = f"NOT YET VALID (starts in {(c['not_before'] - now).days} day(s))"
        else:
            state = f"valid, expires in {(c['not_after'] - now).days} day(s)"
        lines += [f"certificate {k} of {len(blocks)}:",
                  f"  subject CN: {c['subject_cn'] or '-'}",
                  f"  issuer CN:  {c['issuer_cn'] or '-'}" + ("  (self-signed)" if c["issuer_cn"] and c["issuer_cn"] == c["subject_cn"] else ""),
                  f"  DNS names:  {', '.join(c['dns_names']) or '-'}",
                  f"  not before: {c['not_before']:%Y-%m-%d %H:%M} UTC",
                  f"  not after:  {c['not_after']:%Y-%m-%d %H:%M} UTC",
                  f"  now:        {now:%Y-%m-%d %H:%M} UTC",
                  f"  state:      {state}"]
    return "\n".join(lines)


def inspect_tls_secret(namespace: str, name: str) -> ActionResult:
    """Read-only: the certificates in a Secret (tls.crt, and ca.crt if present) with names and validity dates."""
    import base64
    r = _run(["kubectl", "get", "secret", name, "-n", namespace, "-o", "json"])
    if r.exit_code != 0:
        return r
    try:
        obj = json.loads(r.stdout)
    except ValueError:
        return ActionResult("", "could not read the Secret as JSON", 1)
    data = obj.get("data") or {}
    out = [f"secret {namespace}/{name}, type {obj.get('type') or '-'}, keys: {', '.join(sorted(data)) or 'none'}"]
    found = False
    for key in ("tls.crt", "ca.crt"):
        if key in data:
            found = True
            try:
                pem = base64.b64decode(data[key]).decode("ascii", "replace")
            except (ValueError, TypeError):
                out.append(f"{key}: not valid base64")
                continue
            out.append(f"{key}:\n{describe_pem(pem)}")
    if not found:
        out.append("no tls.crt or ca.crt key in this Secret")
    return ActionResult("\n".join(out) + "\n", "", 0)
