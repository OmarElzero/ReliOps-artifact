# Frozen 30: facts for the AGENT 2027 paper

Written by `sim/frozen_paper_facts.py` on 19 Nov 2026 00:49 EET. Read-only. Counted cell = earliest valid run per (arm, problem, repeat); infrastructure rule and arms as in `sim/frozen_analysis.py`.
Summary: (1) cost table below; V5 is the most expensive arm (median 25 model calls, 344k tokens). (2) fix gate, F30 V5: 18 of 90 counted cells had at least one restore and 8 of those passed mitigation; median 2.0 (max 3) restore rounds; 46 of 72 cells passed with no restore. (3) example: see section 3. (4) runs collection: 3,391 on 19 Nov 2026. (5) hand label: not drawn yet.


## 1. Cost per arm (counted cells)

Median and 90th percentile (linear interpolation). `num_llm_calls` and `total_tokens` are the agent's own model calls and tokens as the Lab records them (judge calls excluded); `duration_s` is the whole run (deploy, fault, both stages, judge, cleanup).

| Arm | n | LLM calls median / p90 | total tokens median / p90 | duration s median / p90 |
|---|---|---|---|---|
| F30 A | 90 | 16 / 24 | 154,358 / 314,858 | 371 / 747 |
| F30 B2 +FLAT | 90 | 11 / 23 | 85,987 / 338,638 | 334 / 511 |
| F30 STRATUS | 90 | n/a / n/a (missing 90) | n/a / n/a (missing 90) | 570 / 2,050 |
| F30 V3 A +CARDS +T1 | 90 | 16 / 35 (missing 1) | 178,293 / 615,452 (missing 1) | 526 / 988 |
| F30 V3 A +T1v2 | 90 | 23 / 40 (missing 1) | 295,715 / 768,851 (missing 1) | 601 / 1,094 |
| F30 V5 | 90 | 25 / 48 | 343,913 / 1,077,689 | 587 / 1,409 |

STRATUS: none of its 90 counted run records has `num_llm_calls` or `total_tokens` (the Lab fills them from our agent's transcript (`runner.py` token totals), which STRATUS does not write), so only its duration is given here.

Attempts per arm (every stored run of the arm in its frozen experiment):

| Arm | attempts | lost to infrastructure | duplicates (later valid runs of a counted cell) | counted | of which incomplete, not infrastructure (counted as fail) |
|---|---|---|---|---|---|
| F30 A | 119 | 14 | 15 | 90 | 3 |
| F30 B2 +FLAT | 127 | 22 | 15 | 90 | 2 |
| F30 STRATUS | 216 | 105 | 21 | 90 | 7 |
| F30 V3 A +CARDS +T1 | 101 | 7 | 4 | 90 | 1 |
| F30 V3 A +T1v2 | 105 | 7 | 8 | 90 | 5 |
| F30 V5 | 121 | 12 | 19 | 90 | 4 |

Infrastructure losses by kind and matched INFRA keyword:

- F30 A: other: Max retries 10, key: quota 2, judge: judge model check 1, key: key rejected 1
- F30 B2 +FLAT: other: Max retries 14, key: key rejected 4, judge: judge model check 2, key: quota 2
- F30 STRATUS: other: Max retries 84, key: quota 11, judge: judge model check 4, key: key rejected 3, other: failed to deploy 2, cluster: Cluster not ready 1
- F30 V3 A +CARDS +T1: other: failed to deploy 4, judge: judge model check 2, key: key rejected 1
- F30 V3 A +T1v2: key: quota 4, key: key rejected 2, judge: judge model check 1
- F30 V5: judge: judge model check 9, key: quota 2, cluster: Cluster not ready 1

## 2. The transactional-fix gate in numbers

How the events appear (agent/react_v3_r5/driver.py; agent/react_v3_r4 writes the same names, minus `rebaseline`):
- `T1_DRIVER baseline`: health findings of the namespace before any mitigation change.
- `TRANSACTIONAL_FIX recorded`: an object is snapshotted before the agent's first write to it.
- On the agent's first `submit` after a change (T1 v2 arms, `T1_DRIVER` on): the driver waits (`ADAPTIVE_WAIT waited` in V5), re-reads the findings and logs `T1_DRIVER verdict` = clear / partial / unknown / no_effect / worse. On worse or no_effect, with rounds left, it restores every recorded object (`T1_DRIVER restored`, round n), re-baselines (V5: `T1_DRIVER rebaseline`), refuses the submit and tells the agent to try a different fix (V5 adds the routed procedure's next untried fix family, FIX_FAMILIES).
- Otherwise (and in A +CARDS +T1, which has no driver check) the gate asks the agent for one proof read (`TRANSACTIONAL_FIX proof_asked` / `proof_run`); the agent answers `not_fixed`, which restores (`TRANSACTIONAL_FIX restored`), or submits again (`proven`). `rounds_exhausted` = no restore rounds left (3 in V5, 2 in the v3 arms).

