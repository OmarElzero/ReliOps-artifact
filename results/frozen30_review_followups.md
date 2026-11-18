# Frozen 30: review follow-ups for the AGENT 2027 paper (v5)

Written by `sim/frozen_review_followups.py` on 19 Nov 2026 01:47 EET, read-only. Arms, infrastructure rule and counted cell (earliest valid run per (arm, problem, repeat)) as in `sim/frozen_analysis.py`. Seed 20261119 for every random draw. Names: Base = `F30 B2 +FLAT`, A = `F30 A`, A+cards+gate = `F30 V3 A +CARDS +T1`, A+driver gate = `F30 V3 A +T1v2`, V5 = `F30 V5`, STRATUS = `F30 STRATUS`. Tests are two-sided. Cell-level sign test = the paper's pre-registered test; the problem-level tests treat the 30 problems as the units (three repeats of a problem are not independent).

**Summary.** (1) Mitigation vs A, problem level (more : less : ties, sign p, Wilcoxon p, 95% CI in points): A+cards+gate 13:5:12, p = 0.096, W p = 0.132, [-2.2, +27.8]; A+driver gate 10:4:16, p = 0.180, W p = 0.052, [+1.1, +23.3]; V5 12:4:14, p = 0.077, W p = 0.045, [+2.2, +28.9]; Base 8:7:15, p = 1.000, W p = 0.959, [-10.0, +12.2]; STRATUS 11:5:14, p = 0.210, W p = 0.226, [-5.6, +23.3]. Plan 19 primary (A vs Base, E2E): cells 10:12 (p = 0.832), problems 4:8:18 (p = 0.388). (2) E2E under GPT-5.4 vs A, cells: A+cards+gate 19:12 (p = 0.281); A+driver gate 11:9 (p = 0.824); V5 16:12 (p = 0.572); Base 11:15 (p = 0.557); STRATUS 12:11 (p = 1.000). Pooled 2x2: first-judge-pass/GPT-fail 91, the reverse 4, of 540. (3) V5 vs A mitigation: earliest 21:7, p = 0.013 (n = 90); problems 12:4:14, Wilcoxon p = 0.045; first-attempt-valid 20:7, p = 0.019 (n = 84); latest 19:9, p = 0.087 (n = 90); problems 11:5:14, Wilcoxon p = 0.146. (4) same machine as A: A+cards+gate 5/90, A+driver gate 6/90, V5 32/90, Base 86/90, STRATUS 77/90. (5) 3,391 runs; rounds 1-4 by experiment name 1,888 (paper 1,807 from earlier exports). (6) STRATUS model: gemini/gemini-3.5-flash-lite (90).

## 1. Problem-level tests, mitigation, each configuration vs A

### A+cards+gate vs A, mitigation

- Cells (both sides): 90; discordant cells A+cards+gate better : A better = **23:11**, exact sign test p = 0.058.
- Problems where A+cards+gate has more passes : A has more : ties = **13:5:12**, exact sign test over problems p = 0.096.
- Wilcoxon signed-rank on the 30 per-problem differences: 18 nonzero, W+ = 119.5, W- = 51.5, exact two-sided p = 0.132.
- Difference in rate: +13.3 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-2.2, +27.8].
- Concentration: the 34 discordant cells lie in 19 problems; the 5 problems with most carry 14. By problem (discordant cells): `configmap_drift_hotel_reservation` 3, `readiness_probe_misconfiguration_hotel_reservation` 3, `finalizer_deadlock_controller_hotel_reservation` 3, `storage_user_unregistered-1` 3, `revoke_auth_mongodb-1` 2, `wrong_bin_usage` 2, `missing_service_hotel_reservation` 2, `init_container_dependency_hang_social_network` 2, `network_policy_block` 2, `duplicate_pvc_mounts_social_network` 2, `ephemeral_port_range_hotel_reservation` 2, `service_wrong_pod_selection_hotel_reservation` 1, `file_descriptor_exhaustion` 1, `search_rate_retry_collapse_hotel_reservation` 1, `wrong_service_selector_hotel_reservation` 1, `misconfig_app_hotel_res` 1, `latent_sector_error` 1, `scale_pod_zero_social_net` 1, `update_incompatible_correlated` 1.

