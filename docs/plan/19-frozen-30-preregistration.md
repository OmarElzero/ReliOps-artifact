Status: frozen 14 Nov 2026. Agent code at commit `d8137ebf8b129ce772adf850605d9da1a4e896b5` (last commit touching `agent/`). Nothing below changes after the
first frozen run starts; a change before that is a new commit that says why.

# Frozen 30 confirmation: pre-registration

## Why

Everything so far was measured on the 12 development problems, whose failures the team read to choose agent changes. The
frozen 30 (`experiments/first-30.csv`, pinned in `pins.json`) were never read. Each arm below is measured on them once,
and the result is reported whatever it is. Nothing in the agent is changed because of these runs.

## What dev-12 says going in

| Configuration | Diagnosis (first judge) | Diagnosis (GPT-5.4) | End-to-end | Source |
|---|---|---|---|---|
| Plain base (`B2 +FLAT`) | 44% | 28% | 39% | R3, 36 cells |
| A (routing + review + procedures v2) | 50% | 39% | 33% | R3, 36 cells |
| R4: A variants with REF, EXCAP, FLOW | 48% to 70% | not re-judged | 28% to 41% | R4, about 24 of 36 cells each (12 Nov) |
| R4 plain control | 62% | not re-judged | 54% | R4, 24 of 36 cells (12 Nov) |

No configuration beats the plain base end to end on dev-12, and the procedures' diagnosis gain shrank under a second
judge (9:2 pairs to 5:3). So the frozen 30 is a confirmation of a null or negative result, not a search for a winner.

## Arms (fixed)

1. `F30 B2 +FLAT`: the plain base (switches `TOKEN_LOG EMPTY_SUBMIT_GUARD OPTIONAL_ARGS FLAT_ARGS`).
2. `F30 A`: routing, route review and procedures v2 on the base (`+ ROUTING ROUTE_REVIEW PROC_V2`), the configuration
   the knowledge track built, as R3 and R4 ran it.
3. `F30 STRATUS`: the outside reference, descriptive only (no test).

If R4 finishes with an A variant beating the R4 plain control by the round 2 rule (sign test p < 0.05 end to end, both
in its favour), that variant replaces arm 2 before the freeze. Otherwise the arms stay as listed.

Deviation, stated at the freeze: R4 had not finished on 14 Nov (about two thirds of its cells). The plan was frozen anyway because
of the 20 Nov workshop deadline. In the interim export no A variant led the plain control end to end (28% to 41% against
54%), so the arms stay as listed.

## Setup (fixed)

- Agent and first judge `gemini/gemini-3.5-flash-lite`; agent code at commit `d8137eb`; no agent change
  until every cell has a result.
- 30 problems x 3 repeats per arm; shared queue split by problem, so all arms of a (problem, repeat) run on the same
  machine, back to back.
- Runs lost to the cluster, keys or quotas are missing, never failures; a cell is rerun up to 3 times.
- Mitigation is reported only on problems whose check fails for the do-nothing agent (the frozen 30 null calibration).
- After the runs, every diagnosis is re-judged with `openai/gpt-5.4` through SREGym's own judge (Lab audit tab).
- Then a hand label, blind to both judges: every diagnosis the two judges dispute, or a random 40 of them if there are
  more, each labeled by two team members separately (the dev-12 check had one labeler, who sided with GPT-5.4 on 14 and
  with the first judge on 13 of 27 disputed diagnoses).

## Analysis (fixed)

- **Primary:** end-to-end success (first judge), arm 2 against arm 1, exact two-sided sign test on discordant
  (problem, repeat) pairs; also at problem level (a problem counts for the arm that passed more of its repeats).
- **Decision:** arm 2 "helps" only if p < 0.05 in its favour; "hurts" only if p < 0.05 against it; otherwise "no
  detectable difference", reported with both rates and their Wilson intervals. Only discordant pairs count: with 20 of
  them, a 15:5 split is needed (p = 0.041); 6:0 is the smallest split that can pass.
- **Secondary, no test claims:** diagnosis under both judges; judge agreement and kappa; mitigation; tokens and time
  per run; STRATUS rates next to arms 1 and 2.
- Expectation written before the run: no detectable difference end to end; the first judge's diagnosis rates higher
  than GPT-5.4's by 10 to 20 points. The two-labeler hand label sides with each judge on roughly half of the disputed
  diagnoses.


## Planned deviation (15 Nov 2026)

Frozen runs that end on the model's per-minute limit (an infrastructure failure, no agent result) are re-run after the
confirmation finishes, through a key-rotating proxy (same model and requests; plan 24 section 6). Which runs and when is
recorded here when it happens.

### Applied: re-runs through the key proxy (16-17 Nov 2026)

After the confirmation's first pass, `F30 STRATUS` had 15 cells missing (84 of its runs had ended on the per-minute limit);
`F30 A` and `F30 B2 +FLAT` were complete. From 16 Nov 18:43 UTC the cloud machine re-ran the missing cells with
"only missing" through `scripts/key_proxy.py` (plan 24 section 6b): 8 keys of separate projects, the agent's model calls
sent to `AGENT_API_BASE=http://127.0.0.1:8790/v1beta`, forwarded to Google unchanged except for the key. Proxy log on the cloud machine
(kept by the team, not in this artifact): 1,071 requests from 16 Nov 18:43 to 17 Nov 00:18 UTC, 1,042 answered 200, 17 x 429 and
12 x 503 returned to the agent, 228 moved to another key after a 429 or a dead key. The Lab's network pre-check had to be
turned off on the cloud machine (`RELIOPS_NET_WAIT_MIN=0`): it tests the API host on port 443 with TLS and so cannot pass on a local
http proxy (Lab bug). The cloud machine's ReliOps clone was pulled to `33e625d` before these re-runs (agent/react_v2 unchanged; only the
recorded commit differs). State on 17 Nov 04:35: `F30 STRATUS` 88/90 cells, 2 still missing. Which runs went through the
proxy is identified by machine (the cloud machine, `machine-4` in `artifact-data/runs.csv`) and start time (after 16 Nov 18:43 UTC).