Counted per cell from its shared story. "Passed on the first fix" = mitigation pass with no restore.

| Arm | cells with story | >= 1 restore | of those, mitigation pass | median restore rounds (cells with >= 1) | restores by driver / by agent's not_fixed | rounds exhausted | mitigation pass with no restore | mitigation pass, all cells |
|---|---|---|---|---|---|---|---|---|
| F30 V5 | 90/90 | 18 | 8 | 2.0 (max 3) | 26 / 10 | 4 | 46 of 72 | 54/90 |
| F30 V3 A +T1v2 | 89/90 | 22 | 10 | 1.5 (max 2) | 29 / 4 | 6 | 41 of 67 | 51/90 |
| F30 V3 A +CARDS +T1 | 89/90 | 7 | 1 | 1 (max 2) | 0 / 10 | 0 | 51 of 82 | 52/90 |

First driver verdict per cell (T1 v2 arms; cells where the driver judged at least once):

- F30 V5: clear 37 (mitigation pass 31), unknown 35 (mitigation pass 13), no_effect 11 (mitigation pass 8), partial 3 (mitigation pass 2), worse 3 (mitigation pass 0)
- F30 V3 A +T1v2: unknown 33 (mitigation pass 13), clear 31 (mitigation pass 28), no_effect 16 (mitigation pass 10), worse 5 (mitigation pass 0), partial 2 (mitigation pass 0)

Cells with no shared story (left out of this section): 2 (ba567b9e-72af-41e7-b38d-98087fb067fe, 5bd90c26-43d8-4e5b-980e-b6d667c9be46).

## 3. Example cell for a figure

Selection rule (fixed before reading any candidate): counted F30 V5 cells whose first driver verdict was worse or no_effect, whose cluster was restored by the driver, with at least one mitigation write before and after the restore, and mitigation pass; take the one with the fewest agent steps (shortest story). Candidates meeting the rule: 7.

- 11 steps · `sidecar_port_conflict_hotel_reservation` · `8875928e-1c55-4f41-bca9-d4ff79d677dd` · writes before/after restore 1/1 · verdicts ['no_effect', 'clear']
- 15 steps · `readiness_probe_misconfiguration_hotel_reservation` · `9d005a43-060c-4238-9c57-f338b8b2e234` · writes before/after restore 1/1 · verdicts ['no_effect', 'clear']
- 18 steps · `readiness_probe_misconfiguration_hotel_reservation` · `cfae5177-8378-49de-8241-0117e042842b` · writes before/after restore 1/2 · verdicts ['no_effect', 'clear']
- 21 steps · `readiness_probe_misconfiguration_hotel_reservation` · `a9bbb051-5deb-4086-8999-0544c88cca4a` · writes before/after restore 1/1 · verdicts ['no_effect', 'clear']
- 26 steps · `revoke_auth_mongodb-1` · `40e33294-7816-49c6-b142-51a6b72ccba2` · writes before/after restore 4/4 · verdicts ['no_effect', 'clear']
- 39 steps · `duplicate_pvc_mounts_social_network` · `b882f9d1-0475-4191-be6f-69a0ee2c3e22` · writes before/after restore 4/13 · verdicts ['no_effect', 'no_effect', 'clear']
- 49 steps · `storage_user_unregistered-1` · `a066cebf-fe1c-46b6-bf34-e310a3853543` · writes before/after restore 3/12 · verdicts ['no_effect', 'no_effect', 'clear']

### Pick by the rule: `sidecar_port_conflict_hotel_reservation`, run `8875928e-1c55-4f41-bca9-d4ff79d677dd` (11 steps)

| Step | time | action (copied from the story, shortened) | driver check | restore |
|---|---|---|---|---|
| 8 | +219s | diagnosis submitted (procedures loaded: crash, probes, network) | | |
| | | driver baseline: 3 health findings in the namespace | | |
| 9 | +226s | WRITE `{"cmd": "kubectl patch deployment frontend -n hotel-reservation --type='json' -p='[{\"op\": \"remove\", \"path\": \"/spec/template/spec/containers/1/ports\"}]'"}` | | |
| | | driver check on the submit (waited 180 s, settled=False) | **no_effect** (round 0) | **yes**: 1 object(s) restored, submit refused, round 1 |
| 10 | +437s | WRITE `{"cmd": "kubectl patch deployment frontend -n hotel-reservation --type='json' -p='[{\"op\": \"remove\", \"path\": \"/spec/template/spec/containers/1\"}]'"}` -- agent's stated reason: "I am using mitigation family 2 (removing the conflicting sidecar container entirely or correcting its port/definition so it doesn't try to bind port 5000) by patching the deployment to remove the side" | | |
| | | driver check on the submit (waited 30 s, settled=True) | **clear** (round 1) | |
| | | gate asks for one proof read; agent runs `get_pod_status` (waited 30 s, settled=True) | | |
| 11 | +507s | submit | | |
| | | submit accepted (`proven`) | | no |
| | | **graded:** mitigation True, diagnosis True | | |