| Problem | A+cards+gate (of 3) | A (of 3) |
|---|---|---|
| `configmap_drift_hotel_reservation` | 1 | 2 |
| `ephemeral_port_range_hotel_reservation` | 3 | 1 |
| `file_descriptor_exhaustion` | 3 | 2 |
| `finalizer_deadlock_controller_hotel_reservation` | 3 | 0 |
| `init_container_dependency_hang_social_network` | 0 | 2 |
| `latent_sector_error` | 1 | 0 |
| `misconfig_app_hotel_res` | 3 | 2 |
| `missing_service_hotel_reservation` | 1 | 3 |
| `network_policy_block` | 3 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `revoke_auth_mongodb-1` | 3 | 1 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `search_rate_retry_collapse_hotel_reservation` | 1 | 0 |
| `service_wrong_pod_selection_hotel_reservation` | 0 | 1 |
| `storage_user_unregistered-1` | 2 | 1 |
| `update_incompatible_correlated` | 2 | 1 |
| `wrong_bin_usage` | 0 | 2 |
| `wrong_service_selector_hotel_reservation` | 3 | 2 |
| (the other 12 problems: equal) | | |

### A+driver gate vs A, mitigation

- Cells (both sides): 90; discordant cells A+driver gate better : A better = **19:8**, exact sign test p = 0.052.
- Problems where A+driver gate has more passes : A has more : ties = **10:4:16**, exact sign test over problems p = 0.180.
- Wilcoxon signed-rank on the 30 per-problem differences: 14 nonzero, W+ = 83, W- = 22, exact two-sided p = 0.052.
- Difference in rate: +12.2 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [+1.1, +23.3].
- Concentration: the 27 discordant cells lie in 18 problems; the 5 problems with most carry 11. By problem (discordant cells): `readiness_probe_misconfiguration_hotel_reservation` 3, `revoke_auth_mongodb-1` 2, `misconfig_app_hotel_res` 2, `wrong_bin_usage` 2, `finalizer_deadlock_controller_hotel_reservation` 2, `storage_user_unregistered-1` 2, `init_container_dependency_hang_social_network` 2, `latent_sector_error` 2, `network_policy_block` 1, `wrong_service_selector_hotel_reservation` 1, `duplicate_pvc_mounts_social_network` 1, `service_wrong_pod_selection_hotel_reservation` 1, `file_descriptor_exhaustion` 1, `missing_service_hotel_reservation` 1, `configmap_drift_hotel_reservation` 1, `duplicate_pvc_mounts_hotel_reservation` 1, `scale_pod_zero_social_net` 1, `update_incompatible_correlated` 1.

| Problem | A+driver gate (of 3) | A (of 3) |
|---|---|---|
| `configmap_drift_hotel_reservation` | 3 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 2 | 3 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `file_descriptor_exhaustion` | 3 | 2 |
| `finalizer_deadlock_controller_hotel_reservation` | 2 | 0 |
| `latent_sector_error` | 2 | 0 |
| `missing_service_hotel_reservation` | 2 | 3 |
| `network_policy_block` | 0 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `revoke_auth_mongodb-1` | 3 | 1 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `service_wrong_pod_selection_hotel_reservation` | 0 | 1 |
| `update_incompatible_correlated` | 2 | 1 |
| `wrong_service_selector_hotel_reservation` | 3 | 2 |
| (the other 16 problems: equal) | | |

### V5 vs A, mitigation

- Cells (both sides): 90; discordant cells V5 better : A better = **21:7**, exact sign test p = 0.013.
- Problems where V5 has more passes : A has more : ties = **12:4:14**, exact sign test over problems p = 0.077.
- Wilcoxon signed-rank on the 30 per-problem differences: 16 nonzero, W+ = 107, W- = 29, exact two-sided p = 0.045.
- Difference in rate: +15.6 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [+2.2, +28.9].
- Concentration: the 28 discordant cells lie in 18 problems; the 5 problems with most carry 12. By problem (discordant cells): `readiness_probe_misconfiguration_hotel_reservation` 3, `latent_sector_error` 3, `revoke_auth_mongodb-1` 2, `wrong_bin_usage` 2, `misconfig_app_hotel_res` 2, `finalizer_deadlock_controller_hotel_reservation` 2, `update_incompatible_correlated` 2, `storage_user_unregistered-1` 2, `search_rate_retry_collapse_hotel_reservation` 1, `configmap_drift_hotel_reservation` 1, `network_policy_block` 1, `service_wrong_pod_selection_hotel_reservation` 1, `file_descriptor_exhaustion` 1, `missing_service_hotel_reservation` 1, `wrong_service_selector_hotel_reservation` 1, `duplicate_pvc_mounts_social_network` 1, `scale_pod_zero_social_net` 1, `init_container_dependency_hang_social_network` 1.

