# Development set (dev-12)

Twelve problems for building and tuning the agent. They are disjoint from the frozen 30
(`first-30.csv`): no (fault type, target) pair appears in both. Rules are in `docs/plan/03-testing-plan.md` §4a.

Selected 30 Oct 2026 and pinned in `pins.json`. Every ID was checked against the SREGym registry
(`sregym/conductor/problems/registry.py`, clone at commit `d19d6f5`) and against the catalogue
(`Problem List.md`). Difficulty is left `unrated` on purpose: no estimate exists yet, and one made up now would
look like data.

## How the twelve were chosen

1. Start from the registered SREGym problems outside the frozen 30.
2. Keep problems on the small apps (hotel-reservation, social-network). Anything on Astronomy Shop is out: it
   does not fit the team's machines (`docs/envs/sregym.md`).
3. Cover the fault classes present in the 30, one to three per class, preferring fault types that are not in
   the 30.
4. Where the only candidate shares a fault type with a frozen problem, keep it and record it in
   `seen_type_in_30`, so the final results can report "seen type" and "unseen type" separately.

## Known gaps and risks

- **Correlated failures:** no registered candidate on a small app outside the 30 (`faulty_image_correlated` is
  retired as saturated; `kubelet_crash` runs on Astronomy Shop). The class has no dev problem.
- **`gc_capacity_degradation`** runs on the Blueprint variant of hotel-reservation. It has not been run on our
  machines. If it does not fit, swap in a reserve (below).
- **Seen types:** #1 (same fault type as frozen #15), #10 (same base class as frozen #30). Rows 3 and 6 are
  related to #3 and #23 but are different faults.
- **Not validated yet:** none of the twelve has been run. Validation is the plumbing check in
  `docs/plan/11-sprint-to-13-nov.md` (step 2).

## Reserves (named before any result exists)

If a dev problem fails validation, replace it with the next reserve in this order, never with a problem chosen
after looking at agent results:

1. `service_port_conflict_hotel_reservation`
2. `wrong_dns_policy_social_network`
3. `liveness_probe_too_aggressive_social_network`
4. `rolling_update_misconfigured_hotel_reservation` (same fault type as frozen #14, other target)
