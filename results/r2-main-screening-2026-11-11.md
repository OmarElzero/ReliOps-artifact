# Round 2 main stage: screening on the export of 11 Nov 2026 (dev-12, selection only)

Export `Dev - Ladder R2 - main - first try`: 688 runs, 107 incomplete (never counted as failures), 565 of 648 cells with a clean end-to-end result; 3 (problem, repeat) pairs not yet attempted. Computed with the Lab's `screening.screen` (rule of docs/plan/16). Pooled: end-to-end 167/565 (29.6%), diagnosis 229/566 (40.5%), mitigation 220/565 (38.9%). Without the 94 clean runs made on Helm v3: end-to-end 150/487 (30.8%); no contrast passes either way (strongest: FAULT_EXISTS one-on 7:2, p=0.18). Never solved end to end by any configuration: gc_capacity_degradation, priority_preemption_cascade, expired_tls. Warning: runs come from 9 repository commits; later agent changes are behind switches that are off in these configurations (off-equals-v1 tests).

## End-to-end

Metric `e2e_pass`; base `R2 B2`; all `R2 ALL`; 8 switches; 33 (problem, repeat) pairs expected per configuration (12 problems x 3 repeats).

## Configurations

| Configuration | Cells | Pass | Rate | 95% Wilson | Missing | Worst case | Problems all repeats pass |
|---|---|---|---|---|---|---|---|
| R2 B2 | 29 | 7 | 24% | 12% to 42% | 4 | 21% to 33% | 0 of 5 |
| R2 B2 +CHANGE_DIFF | 32 | 6 | 19% | 9% to 35% | 1 | 18% to 21% | 0 of 8 |
| R2 B2 +FAULT_EXISTS | 31 | 13 | 42% | 26% to 59% | 2 | 39% to 45% | 0 of 7 |
| R2 B2 +HEALTH_SWEEP | 32 | 11 | 34% | 20% to 52% | 1 | 33% to 36% | 0 of 8 |
| R2 B2 +LEDGER | 32 | 6 | 19% | 9% to 35% | 1 | 18% to 21% | 0 of 8 |
| R2 B2 +OUTPUT_TRIM | 32 | 12 | 38% | 23% to 55% | 1 | 36% to 39% | 0 of 8 |
| R2 B2 +SELFCHECK | 32 | 10 | 31% | 18% to 49% | 1 | 30% to 33% | 1 of 8 |
| R2 B2 +SOAK | 32 | 13 | 41% | 26% to 58% | 1 | 39% to 42% | 0 of 8 |
| R2 B2 +VERIFY_UNDO | 32 | 9 | 28% | 16% to 45% | 1 | 27% to 30% | 0 of 8 |
| R2 ALL | 31 | 9 | 29% | 16% to 47% | 2 | 27% to 33% | 1 of 7 |
| R2 ALL -CHANGE_DIFF | 31 | 9 | 29% | 16% to 47% | 2 | 27% to 33% | 0 of 7 |
| R2 ALL -FAULT_EXISTS | 32 | 7 | 22% | 11% to 39% | 1 | 21% to 24% | 1 of 8 |
| R2 ALL -HEALTH_SWEEP | 31 | 6 | 19% | 9% to 36% | 2 | 18% to 24% | 0 of 7 |
| R2 ALL -LEDGER | 31 | 12 | 39% | 24% to 56% | 2 | 36% to 42% | 1 of 7 |
| R2 ALL -OUTPUT_TRIM | 31 | 10 | 32% | 19% to 50% | 2 | 30% to 36% | 1 of 7 |
| R2 ALL -SELFCHECK | 32 | 8 | 25% | 13% to 42% | 1 | 24% to 27% | 0 of 8 |
| R2 ALL -SOAK | 31 | 8 | 26% | 14% to 43% | 2 | 24% to 30% | 0 of 7 |
| R2 ALL -VERIFY_UNDO | 31 | 11 | 35% | 21% to 53% | 2 | 33% to 39% | 0 of 7 |

## Contrasts (exact two-sided sign test on the pairs that flipped)