| Problem | V5 (of 3) | A (of 3) |
|---|---|---|
| `configmap_drift_hotel_reservation` | 3 | 2 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `file_descriptor_exhaustion` | 3 | 2 |
| `finalizer_deadlock_controller_hotel_reservation` | 2 | 0 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 3 | 0 |
| `misconfig_app_hotel_res` | 0 | 2 |
| `missing_service_hotel_reservation` | 2 | 3 |
| `network_policy_block` | 0 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `revoke_auth_mongodb-1` | 3 | 1 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `search_rate_retry_collapse_hotel_reservation` | 1 | 0 |
| `service_wrong_pod_selection_hotel_reservation` | 0 | 1 |
| `update_incompatible_correlated` | 3 | 1 |
| `wrong_service_selector_hotel_reservation` | 3 | 2 |
| (the other 14 problems: equal) | | |

### Base vs A, mitigation

- Cells (both sides): 90; discordant cells Base better : A better = **14:13**, exact sign test p = 1.000.
- Problems where Base has more passes : A has more : ties = **8:7:15**, exact sign test over problems p = 1.000.
- Wilcoxon signed-rank on the 30 per-problem differences: 15 nonzero, W+ = 63, W- = 57, exact two-sided p = 0.959.
- Difference in rate: +1.1 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-10.0, +12.2].
- Concentration: the 27 discordant cells lie in 18 problems; the 5 problems with most carry 11. By problem (discordant cells): `revoke_auth_mongodb-1` 3, `scale_pod_zero_social_net` 2, `misconfig_app_hotel_res` 2, `update_incompatible_correlated` 2, `file_descriptor_exhaustion` 2, `latent_sector_error` 2, `wrong_service_selector_hotel_reservation` 2, `ephemeral_port_range_hotel_reservation` 2, `duplicate_pvc_mounts_hotel_reservation` 1, `service_dns_resolution_failure_social_network` 1, `network_policy_block` 1, `service_wrong_pod_selection_hotel_reservation` 1, `missing_service_hotel_reservation` 1, `finalizer_deadlock_controller_hotel_reservation` 1, `duplicate_pvc_mounts_social_network` 1, `storage_user_unregistered-1` 1, `init_container_dependency_hang_social_network` 1, `wrong_bin_usage` 1.

| Problem | Base (of 3) | A (of 3) |
|---|---|---|
| `duplicate_pvc_mounts_hotel_reservation` | 2 | 3 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `finalizer_deadlock_controller_hotel_reservation` | 1 | 0 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 2 | 0 |
| `missing_service_hotel_reservation` | 2 | 3 |
| `network_policy_block` | 0 | 1 |
| `revoke_auth_mongodb-1` | 2 | 1 |
| `scale_pod_zero_social_net` | 0 | 2 |
| `service_dns_resolution_failure_social_network` | 1 | 0 |
| `service_wrong_pod_selection_hotel_reservation` | 0 | 1 |
| `storage_user_unregistered-1` | 0 | 1 |
| `update_incompatible_correlated` | 3 | 1 |
| `wrong_bin_usage` | 3 | 2 |
| `wrong_service_selector_hotel_reservation` | 0 | 2 |
| (the other 15 problems: equal) | | |

### STRATUS vs A, mitigation

- Cells (both sides): 90; discordant cells STRATUS better : A better = **16:8**, exact sign test p = 0.152.
- Problems where STRATUS has more passes : A has more : ties = **11:5:14**, exact sign test over problems p = 0.210.
- Wilcoxon signed-rank on the 30 per-problem differences: 16 nonzero, W+ = 91.5, W- = 44.5, exact two-sided p = 0.226.
- Difference in rate: +8.9 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-5.6, +23.3].
- Concentration: the 24 discordant cells lie in 16 problems; the 5 problems with most carry 12. By problem (discordant cells): `missing_service_hotel_reservation` 3, `readiness_probe_misconfiguration_hotel_reservation` 3, `revoke_auth_mongodb-1` 2, `configmap_drift_hotel_reservation` 2, `latent_sector_error` 2, `network_policy_block` 2, `node_conntrack_exhaustion_hotel_reservation` 1, `service_wrong_pod_selection_hotel_reservation` 1, `storage_user_unregistered-1` 1, `update_incompatible_correlated` 1, `duplicate_pvc_mounts_social_network` 1, `misconfig_app_hotel_res` 1, `file_descriptor_exhaustion` 1, `scale_pod_zero_social_net` 1, `init_container_dependency_hang_social_network` 1, `wrong_bin_usage` 1.

