#!/usr/bin/env python3
"""Apply the 4 required patches to a fresh SREGym clone, idempotently.

What each one does: REPRODUCE.md in the published artifact (team copy: `experiments/testbed-setup.md` §6b).
Safe to re-run: each patch checks whether its marker is already present before touching anything,
so running this twice (or against an already-patched clone) is a no-op, not a double-patch.

Usage: python3 scripts/apply_sregym_patches.py [path-to-sregym-clone]
Default clone path: external/envs/sregym (relative to the repo root this script lives in).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


AGENT_NAMES = ("reliops_v1", "reliops_v2", "reliops_v3")


def patch_agents_yaml(sregym_dir: Path) -> bool:
    path = sregym_dir / "agents.yaml"
    text = path.read_text(encoding="utf-8")
    missing = [n for n in AGENT_NAMES if f"  - name: {n}\n" not in text]
    if not missing:
        return False
    marker = "  - name: stratus\n"
    if marker not in text:
        raise RuntimeError(f"{path}: expected marker '  - name: stratus' not found — SREGym's file layout changed, check experiments/testbed-setup.md §6b by hand")
    entries = "".join(
        f"  - name: {n}\n"
        f"    kickoff_command: python -m clients.{n}.driver\n"
        "    kickoff_workdir: .\n"
        "    kickoff_env: null\n"
        "    install_script: null\n"
        "    agent_version: null\n"
        for n in missing
    )
    path.write_text(text.replace(marker, entries + marker, 1), encoding="utf-8")
    return True


def patch_provider_endpoints(sregym_dir: Path) -> bool:
    path = sregym_dir / "sregym" / "service" / "provider_endpoints.py"
    text = path.read_text(encoding="utf-8")
    new = 'if agent in {"stratus", "mini-sre", "reliops_v1", "reliops_v2", "reliops_v3"}:'
    if new in text:
        return False
    for old in ('if agent in {"stratus", "mini-sre", "reliops_v1", "reliops_v2"}:', 'if agent in {"stratus", "mini-sre", "reliops_v1"}:',
                'if agent in {"stratus", "mini-sre"}:'):
        if text.count(old) == 1:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            return True
    raise RuntimeError(f"{path}: expected the agent allowlist line not found — check experiments/testbed-setup.md §6b by hand")


def forwarded_env_names() -> list[str]:
    """Every REACT_V1_* name the agents read. The switch names come from agent/react_v2/features.py itself, so a new switch
    can never be left off the whitelist (round 2's switches were, before this)."""
    import importlib.util
    # react_v3's switch list is a superset of react_v2's (plan 22), so it covers both agents.
    spec = importlib.util.spec_from_file_location("_v3_features", REPO_ROOT / "agent" / "react_v3_r4" / "features.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fixed = ["REACT_V1_ACTION_SPACE", "REACT_V1_LOG_OBS", "REACT_V1_LOG_OBS_MAX", "REACT_V1_BUDGET_AWARE", "REACT_V1_SOAK_S",
             "REACT_V1_VARIANT", "REACT_V1_MAX_MODEL_FAILURES", "REACT_V1_RETRY_WAIT_S", "REACT_V1_VERIFY_WAIT_S",
             "REACT_V1_MAX_UNDO_ROUNDS", "REACT_V1_EVIDENCE_MODE", "REACT_V1_T1_WAIT_S", "REACT_V1_T1_MAX_ROUNDS", "REACT_V1_FINAL_MODEL"]
    return fixed + [f"REACT_V1_{n}" for n in mod.SWITCHES if f"REACT_V1_{n}" not in fixed]


def patch_container_runner(sregym_dir: Path) -> bool:
    path = sregym_dir / "sregym" / "service" / "container_runner.py"
    text = path.read_text(encoding="utf-8")
    # Every REACT_V1_* switch the driver reads must be on SREGym's env whitelist, or it silently never
    # reaches the agent container. Idempotent per variable, so an already-patched clone gets only the new ones.
    wanted = forwarded_env_names()
    missing = [v for v in wanted if f'"{v}"' not in text]
    if not missing:
        return False
    marker = '        # SREGym internal\n        "AGENT_MODEL_ID",\n'
    if marker not in text:
        raise RuntimeError(f"{path}: expected env-whitelist marker not found — check experiments/testbed-setup.md §6b by hand")
    replacement = marker + "".join(f'        "{v}",\n' for v in missing)
    path.write_text(text.replace(marker, replacement, 1), encoding="utf-8")
    return True


def patch_helm4_list(sregym_dir: Path) -> bool:
    """SREGym's ingress-nginx check runs `helm list --all --namespace ...`. Helm 4 removed `--all` (it lists every release by
    default), so on Helm 4 every problem that deploys ingress-nginx (ingress_misroute, expired_tls_hotel_reservation, ...) ends as
    'The app failed to deploy: unknown flag: --all' (seen 5 Nov 2026). The same file works on Helm 3 without the flag in the
    normal case (Helm 3 then hides only releases stuck in pending or uninstalling states). Helm 4 is needed anyway for
    `helm upgrade --server-side` (social-network faults). Source for the removal: helm/helm issue #31784 (secondary, not the release notes)."""
    path = sregym_dir / "sregym" / "observer" / "ingress_nginx.py"
    text = path.read_text(encoding="utf-8")
    old = '                        "list",\n                        "--all",\n                        "--namespace",\n'
    new = '                        "list",\n                        "--namespace",\n'
    if old not in text:
        if '"list",\n                        "--namespace",' in text:
            return False
        raise RuntimeError(f"{path}: expected `helm list --all` block not found — SREGym changed, check by hand")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def main() -> None:
    sregym_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO_ROOT / "external" / "envs" / "sregym"
    if not sregym_dir.is_dir():
        print(f"SREGym clone not found at {sregym_dir} — clone it first (REPRODUCE.md)", file=sys.stderr)
        sys.exit(1)

    results = {
        "agents.yaml (register reliops_v1 and reliops_v2)": patch_agents_yaml(sregym_dir),
        "provider_endpoints.py (egress allowlist)": patch_provider_endpoints(sregym_dir),
        "container_runner.py (forward REACT_V1_* env switches)": patch_container_runner(sregym_dir),
        "observer/ingress_nginx.py (no `helm list --all`, Helm 4 removed it)": patch_helm4_list(sregym_dir),
    }
    for name, changed in results.items():
        print(f"{'patched' if changed else 'already applied, skipped'}: {name}")


if __name__ == "__main__":
    main()
