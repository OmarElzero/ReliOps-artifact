#!/usr/bin/env python3
"""Apply the 3 required patches to a fresh SREGym clone, idempotently.

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


AGENT_NAMES = ("reliops_v1", "reliops_v2")


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
    new = 'if agent in {"stratus", "mini-sre", "reliops_v1", "reliops_v2"}:'
    if new in text:
        return False
    for old in ('if agent in {"stratus", "mini-sre", "reliops_v1"}:', 'if agent in {"stratus", "mini-sre"}:'):
        if text.count(old) == 1:
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            return True
    raise RuntimeError(f"{path}: expected the agent allowlist line not found — check experiments/testbed-setup.md §6b by hand")


def patch_container_runner(sregym_dir: Path) -> bool:
    path = sregym_dir / "sregym" / "service" / "container_runner.py"
    text = path.read_text(encoding="utf-8")
    # Every REACT_V1_* switch the driver reads must be on SREGym's env whitelist, or it silently never
    # reaches the agent container. Idempotent per variable, so an already-patched clone gets only the new ones.
    wanted = ["REACT_V1_ACTION_SPACE", "REACT_V1_LOG_OBS", "REACT_V1_LOG_OBS_MAX", "REACT_V1_BUDGET_AWARE",
              # react-v2 switches (agent/react_v2/features.py), the variant name and the soak wait
              "REACT_V1_TOKEN_LOG", "REACT_V1_EMPTY_SUBMIT_GUARD", "REACT_V1_OPTIONAL_ARGS", "REACT_V1_FAULT_EXISTS",
              "REACT_V1_SURVEY", "REACT_V1_LEDGER", "REACT_V1_SELFCHECK", "REACT_V1_SOAK", "REACT_V1_CATALOGUE_V2",
              "REACT_V1_K8S_KNOWLEDGE", "REACT_V1_SOAK_S", "REACT_V1_VARIANT"]
    missing = [v for v in wanted if f'"{v}"' not in text]
    if not missing:
        return False
    marker = '        # SREGym internal\n        "AGENT_MODEL_ID",\n'
    if marker not in text:
        raise RuntimeError(f"{path}: expected env-whitelist marker not found — check experiments/testbed-setup.md §6b by hand")
    replacement = marker + "".join(f'        "{v}",\n' for v in missing)
    path.write_text(text.replace(marker, replacement, 1), encoding="utf-8")
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
    }
    for name, changed in results.items():
        print(f"{'patched' if changed else 'already applied, skipped'}: {name}")


if __name__ == "__main__":
    main()