| Problem | STRATUS (of 3) | A (of 3) |
|---|---|---|
| `configmap_drift_hotel_reservation` | 0 | 2 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `file_descriptor_exhaustion` | 1 | 2 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 2 | 0 |
| `misconfig_app_hotel_res` | 1 | 2 |
| `missing_service_hotel_reservation` | 0 | 3 |
| `network_policy_block` | 3 | 1 |
| `node_conntrack_exhaustion_hotel_reservation` | 1 | 0 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `revoke_auth_mongodb-1` | 3 | 1 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `service_wrong_pod_selection_hotel_reservation` | 0 | 1 |
| `storage_user_unregistered-1` | 2 | 1 |
| `update_incompatible_correlated` | 2 | 1 |
| `wrong_bin_usage` | 3 | 2 |
| (the other 14 problems: equal) | | |

## 1b. Plan 19 primary: A vs Base, end-to-end (first judge)

### A vs Base, end-to-end (first judge)

- Cells (both sides): 90; discordant cells A better : Base better = **10:12**, exact sign test p = 0.832.
- Problems where A has more passes : Base has more : ties = **4:8:18**, exact sign test over problems p = 0.388.
- Wilcoxon signed-rank on the 30 per-problem differences: 12 nonzero, W+ = 36, W- = 42, exact two-sided p = 0.843.
- Difference in rate: -2.2 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-12.2, +8.9].
- Concentration: the 22 discordant cells lie in 14 problems; the 5 problems with most carry 11. By problem (discordant cells): `file_descriptor_exhaustion` 3, `duplicate_pvc_mounts_hotel_reservation` 2, `missing_service_hotel_reservation` 2, `scale_pod_zero_social_net` 2, `misconfig_app_hotel_res` 2, `latent_sector_error` 2, `wrong_service_selector_hotel_reservation` 2, `revoke_auth_mongodb-1` 1, `service_dns_resolution_failure_social_network` 1, `network_policy_block` 1, `finalizer_deadlock_controller_hotel_reservation` 1, `duplicate_pvc_mounts_social_network` 1, `init_container_dependency_hang_social_network` 1, `wrong_bin_usage` 1.

| Problem | A (of 3) | Base (of 3) |
|---|---|---|
| `duplicate_pvc_mounts_hotel_reservation` | 3 | 1 |
| `duplicate_pvc_mounts_social_network` | 2 | 3 |
| `file_descriptor_exhaustion` | 1 | 2 |
| `finalizer_deadlock_controller_hotel_reservation` | 0 | 1 |
| `init_container_dependency_hang_social_network` | 2 | 3 |
| `latent_sector_error` | 0 | 2 |
| `network_policy_block` | 1 | 0 |
| `revoke_auth_mongodb-1` | 0 | 1 |
| `scale_pod_zero_social_net` | 2 | 0 |
| `service_dns_resolution_failure_social_network` | 0 | 1 |
| `wrong_bin_usage` | 2 | 3 |
| `wrong_service_selector_hotel_reservation` | 2 | 0 |
| (the other 18 problems: equal) | | |

## 2. End-to-end under the second judge (GPT-5.4)

E2E J2 = GPT-5.4 passes the diagnosis and the mitigation check passes. A counted run with no diagnosis text counts as a J2 diagnosis fail (it was never sent to the judge); a counted run with text but no GPT-5.4 verdict is left out (listed).

| Configuration | E2E J2 | E2E (first judge) | cells without a J2 verdict |
|---|---|---|---|
| A | 30/90 (33%) | 34/90 (38%) | 0 |
| Base | 26/90 (29%) | 36/90 (40%) | 0 |
| STRATUS | 31/90 (34%) | 39/90 (43%) | 0 |
| A+cards+gate | 37/90 (41%) | 44/90 (49%) | 0 |
| A+driver gate | 32/90 (36%) | 40/90 (44%) | 0 |
| V5 | 34/90 (38%) | 42/90 (47%) | 0 |

### A+cards+gate vs A, E2E under GPT-5.4

