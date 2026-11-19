# Frozen 30: checks for paper v7 (from artifact-data)

## 1. Duplicate valid runs

| Configuration | cells with >1 valid run | extra runs | same machine as counted run | median hours after counted run |
|---|---|---|---|---|
| F30 B2 +FLAT | 13 | 15 | 1 | 3.9 |
| F30 A | 15 | 15 | 3 | 4.3 |
| F30 V3 A +CARDS +T1 | 4 | 4 | 0 | 0.2 |
| F30 V3 A +T1v2 | 8 | 8 | 2 | 0.2 |
| F30 V5 | 17 | 19 | 5 | 0.8 |
| F30 STRATUS | 18 | 21 | 10 | 13.6 |
- F30 B2 +FLAT: (counted machine, duplicate machine) {('machine-6', 'machine-4'): 12, ('machine-4', 'machine-6'): 2, ('machine-6', 'machine-6'): 1}
- F30 A: (counted machine, duplicate machine) {('machine-6', 'machine-4'): 11, ('machine-4', 'machine-4'): 3, ('machine-4', 'machine-6'): 1}
- F30 V3 A +CARDS +T1: (counted machine, duplicate machine) {('machine-5', 'machine-2'): 3, ('machine-2', 'machine-5'): 1}
- F30 V3 A +T1v2: (counted machine, duplicate machine) {('machine-5', 'machine-2'): 2, ('machine-2', 'machine-5'): 2, ('machine-6', 'machine-6'): 1, ('machine-6', 'machine-2'): 1, ('machine-3', 'machine-2'): 1, ('machine-5', 'machine-5'): 1}
- F30 V5: (counted machine, duplicate machine) {('machine-4', 'machine-1'): 6, ('machine-2', 'machine-2'): 4, ('machine-4', 'machine-3'): 4, ('machine-2', 'machine-4'): 3, ('machine-4', 'machine-4'): 1, ('machine-4', 'machine-2'): 1}
- F30 STRATUS: (counted machine, duplicate machine) {('machine-6', 'machine-4'): 10, ('machine-4', 'machine-4'): 8, ('machine-6', 'machine-6'): 2, ('machine-4', 'machine-6'): 1}

## 2. Same-machine split, mitigation vs A (discordant cells: configuration better : A better)

| Configuration | same-machine cells | split there | other cells | split there |
|---|---|---|---|---|
| F30 B2 +FLAT | 86 | 13:12, p = 1.000 | 4 | 1:1, p = 1.000 |
| F30 V3 A +CARDS +T1 | 5 | 3:0, p = 0.250 | 85 | 20:11, p = 0.150 |
| F30 V3 A +T1v2 | 6 | 2:0, p = 0.500 | 84 | 17:8, p = 0.108 |
| F30 V5 | 32 | 15:2, p = 0.002 | 58 | 6:5, p = 1.000 |
| F30 STRATUS | 77 | 14:8, p = 0.286 | 13 | 2:0, p = 0.500 |

## 3. Machines

- F30 B2 +FLAT: machine-4 31/64, machine-2 7/15, machine-6 3/11
- F30 A: machine-4 34/63, machine-2 5/16, machine-6 1/11
- F30 V3 A +CARDS +T1: machine-2 22/35, machine-5 6/18, machine-1 13/15, machine-6 5/13, machine-3 6/9
- F30 V3 A +T1v2: machine-2 20/37, machine-5 8/16, machine-1 12/15, machine-6 4/12, machine-3 7/10
- F30 V5: machine-4 21/28, machine-2 14/27, machine-6 16/21, machine-3 3/8, machine-1 0/6
- F30 STRATUS: machine-4 40/71, machine-6 3/11, machine-2 5/8

## 4. Run-to-run agreement (counted run vs the next valid run of the same cell, same configuration)

| Configuration | pairs | mitigation agree | diagnosis J1 agree | mitigation pass, counted vs next |
|---|---|---|---|---|
| F30 B2 +FLAT | 13 | 9/13 | 11/13 | 4 vs 4 |
| F30 A | 15 | 11/15 | 8/15 | 1 vs 5 |
| F30 V3 A +CARDS +T1 | 4 | 4/4 | 4/4 | 1 vs 1 |
| F30 V3 A +T1v2 | 8 | 6/8 | 8/8 | 0 vs 2 |
| F30 V5 | 17 | 16/17 | 16/17 | 11 vs 10 |
| F30 STRATUS | 18 | 14/18 | 15/18 | 3 vs 7 |
| all | 75 | 60/75 | 62/75 | |

## 5. Problem-level sign tests of the gate configurations vs A, Holm over the three (post-hoc)

- F30 V3 A +CARDS +T1: 13:5, p = 0.0963
- F30 V3 A +T1v2: 10:4, p = 0.1796
- F30 V5: 12:4, p = 0.0768
- Holm: F30 V5 p = 0.0768 vs bar 0.0167: not significant
- Holm: F30 V3 A +CARDS +T1 p = 0.0963 vs bar 0.0250: not significant
- Holm: F30 V3 A +T1v2 p = 0.1796 vs bar 0.0500: not significant
- Holm-adjusted p: F30 V5 0.230, F30 V3 A +CARDS +T1 0.230, F30 V3 A +T1v2 0.230

## 6. Run ledger

- by phase: {'calibration': 150, 'development': 2449, 'frozen': 792}; total 3391
- frozen by (experiment, arm or stray): {('Final - Frozen 30 V3 - first try', 'F30 V3 A +T1v2'): 105, ('Final - Frozen 30 V3 - first try', 'F30 V3 A +CARDS +T1'): 101, ('Final - Frozen 30 V3 - first try', 'other label'): 3, ('Final - Frozen 30 V5 - first try', 'F30 V5'): 121, ('Final - Frozen 30 confirmation - first try', 'F30 B2 +FLAT'): 127, ('Final - Frozen 30 confirmation - first try', 'F30 A'): 119, ('Final - Frozen 30 confirmation - first try', 'F30 STRATUS'): 216}
- calibration: {'Calibration - null agent - frozen 30 - first try': 38, 'Calibration - null agent - frozen 30 - second try': 112}
- development experiments (25): {'Dev - Ladder R2 - main - first try': 775, 'Dev - R4 REF EXCAP FLOW - first try': 588, 'Dev - R3 Routing + STRATUS - first try': 291, 'Dev - Ladder R1 - M1 - first try': 234, 'Dev - V3 r4.1 - first try': 195, '(none)': 118, 'Dev Analysis - A1 & A4 -  Second Try': 88, 'Dev - V5 r5 - first try': 45} ...
