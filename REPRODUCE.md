# Running the agents on SREGym

What the team used, so a run can be repeated. A live run takes about nine minutes per problem and needs a model API
key. Results vary from run to run; that is the subject of the paper.

## Machine

Linux or Windows with WSL2, Docker, and about 10 GB of memory free for one `kind` cluster. The team used five laptops
and one cloud machine (8 vCPUs, 32 GB).

## Tools

| Tool | Version used |
|---|---|
| kind | v0.30.0 |
| Helm | 4.0.2 (Helm 4 is needed: SREGym injects the social-network faults with `helm upgrade --server-side`) |
| kubectl | current stable |
| uv | current |

## SREGym

1. Clone SREGym with its submodule at the pinned commit:
   ```
   git clone https://github.com/SREGym/SREGym.git sregym
   cd sregym && git checkout d19d6f55589f154374cd5d8aff70d5c37c30275e && git submodule update --init --recursive
   ```
2. Apply the four patches (each is idempotent): `python3 scripts/apply_sregym_patches.py <path-to-sregym>`.
   They register our agents (`reliops_v2`, `reliops_v3`, `reliops_v5`), allow the agent's model hosts through SREGym's
   egress allowlist, forward the agent's `REACT_V1_*` switches into its container, and drop `helm list --all`, which
   Helm 4 removed.
3. Copy the agent code into SREGym's `clients/` folder (a symlink does not work, because Docker builds from the SREGym
   folder): `agent/react_v2` -> `clients/reliops_v2`, `agent/react_v3_r4` -> `clients/reliops_v3`,
   `agent/react_v3_r5` -> `clients/reliops_v5`.

## Configurations

A configuration is a set of switches, passed to the agent as `REACT_V1_<SWITCH>` environment variables:

| Paper | Agent | Switches |
|---|---|---|
| Base | `reliops_v2` | `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS FLAT_ARGS` |
| A | `reliops_v2` | Base + `ROUTING ROUTE_REVIEW PROC_V2` |
| A+cards+gate | `reliops_v3` | A + `EVIDENCE_FIRST TRANSACTIONAL_FIX`, and `REACT_V1_EVIDENCE_MODE=cards` (plan 23) |
| A+driver gate | `reliops_v3` | A + `TRANSACTIONAL_FIX T1_DRIVER` (plan 25) |
| V5 | `reliops_v5` | A + `TRANSACTIONAL_FIX T1_DRIVER FIX_FAMILIES ADAPTIVE_WAIT D1_PREDICT` (plan 27) |

Agent and first judge: `gemini/gemini-3.5-flash-lite`. Second judge: `openai/gpt-5.4` with SREGym's judge prompt
(`scripts/rejudge.py`).

## Queues, pairing and records

The team ran every experiment through ReliOps Lab ([OmarElzero/ReliOps-Lab](https://github.com/OmarElzero/ReliOps-Lab)),
a local web application that clones SREGym, builds the cluster, splits a queue of (configuration, problem, repeat)
cells across machines, classifies runs that end without a result, and stores one record per run. Its guide
(`docs/GUIDE.md` in that repository) covers setup and running a queue. Its setup step clones the team's working
repository, which is private; with this artifact, follow the manual steps above instead.