- Cells (both sides): 90; discordant cells A+cards+gate better : A better = **19:12**, exact sign test p = 0.281.
- Problems where A+cards+gate has more passes : A has more : ties = **12:7:11**, exact sign test over problems p = 0.359.
- Wilcoxon signed-rank on the 30 per-problem differences: 19 nonzero, W+ = 115.5, W- = 74.5, exact two-sided p = 0.413.
- Difference in rate: +7.8 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-7.8, +23.3].
- Concentration: the 31 discordant cells lie in 19 problems; the 5 problems with most carry 12. By problem (discordant cells): `configmap_drift_hotel_reservation` 3, `readiness_probe_misconfiguration_hotel_reservation` 3, `duplicate_pvc_mounts_hotel_reservation` 2, `finalizer_deadlock_controller_hotel_reservation` 2, `wrong_bin_usage` 2, `missing_service_hotel_reservation` 2, `file_descriptor_exhaustion` 2, `init_container_dependency_hang_social_network` 2, `network_policy_block` 2, `update_incompatible_correlated` 2, `missing_configmap_hotel_reservation` 1, `wrong_service_selector_hotel_reservation` 1, `storage_user_unregistered-1` 1, `duplicate_pvc_mounts_social_network` 1, `misconfig_app_hotel_res` 1, `latent_sector_error` 1, `scale_pod_zero_social_net` 1, `auth_miss_mongodb` 1, `ephemeral_port_range_hotel_reservation` 1.

| Problem | A+cards+gate (of 3) | A (of 3) |
|---|---|---|
| `auth_miss_mongodb` | 3 | 2 |
| `configmap_drift_hotel_reservation` | 1 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 1 | 3 |
| `duplicate_pvc_mounts_social_network` | 1 | 2 |
| `ephemeral_port_range_hotel_reservation` | 1 | 0 |
| `file_descriptor_exhaustion` | 3 | 1 |
| `finalizer_deadlock_controller_hotel_reservation` | 2 | 0 |
| `init_container_dependency_hang_social_network` | 0 | 2 |
| `latent_sector_error` | 1 | 0 |
| `misconfig_app_hotel_res` | 0 | 1 |
| `missing_configmap_hotel_reservation` | 3 | 2 |
| `missing_service_hotel_reservation` | 0 | 2 |
| `network_policy_block` | 3 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `storage_user_unregistered-1` | 1 | 0 |
| `update_incompatible_correlated` | 2 | 0 |
| `wrong_bin_usage` | 0 | 2 |
| `wrong_service_selector_hotel_reservation` | 3 | 2 |
| (the other 11 problems: equal) | | |

### A+driver gate vs A, E2E under GPT-5.4

- Cells (both sides): 90; discordant cells A+driver gate better : A better = **11:9**, exact sign test p = 0.824.
- Problems where A+driver gate has more passes : A has more : ties = **8:6:16**, exact sign test over problems p = 0.791.
- Wilcoxon signed-rank on the 30 per-problem differences: 14 nonzero, W+ = 59, W- = 46, exact two-sided p = 0.800.
- Difference in rate: +2.2 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-7.8, +12.2].
- Concentration: the 20 discordant cells lie in 16 problems; the 5 problems with most carry 9. By problem (discordant cells): `wrong_service_selector_hotel_reservation` 2, `wrong_bin_usage` 2, `missing_service_hotel_reservation` 2, `latent_sector_error` 2, `network_policy_block` 1, `misconfig_app_hotel_res` 1, `duplicate_pvc_mounts_social_network` 1, `readiness_probe_misconfiguration_hotel_reservation` 1, `missing_configmap_hotel_reservation` 1, `file_descriptor_exhaustion` 1, `duplicate_pvc_mounts_hotel_reservation` 1, `init_container_dependency_hang_social_network` 1, `auth_miss_mongodb` 1, `scale_pod_zero_social_net` 1, `update_incompatible_correlated` 1, `configmap_drift_hotel_reservation` 1.

| Problem | A+driver gate (of 3) | A (of 3) |
|---|---|---|
| `auth_miss_mongodb` | 3 | 2 |
| `configmap_drift_hotel_reservation` | 1 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 2 | 3 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `file_descriptor_exhaustion` | 2 | 1 |
| `init_container_dependency_hang_social_network` | 1 | 2 |
| `latent_sector_error` | 2 | 0 |
| `misconfig_app_hotel_res` | 0 | 1 |
| `missing_configmap_hotel_reservation` | 3 | 2 |
| `missing_service_hotel_reservation` | 0 | 2 |
| `network_policy_block` | 0 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 1 | 0 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `update_incompatible_correlated` | 1 | 0 |
| (the other 16 problems: equal) | | |

### V5 vs A, E2E under GPT-5.4