| Contrast | Treated | Control | Pairs | Only treated | Only control | p | p Holm (16) |
|---|---|---|---|---|---|---|---|
| CHANGE_DIFF:on | R2 B2 +CHANGE_DIFF | R2 B2 | 29 | 0 | 2 | 0.5000 | 1.0000 |
| CHANGE_DIFF:off | R2 ALL | R2 ALL -CHANGE_DIFF | 30 | 4 | 4 | 1.0000 | 1.0000 |
| FAULT_EXISTS:on | R2 B2 +FAULT_EXISTS | R2 B2 | 29 | 8 | 2 | 0.1094 | 1.0000 |
| FAULT_EXISTS:off | R2 ALL | R2 ALL -FAULT_EXISTS | 31 | 5 | 3 | 0.7266 | 1.0000 |
| HEALTH_SWEEP:on | R2 B2 +HEALTH_SWEEP | R2 B2 | 29 | 5 | 2 | 0.4531 | 1.0000 |
| HEALTH_SWEEP:off | R2 ALL | R2 ALL -HEALTH_SWEEP | 30 | 5 | 2 | 0.4531 | 1.0000 |
| LEDGER:on | R2 B2 +LEDGER | R2 B2 | 29 | 1 | 3 | 0.6250 | 1.0000 |
| LEDGER:off | R2 ALL | R2 ALL -LEDGER | 30 | 2 | 5 | 0.4531 | 1.0000 |
| OUTPUT_TRIM:on | R2 B2 +OUTPUT_TRIM | R2 B2 | 29 | 5 | 3 | 0.7266 | 1.0000 |
| OUTPUT_TRIM:off | R2 ALL | R2 ALL -OUTPUT_TRIM | 30 | 3 | 4 | 1.0000 | 1.0000 |
| SELFCHECK:on | R2 B2 +SELFCHECK | R2 B2 | 29 | 4 | 1 | 0.3750 | 1.0000 |
| SELFCHECK:off | R2 ALL | R2 ALL -SELFCHECK | 31 | 2 | 1 | 1.0000 | 1.0000 |
| SOAK:on | R2 B2 +SOAK | R2 B2 | 29 | 6 | 2 | 0.2891 | 1.0000 |
| SOAK:off | R2 ALL | R2 ALL -SOAK | 30 | 4 | 3 | 1.0000 | 1.0000 |
| VERIFY_UNDO:on | R2 B2 +VERIFY_UNDO | R2 B2 | 29 | 5 | 3 | 0.7266 | 1.0000 |
| VERIFY_UNDO:off | R2 ALL | R2 ALL -VERIFY_UNDO | 30 | 2 | 4 | 0.6875 | 1.0000 |
| ALL:base | R2 ALL | R2 B2 | 28 | 5 | 4 | 1.0000 | outside the 16 |

## Verdict per switch

| Switch | Verdict | Why |
|---|---|---|
| CHANGE_DIFF | no evidence | no contrast passes the exact sign test |
| FAULT_EXISTS | no evidence | no contrast passes the exact sign test |
| HEALTH_SWEEP | no evidence | no contrast passes the exact sign test |
| LEDGER | no evidence | no contrast passes the exact sign test |
| OUTPUT_TRIM | no evidence | no contrast passes the exact sign test |
| SELFCHECK | no evidence | no contrast passes the exact sign test |
| SOAK | no evidence | no contrast passes the exact sign test |
| VERIFY_UNDO | no evidence | no contrast passes the exact sign test |

## Candidate by the doc 15 rule

ALL beats B2: the candidate is ALL without CHANGE_DIFF, LEDGER, OUTPUT_TRIM, VERIFY_UNDO; stage 3 would run it. No switch has passed the sign test, so this only describes the current signs; it is not evidence. Switches: FAULT_EXISTS, HEALTH_SWEEP, SELFCHECK, SOAK.

## Warnings

- 18 configurations have runs from more than one commit (all commits: 02762304, 42f616fa, 715f7fb4, 792044b4, 826d7a51, a3fa20f3, b6551357, cda9bf04, eb489f14). Check that the agent code was the same, or set the older commits aside.
- 18 configurations have runs made with different tool versions (kind 0.24.0; kubectl v1.37.1; k8s v1.32.1; docker 29.9.3; helm v3.22.1 | kind 0.24.0; kubectl v1.37.1; k8s v1.32.1; docker 29.9.3; helm v4.0.2 | kind 0.25.0; kubectl v1.37.1; k8s v1.32.1; docker 29.1.3; helm v4.0.2 | kind 0.30.0; kubectl v1.37.1; k8s v1.32.1; docker 29.1.3; helm v4.0.2 | kind 0.30.0; kubectl v1.37.1; k8s v1.32.1; docker 29.9.3; helm v4.0.2 | kind 0.30.0; kubectl v1.37.2; k8s v1.32.1; docker 29.9.3; helm v4.0.2 | kind 0.33.0; kubectl v1.37.2; k8s v1.32.1; docker 29.9.3; helm v4.0.2).

## Rule

A switch helps only if one of its two contrasts passes the exact two-sided sign test on the pairs that flipped and its one-on and one-off effects point the same way. Without correction that is p < 0.05 (the smallest case is 6 flipped pairs, all one way); with Holm over the 16 contrasts it is the adjusted p < 0.05 (the smallest case is 10, all one way). Passing without correction only is a candidate, not a finding. Cells without a clean result are missing, never failures. This is a screening on dev data; gains are reported only from the frozen 30.