### Next by the rule: `readiness_probe_misconfiguration_hotel_reservation`, run `9d005a43-060c-4238-9c57-f338b8b2e234` (15 steps)

| Step | time | action (copied from the story, shortened) | driver check | restore |
|---|---|---|---|---|
| 7 | +173s | diagnosis submitted (procedures loaded: probes) | | |
| | | driver baseline: 3 health findings in the namespace | | |
| 8 | +183s | WRITE `{"cmd": "kubectl patch deployment frontend -n hotel-reservation --type=json -p='[{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/readinessProbe/httpGet/port\", \"value\": 5000}]'"}` | | |
| | | driver check on the submit (waited 180 s, settled=False) | **no_effect** (round 0) | **yes**: 1 object(s) restored, submit refused, round 1 |
| 12 | +404s | WRITE `{"cmd": "kubectl patch deployment frontend -n hotel-reservation --type=json -p='[{\"op\": \"remove\", \"path\": \"/spec/template/spec/containers/0/readinessProbe\"}]'"}` -- agent's stated reason: "I will use probe family 2 (probe timing) and family 5 (or relax/remove the faulty probe / fix path). Let's check what the HTTP GET path `/healthz` returns or adjust the path/probe timing/remove it if " | | |
| | | driver check on the submit (waited 30 s, settled=True) | **clear** (round 1) | |
| | | gate asks for one proof read; agent runs `get_resource` (waited 30 s, settled=True) | | |
| 15 | +476s | submit | | |
| | | submit accepted (`proven`) | | no |
| | | **graded:** mitigation True, diagnosis True | | |

**Read before using the pick.** The restore message lists the routed procedure's fix families and asks for the next untried one (FIX_FAMILIES). In the pick, the last procedure loaded was `network` (families: 1 Service selector, port or targetPort; 2 pod labels and endpoints; 3 NetworkPolicy; ...). After the restore the agent says it uses "family 2" but describes a family of its own (remove the conflicting sidecar), which is not the listed family 2. The second fix is a different change from the first (remove the whole sidecar container instead of only its ports), and it passed; but it is not a clean example of a switch between listed families. In the next cell by the rule (`probes` procedure), the first fix is the probe port (listed family 1) and the second removes the probe (listed family 5, "relax or remove the faulty probe"; the agent names families 2 and 5). If the figure must show a switch between listed families, the second cell is the first one that does; that is a criterion of the request, not a choice by outcome (both passed). Restore messages themselves are not in the story (the story shows agent steps and driver events, not the driver's text to the model); their wording is `T1_DRIVER_FAIL_TEXT` + `FIX_FAMILIES_TEXT` in `agent/react_v3_r5/prompts.py`. In both cells the driver's first check came after the 180 s cap of ADAPTIVE_WAIT with the rollout not settled, so the first fix was judged before its rollout had finished; whether that first fix would have passed is not known.

## 4. Total recorded runs

Aggregation count of the Firestore `runs` collection on 19 Nov 2026 00:49 EET: **3,391** (every run any team machine recorded through the Lab, including incomplete and infrastructure-failed attempts and the do-nothing calibration).

By purpose: the purpose is not a field of the run; the Lab stores it as a `marks` record when a run is started with one (a run can be re-marked, so these are mark records, not distinct runs). Mark records by purpose: experiment 967, dev 2,245, final 0 (all mark records 3,212). Runs started without a purpose have no mark.

## 5. Hand label (plan 19)

No frozen hand-label audit exists yet. Firestore `audit_plans` holds 3 audits (Final audit [2026-11-12], R2 all [2026-11-13], R3 Audit [2026-11-12]), none on the frozen arms; `audit_labels` holds 0 labels. The draw described in plan 19's 18 Nov addendum (group `F30 | pooled | 40`, seed 20261118, everyone labels every item) has not been made; the fallback sheets of `sim/frozen_followups.py draw-labels` do not exist either. So: 0 items labeled by either labeler, no score.