- Cells (both sides): 90; discordant cells V5 better : A better = **16:12**, exact sign test p = 0.572.
- Problems where V5 has more passes : A has more : ties = **8:5:17**, exact sign test over problems p = 0.581.
- Wilcoxon signed-rank on the 30 per-problem differences: 13 nonzero, W+ = 53, W- = 38, exact two-sided p = 0.629.
- Difference in rate: +4.4 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-8.9, +17.8].
- Concentration: the 28 discordant cells lie in 17 problems; the 5 problems with most carry 11. By problem (discordant cells): `latent_sector_error` 3, `duplicate_pvc_mounts_hotel_reservation` 2, `duplicate_pvc_mounts_social_network` 2, `file_descriptor_exhaustion` 2, `wrong_bin_usage` 2, `missing_configmap_hotel_reservation` 2, `configmap_drift_hotel_reservation` 2, `missing_service_hotel_reservation` 2, `update_incompatible_correlated` 2, `scale_pod_zero_social_net` 2, `network_policy_block` 1, `readiness_probe_misconfiguration_hotel_reservation` 1, `misconfig_app_hotel_res` 1, `auth_miss_mongodb` 1, `wrong_service_selector_hotel_reservation` 1, `ephemeral_port_range_hotel_reservation` 1, `init_container_dependency_hang_social_network` 1.

| Problem | V5 (of 3) | A (of 3) |
|---|---|---|
| `auth_miss_mongodb` | 3 | 2 |
| `configmap_drift_hotel_reservation` | 0 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 1 | 3 |
| `duplicate_pvc_mounts_social_network` | 0 | 2 |
| `ephemeral_port_range_hotel_reservation` | 1 | 0 |
| `file_descriptor_exhaustion` | 3 | 1 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 3 | 0 |
| `misconfig_app_hotel_res` | 0 | 1 |
| `network_policy_block` | 0 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 1 | 0 |
| `update_incompatible_correlated` | 2 | 0 |
| `wrong_service_selector_hotel_reservation` | 3 | 2 |
| (the other 17 problems: equal) | | |

### Base vs A, E2E under GPT-5.4

- Cells (both sides): 90; discordant cells Base better : A better = **11:15**, exact sign test p = 0.557.
- Problems where Base has more passes : A has more : ties = **7:7:16**, exact sign test over problems p = 1.000.
- Wilcoxon signed-rank on the 30 per-problem differences: 14 nonzero, W+ = 38.5, W- = 66.5, exact two-sided p = 0.385.
- Difference in rate: -4.4 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-17.8, +7.8].
- Concentration: the 26 discordant cells lie in 16 problems; the 5 problems with most carry 11. By problem (discordant cells): `file_descriptor_exhaustion` 3, `duplicate_pvc_mounts_hotel_reservation` 2, `auth_miss_mongodb` 2, `missing_service_hotel_reservation` 2, `scale_pod_zero_social_net` 2, `taint_no_toleration_social_network` 2, `duplicate_pvc_mounts_social_network` 2, `latent_sector_error` 2, `wrong_service_selector_hotel_reservation` 2, `configmap_drift_hotel_reservation` 1, `service_dns_resolution_failure_social_network` 1, `network_policy_block` 1, `missing_configmap_hotel_reservation` 1, `finalizer_deadlock_controller_hotel_reservation` 1, `init_container_dependency_hang_social_network` 1, `wrong_bin_usage` 1.

| Problem | Base (of 3) | A (of 3) |
|---|---|---|
| `auth_miss_mongodb` | 0 | 2 |
| `configmap_drift_hotel_reservation` | 1 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 1 | 3 |
| `file_descriptor_exhaustion` | 2 | 1 |
| `finalizer_deadlock_controller_hotel_reservation` | 1 | 0 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 2 | 0 |
| `missing_configmap_hotel_reservation` | 3 | 2 |
| `network_policy_block` | 0 | 1 |
| `scale_pod_zero_social_net` | 0 | 2 |
| `service_dns_resolution_failure_social_network` | 1 | 0 |
| `taint_no_toleration_social_network` | 1 | 3 |
| `wrong_bin_usage` | 3 | 2 |
| `wrong_service_selector_hotel_reservation` | 0 | 2 |
| (the other 16 problems: equal) | | |

### STRATUS vs A, E2E under GPT-5.4

