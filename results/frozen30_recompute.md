# Frozen 30, recomputed from the exported run records

| Arm | cells | diagnosis J1 | diagnosis J2 | mitigation | E2E (J1) | E2E (J2) | kappa J1-J2 | lost / attempts | duplicates |
|---|---|---|---|---|---|---|---|---|---|
| F30 B2 +FLAT | 90 | 53/90 (59%) | 32/90 (36%) | 41/90 (46%) | 36/90 (40%) | 26/90 (29%) | 0.51 | 22/127 | 15 |
| F30 A | 90 | 45/90 (50%) | 33/90 (37%) | 40/90 (44%) | 34/90 (38%) | 30/90 (33%) | 0.73 | 14/119 | 15 |
| F30 V3 A +CARDS +T1 | 90 | 52/90 (58%) | 39/90 (43%) | 52/90 (58%) | 44/90 (49%) | 37/90 (41%) | 0.67 | 7/101 | 4 |
| F30 V3 A +T1v2 | 90 | 49/90 (54%) | 37/90 (41%) | 51/90 (57%) | 40/90 (44%) | 32/90 (36%) | 0.69 | 7/105 | 8 |
| F30 V5 | 90 | 52/90 (58%) | 37/90 (41%) | 54/90 (60%) | 42/90 (47%) | 34/90 (38%) | 0.68 | 12/121 | 19 |
| F30 STRATUS | 90 | 48/90 (53%) | 34/90 (38%) | 48/90 (53%) | 39/90 (43%) | 31/90 (34%) | 0.65 | 105/216 | 21 |

## Paired sign tests against F30 A (discordant cells, arm better : A better; two-sided exact)

| Arm | mitigation | diagnosis J1 | E2E J1 | diagnosis J2 | E2E J2 |
|---|---|---|---|---|---|
| F30 B2 +FLAT | 14:13, p = 1.00000 (n = 90) | 17:9, p = 0.16864 (n = 90) | 12:10, p = 0.83181 (n = 90) | 13:14, p = 1.00000 (n = 90) | 11:15, p = 0.55720 (n = 90) |
| F30 V3 A +CARDS +T1 | 23:11, p = 0.05761 (n = 90) | 22:15, p = 0.32401 (n = 90) | 24:14, p = 0.14331 (n = 90) | 19:13, p = 0.37709 (n = 90) | 19:12, p = 0.28104 (n = 90) |
| F30 V3 A +T1v2 | 19:8, p = 0.05224 (n = 90) | 13:9, p = 0.52347 (n = 90) | 15:9, p = 0.30746 (n = 90) | 12:8, p = 0.50344 (n = 90) | 11:9, p = 0.82380 (n = 90) |
| F30 V5 | 21:7, p = 0.01254 (n = 90) | 16:9, p = 0.22952 (n = 90) | 18:10, p = 0.18493 (n = 90) | 16:12, p = 0.57159 (n = 90) | 16:12, p = 0.57159 (n = 90) |
| F30 STRATUS | 16:8, p = 0.15159 (n = 90) | 12:9, p = 0.66362 (n = 90) | 13:8, p = 0.38331 (n = 90) | 12:11, p = 1.00000 (n = 90) | 12:11, p = 1.00000 (n = 90) |

## Holm over the four primary tests (alpha 0.05)

| Test | p | Holm bar | significant |
|---|---|---|---|
| plan 27: V5 vs A, mitigation | 0.01254 | 0.0125 | no |
| plan 25: A+driver gate vs A, mitigation | 0.05224 | 0.0167 | no |
| plan 25: A+cards+gate vs A, mitigation | 0.05761 | 0.0250 | no |
| plan 19: A vs base, E2E | 0.83181 | 0.0500 | no |

## V5 against the other arms (secondary, uncorrected)

| Comparison | mitigation | diagnosis J1 | E2E J1 |
|---|---|---|---|
| V5 vs F30 STRATUS | 14:8, p = 0.28628 | 18:14, p = 0.59661 | 14:11, p = 0.69004 |
| V5 vs F30 V3 A +T1v2 | 8:5, p = 0.58105 | 13:10, p = 0.67764 | 12:10, p = 0.83181 |
| V5 vs F30 V3 A +CARDS +T1 | 14:12, p = 0.84502 | 17:17, p = 1.00000 | 14:16, p = 0.85554 |
| V5 vs F30 B2 +FLAT | 19:6, p = 0.01463 | 15:16, p = 1.00000 | 18:12, p = 0.36159 |

## Do-nothing calibration (plan 19)

`Calibration - null agent - frozen 30 - second try` (the first try ran the plain v2 agent and is excluded): 77 valid null-agent runs on 30 problems; problems whose mitigation check passes with no fix: 0.
