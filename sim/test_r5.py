"""r5 (plan 27) unit tests: D1_PREDICT, FIX_FAMILIES (with T1 v2), ADAPTIVE_WAIT, 3 TNR rounds.
Run: /root/reliops-lab-workdir/ReliOps/external/envs/sregym/.venv/bin/python sim/test_r5.py"""
import json, os, sys, time
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["REACT_V1_T1_WAIT_S"] = "0"; os.environ["REACT_V1_T1_REBASE_WAIT_S"] = "0"
import run_sim as RS
def J(a, args=None): return "t\n```json\n" + json.dumps({"action": a, "args": args or {}}) + "\n```"


class R:
    status_code = 200
    def __init__(self, stage): self.stage = stage
    def json(self): return {"stage": self.stage}


def run(switches, stage, script, sweeps=None, extra=()):
    drv, actions_mod, prompts, pkg = RS.load_agent(switches, "agent/react_v3_r5",
                                                   {"REACT_V1_T1_WAIT_S": "0", "REACT_V1_T1_REBASE_WAIT_S": "0"})
    try:
        acts = {n: ((lambda n: (lambda **kw: actions_mod.ActionResult(f"ok {n}", "", 0)))(n), req)
                for n, (fn, req) in actions_mod.actions_for("typed+shell").items()}
        class B:
            def complete(self, messages, step_dir=None): return RS.Reply(script.pop(0) if script else J("submit", {"solution": "x"}))
        rec, posted = [], []
        class T:
            def write(self, r): rec.append(r)
        sw = list(sweeps or [])
        patches = [mock.patch.object(drv.requests, "post", side_effect=lambda url, json=None, timeout=None: (posted.append(json), R(stage))[1]),
                   mock.patch.object(drv, "conductor_status", return_value={"stage": stage}),
                   mock.patch.object(drv.requests, "get", side_effect=RuntimeError("no conductor")),
                   mock.patch.object(drv.inspect_tools, "sweep_findings", side_effect=lambda: sw.pop(0) if sw else []),
                   mock.patch.object(drv.inspect_tools, "write_targets", return_value=[("Deployment", "app", "ns")]),
                   mock.patch.object(drv.inspect_tools, "snapshot", return_value={"kind": "Deployment"}),
                   mock.patch.object(drv.inspect_tools, "restore", return_value="restored Deployment/app"),
                   mock.patch.object(drv.inspect_tools, "wait_rollouts", return_value=(40, True))] + list(extra)
        for p in patches: p.start()
        try:
            drv._procedures_loaded[:] = ["config"]
            s = drv.Session(); s.open({"role": "system", "content": "sys"}, "go")
            out = drv.run_stage(B(), s, T(), "ns", acts, stage=stage, run_ends=time.monotonic() + 60)
        finally:
            for p in patches: p.stop()
        return drv, out, rec, posted, s
    finally:
        import shutil; shutil.rmtree(pkg, ignore_errors=True)


# 1) D1: submit -> asked -> read check -> result shown -> corrected submit goes to the conductor
drv, out, rec, posted, s = run(["D1_PREDICT", "FLAT_ARGS"], "diagnosis",
    [J("submit", {"solution": "first guess"}), J("get_pod_status", {"namespace": "ns"}), J("submit", {"solution": "corrected"})])
ev = [r["event"] for r in rec if r.get("type") == "feature" and r.get("name") == "D1_PREDICT"]
print("D1 events", ev, "| submitted", [p["solution"] for p in posted if p])
assert ev == ["asked", "checked"] and [p["solution"] for p in posted if p][-1] == "corrected" and out.termination_reason == "submitted"
assert any("Result of the check for your prediction" in str(m.get("content")) for m in s.messages)
# 1b) D1 skipped: the model submits again without a check read
drv, out, rec, posted, s = run(["D1_PREDICT", "FLAT_ARGS"], "diagnosis",
    [J("submit", {"solution": "a"}), J("submit", {"solution": "a"})])
ev = [r["event"] for r in rec if r.get("type") == "feature" and r.get("name") == "D1_PREDICT"]
assert ev == ["asked", "skipped"] and out.termination_reason == "submitted"
print("D1: PASS")

# 2) FIX_FAMILIES + T1 v2 + ADAPTIVE_WAIT: fix 1 no effect -> restore message names the config families; 3 rounds allowed
W = "exec_kubectl_guarded"
A = ("Pod", "ns/app-5f6d7c8b9d-abcde", "CrashLoopBackOff")
drv, out, rec, posted, s = run(["TRANSACTIONAL_FIX", "T1_DRIVER", "FIX_FAMILIES", "ADAPTIVE_WAIT", "FLAT_ARGS"], "mitigation",
    [J(W, {"cmd": "kubectl set env deploy/app X=1 -n ns"}), J("submit", {"solution": ""}),
     J(W, {"cmd": "kubectl apply -f cm.yaml"}), J("submit", {"solution": ""}),
     J(W, {"cmd": "kubectl get pods -n ns"}), J("submit", {"solution": ""})],
    sweeps=[[A], [A], [A], []])
assert drv.T1_MAX_ROUNDS == 3
fam = [m for m in s.messages if "Fix families for the config procedure" in str(m.get("content"))]
waits = [r for r in rec if r.get("name") == "ADAPTIVE_WAIT"]
verd = [r.get("verdict") for r in rec if r.get("name") == "T1_DRIVER" and r.get("event") == "verdict"]
print("verdicts", verd, "| family messages", len(fam), "| adaptive waits", len(waits), "|", out.termination_reason)
assert verd == ["no_effect", "clear"] and len(fam) == 1 and "family 2 or later" in str(fam[0]["content"]) and waits
assert out.termination_reason == "submitted"
print("FIX_FAMILIES + ADAPTIVE_WAIT: PASS")

# 3) wait_rollouts on its own: unsettled, then settled
drv, actions_mod, prompts, pkg = RS.load_agent(["FLAT_ARGS"], "agent/react_v3_r5", {})
try:
    it = drv.inspect_tools
    dep = lambda upd, av: {"kind": "Deployment", "metadata": {"generation": 2}, "spec": {"replicas": 1},
                           "status": {"observedGeneration": 2, "updatedReplicas": upd, "availableReplicas": av, "replicas": 1}}
    seq = [json.dumps({"items": [dep(0, 0)]}), json.dumps({"items": [dep(1, 0)]}), json.dumps({"items": [dep(1, 1)]})]
    with mock.patch.object(it, "_run", side_effect=lambda a: actions_mod.ActionResult(seq.pop(0) if seq else seq_last, "", 0)):
        seq_last = json.dumps({"items": [dep(1, 1)]})
        waited, ok = it.wait_rollouts("ns", 30, 180, 10, sleep=lambda s: None)
    print("wait_rollouts ->", waited, ok); assert ok and waited == 50
    with mock.patch.object(it, "_run", return_value=actions_mod.ActionResult(json.dumps({"items": [dep(0, 0)]}), "", 0)):
        waited, ok = it.wait_rollouts("ns", 30, 60, 10, sleep=lambda s: None)
    print("wait_rollouts capped ->", waited, ok); assert not ok and waited == 60
finally:
    import shutil; shutil.rmtree(pkg, ignore_errors=True)
print("r5 tests: PASS")