- Cells (both sides): 90; discordant cells STRATUS better : A better = **12:11**, exact sign test p = 1.000.
- Problems where STRATUS has more passes : A has more : ties = **8:5:17**, exact sign test over problems p = 0.581.
- Wilcoxon signed-rank on the 30 per-problem differences: 13 nonzero, W+ = 44.5, W- = 46.5, exact two-sided p = 0.945.
- Difference in rate: +1.1 points; 95% bootstrap interval over problems (10,000 resamples, seed 20261119): [-11.1, +13.3].
- Concentration: the 23 discordant cells lie in 15 problems; the 5 problems with most carry 11. By problem (discordant cells): `readiness_probe_misconfiguration_hotel_reservation` 3, `configmap_drift_hotel_reservation` 2, `duplicate_pvc_mounts_hotel_reservation` 2, `missing_service_hotel_reservation` 2, `misconfig_app_hotel_res` 2, `missing_configmap_hotel_reservation` 2, `file_descriptor_exhaustion` 2, `taint_no_toleration_social_network` 1, `auth_miss_mongodb` 1, `duplicate_pvc_mounts_social_network` 1, `update_incompatible_correlated` 1, `network_policy_block` 1, `scale_pod_zero_social_net` 1, `init_container_dependency_hang_social_network` 1, `latent_sector_error` 1.

| Problem | STRATUS (of 3) | A (of 3) |
|---|---|---|
| `auth_miss_mongodb` | 3 | 2 |
| `configmap_drift_hotel_reservation` | 0 | 2 |
| `duplicate_pvc_mounts_hotel_reservation` | 1 | 3 |
| `duplicate_pvc_mounts_social_network` | 3 | 2 |
| `init_container_dependency_hang_social_network` | 3 | 2 |
| `latent_sector_error` | 1 | 0 |
| `missing_configmap_hotel_reservation` | 0 | 2 |
| `missing_service_hotel_reservation` | 0 | 2 |
| `network_policy_block` | 2 | 1 |
| `readiness_probe_misconfiguration_hotel_reservation` | 3 | 0 |
| `scale_pod_zero_social_net` | 3 | 2 |
| `taint_no_toleration_social_network` | 2 | 3 |
| `update_incompatible_correlated` | 1 | 0 |
| (the other 17 problems: equal) | | |

### Pooled 2x2, first judge x GPT-5.4, counted frozen diagnoses (all six arms)

| | GPT-5.4 pass | GPT-5.4 fail | total |
|---|---|---|---|
| first judge pass | 208 | 91 | 299 |
| first judge fail | 4 | 237 | 241 |
| total | 212 | 328 | 540 |

Agreement 445/540 (82%), Cohen's kappa 0.66. Disagreements: first judge pass / GPT-5.4 fail 91, the reverse 4. The 9 counted cells with no diagnosis text are in the fail/fail cell: the first judge failed every one of them (checked), and they count as a GPT-5.4 fail (never sent).

## 3. Sensitivity to reruns (mitigation vs A, cell-level sign test; problem level where every problem has three cells on both sides)

| Configuration | earliest valid (paper) | first attempt valid on both sides only | latest valid run per cell |
|---|---|---|---|
| A+cards+gate | 23:11, p = 0.058 (n = 90); problems 13:5:12, Wilcoxon p = 0.132 | 20:10, p = 0.099 (n = 81) | 20:12, p = 0.215 (n = 90); problems 12:7:11, Wilcoxon p = 0.311 |
| A+driver gate | 19:8, p = 0.052 (n = 90); problems 10:4:16, Wilcoxon p = 0.052 | 18:8, p = 0.076 (n = 80) | 17:8, p = 0.108 (n = 90); problems 10:5:15, Wilcoxon p = 0.111 |
| V5 | 21:7, p = 0.013 (n = 90); problems 12:4:14, Wilcoxon p = 0.045 | 20:7, p = 0.019 (n = 84) | 19:9, p = 0.087 (n = 90); problems 11:5:14, Wilcoxon p = 0.146 |
| Base | 14:13, p = 1.000 (n = 90); problems 8:7:15, Wilcoxon p = 0.959 | 12:11, p = 1.000 (n = 78) | 11:15, p = 0.557 (n = 90); problems 6:9:15, Wilcoxon p = 0.506 |
| STRATUS | 16:8, p = 0.152 (n = 90); problems 11:5:14, Wilcoxon p = 0.226 | 9:6, p = 0.607 (n = 54) | 18:10, p = 0.185 (n = 90); problems 11:7:12, Wilcoxon p = 0.289 |

Cells whose first attempt ended on infrastructure (dropped in the middle column): A 5, Base 10, STRATUS 35, A+cards+gate 4, A+driver gate 5, V5 1. Cells whose latest valid run differs from the earliest: A 15, Base 13, STRATUS 18, A+cards+gate 4, A+driver gate 8, V5 17.

## 4. Pairing: same machine and time gap between the two counted runs of a cell

Machine = the Lab's `run_by` field, shown with the same pseudonyms as `artifact-data/runs.csv` (`machine-4` is the cloud machine, the others are laptops). The records have no host name, so two machines of one person would look the same.

