# Frozen 30: results (plans 19, 23, 25)

One cell = (problem, repeat); earliest valid run counts; infrastructure failures excluded and re-run.

| Arm | cells | diagnosis (judge 1) | mitigation | end-to-end | diagnosis (gpt-5.4) | judge agreement (kappa) | duplicates |
|---|---|---|---|---|---|---|---|
| F30 A | 90 | 45/90 (50%) | 40/90 (44%) | 34/90 (38%) | 33/87 | 86% (0.73) | 15 |
| F30 B2 +FLAT | 90 | 53/90 (59%) | 41/90 (46%) | 36/90 (40%) | 32/89 | 74% (0.51) | 15 |
| F30 STRATUS | 90 | 48/90 (53%) | 48/90 (53%) | 39/90 (43%) | 34/90 | 82% (0.65) | 21 |
| F30 V3 A +CARDS +T1 | 90 | 52/90 (58%) | 52/90 (58%) | 44/90 (49%) | 38/87 | 83% (0.66) | 4 |
| F30 V3 A +T1v2 | 90 | 49/90 (54%) | 51/90 (57%) | 40/90 (44%) | 37/86 | 84% (0.68) | 8 |
| F30 V5 | 0 | | | | | | |

## Paired sign tests against F30 A (two-sided exact, discordant pairs: arm better : A better)

| Arm | mitigation | diagnosis | end-to-end |
|---|---|---|---|
| F30 B2 +FLAT | 14:13, p = 1.000 (n = 90) | 17:9, p = 0.169 (n = 90) | 12:10, p = 0.832 (n = 90) |
| F30 STRATUS | 16:8, p = 0.152 (n = 90) | 12:9, p = 0.664 (n = 90) | 13:8, p = 0.383 (n = 90) |
| F30 V3 A +CARDS +T1 | 23:11, p = 0.058 (n = 90) | 22:15, p = 0.324 (n = 90) | 24:14, p = 0.143 (n = 90) |
| F30 V3 A +T1v2 | 19:8, p = 0.052 (n = 90) | 13:9, p = 0.523 (n = 90) | 15:9, p = 0.307 (n = 90) |

Holm (plan 25, the two primary mitigation tests): F30 V3 A +CARDS +T1: p = 0.058, not significant; F30 V3 A +T1v2: p = 0.052, not significant
