import unittest

from frozen_recompute import ARMS, cells, holm, report, sign_test


def run(rid, arm, p, rep, t, d="True", m="True", reason=""):
    exp = "Final - Frozen 30 V5 - first try" if arm == "F30 V5" else "Final - Frozen 30 confirmation - first try"
    return {"run_id": rid, "experiment": exp, "arm": arm, "problem_id": p, "repeat": str(rep), "started_utc": t,
            "diagnosis_judge1": d, "mitigation": m, "incomplete_reason": reason}


class T(unittest.TestCase):
    def test_sign_test_matches_paper(self):
        self.assertAlmostEqual(sign_test(21, 7), 0.012540, places=5)
        self.assertEqual(sign_test(0, 0), 1.0)

    def test_holm_step_down(self):
        h = holm({"a": 0.01254, "b": 0.052, "c": 0.058, "d": 0.83})
        self.assertEqual(h["a"][1], 0.0125)
        self.assertFalse(h["a"][2])
        self.assertFalse(h["d"][2])  # stops at the first miss
        h2 = holm({"a": 0.001, "b": 0.02, "c": 0.5})
        self.assertTrue(h2["a"][2] and h2["b"][2] and not h2["c"][2])

    def test_earliest_valid_infra_and_duplicates(self):
        runs = [run("1", "F30 A", "p1", 0, "2026-11-16T01", reason="429 RateLimit hit"),
                run("2", "F30 A", "p1", 0, "2026-11-16T02", d="False"),
                run("3", "F30 A", "p1", 0, "2026-11-16T03"),
                run("4", "F30 A", "p2", 0, "2026-11-16T04", d="", m="", reason="agent hit step cap")]
        by, att, lost, dup = cells(runs, {"2": True})
        c = by["F30 A"]
        self.assertEqual(att["F30 A"], 4)
        self.assertEqual(lost["F30 A"], 1)
        self.assertEqual(dup["F30 A"], 1)
        self.assertEqual(c[("p1", "0")], {"d": False, "m": True, "e": False, "d2": True, "e2": True})
        self.assertFalse(c[("p2", "0")]["m"])  # non-infrastructure incomplete run counts as a failure

    def test_arm_counts_only_in_its_own_experiment(self):
        stray = dict(run("9", "F30 A", "p1", 0, "2026-11-16T00"), experiment="Final - Frozen 30 V3 - first try")
        by, att, _, _ = cells([stray, run("1", "F30 A", "p1", 0, "2026-11-16T01")], {})
        self.assertEqual(att["F30 A"], 1)

    def test_calibration_uses_second_try_only(self):
        null = [{"run_id": "n1", "experiment": "Calibration - null agent - frozen 30 - first try", "arm": "R2 NULL",
                 "problem_id": "p1", "mitigation": "True", "incomplete_reason": ""},
                {"run_id": "n2", "experiment": "Calibration - null agent - frozen 30 - second try", "arm": "R2 NULL",
                 "problem_id": "p1", "mitigation": "False", "incomplete_reason": ""}]
        text = report([run("1", "F30 A", "p1", 0, "t1")] + null, {})
        self.assertIn("passes with no fix: 0.", text)

    def test_report_runs(self):
        runs = [run(str(i), a, f"p{i}", 0, f"t{i}") for i, a in enumerate(ARMS)]
        self.assertIn("Holm over the four primary tests", report(runs, {}))


if __name__ == "__main__":
    unittest.main()