| Configuration vs A | cells on the same machine | time gap, days: median (min to max) |
|---|---|---|
| A+cards+gate | 5/90 | 1.4 (0.64 to 2.6) |
| A+driver gate | 6/90 | 1.4 (0.21 to 2.3) |
| V5 | 32/90 | 2.1 (1.27 to 3.1) |
| Base | 86/90 | 0.0 (0.00 to 1.1) |
| STRATUS | 77/90 | 0.0 (0.00 to 2.4) |

Counted runs per machine: A: machine-4 (cloud) 63, machine-2 16, machine-6 11; Base: machine-4 (cloud) 64, machine-2 15, machine-6 11; STRATUS: machine-4 (cloud) 71, machine-6 11, machine-2 8; A+cards+gate: machine-2 35, machine-5 18, machine-1 15, machine-6 13, machine-3 9; A+driver gate: machine-2 37, machine-5 16, machine-1 15, machine-6 12, machine-3 10; V5: machine-4 (cloud) 28, machine-2 27, machine-6 21, machine-3 8, machine-1 6.

## 5. Run accounting

Firestore `runs`: 3,391 documents by aggregation count; 3,391 read by the projected scan on 19 Nov 2026 01:47 EET. Buckets by the `experiment` field:

| Bucket | runs | experiments |
|---|---|---|
| development rounds 1-4 | 1,888 | 'Dev - Ladder R2 - main - first try' 775; 'Dev - R4 REF EXCAP FLOW - first try' 588; 'Dev - R3 Routing + STRATUS - first try' 291; 'Dev - Ladder R1 - M1 - first try' 234 |
| frozen experiments (all attempts, every label) | 792 | 'Final - Frozen 30 confirmation - first try' 462; 'Final - Frozen 30 V3 - first try' 209; 'Final - Frozen 30 V5 - first try' 121 |
| do-nothing calibration (dev and frozen) | 174 | 'Calibration - null agent - frozen 30 - second try' 112; 'Calibration - null agent - frozen 30 - first try' 38; 'Dev - Ladder R2 - null agent - first try' 24 |
| later development queues (v3 r4.1, V5 r5) | 240 | 'Dev - V3 r4.1 - first try' 195; 'Dev - V5 r5 - first try' 45 |
| everything else | 297 | 'Dev Analysis - A1 & A4 -  Second Try' 88; (no experiment name: None) 77; (no experiment name: '') 41; 'OpenAI4' 17; 'OpenAI5' 14; 'Dev - Blank-reply smoke - first try' 9; 'Test New Variants for R3 Second Try' 9; 'OpenAI3' 8; 'OpenAI1' 7; 'Test PSA' 5; 'Dev - Blank-reply smoke - Second try' 4; 'Test R3 3 Variants' 4; 'OpenAI2' 3; 'Dev - R3 Routing vs B2 - second try' 3; 'groq_qwen1' 3; 'Test New Variants for R3' 2; 'DEV - IS R3 Working ?' 1; 'Reliops-lab v2 test-3' 1; 'Test the new lab version' 1 |
| **total** | **3,391** | |

How rounds 1-4 were matched: by exact experiment name, one experiment per round: round 1: first ladder = 'Dev - Ladder R1 - M1 - first try' (234); round 2: scaffolds = 'Dev - Ladder R2 - main - first try' (775); round 3: knowledge, STRATUS = 'Dev - R3 Routing + STRATUS - first try' (291); round 4: knowledge variants = 'Dev - R4 REF EXCAP FLOW - first try' (588). Sum 1,888, not the paper's 1,807 (239 + 776 + 291 + 501). The paper's numbers come from Lab exports (union by run id, per the note at the top of paper.tex) taken while rounds were still running: round 4 has 588 runs now, the paper's 501 is the export of 14 Nov (`results/r4-review-2026-11-14.md`: "Lab export ..., 501 runs"); in Firestore the 501st round-4 run by time is at 2026-11-13T23:28:52Z, and 86 round-4 runs are from 14-15 Nov. Rounds 1 and 2 differ by 5 and 1 runs (234 vs 239, 775 vs 776); the export files are not in the repository, so which runs those are cannot be checked here. Runs with no experiment name (118, mostly 24-26 Oct and 4-5 Nov) are left in "everything else".

## 6. Model of the F30 STRATUS runs

`model_id` in the run records: all attempts {'gemini/gemini-3.5-flash-lite': 216}; counted cells {'gemini/gemini-3.5-flash-lite': 90}. This is the model the Lab passed to the STRATUS run (the same as every other arm).

