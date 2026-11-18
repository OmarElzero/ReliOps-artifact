"""Unit tests for sim/frozen_followups.py (no Firestore): python3 -I sim/test_frozen_followups.py"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frozen_followups as ff


def run(arm, p, rep, d, m, t="2026-11-17T10:00:00Z", rid=None, reason="", text="diag"):
    return {"config_label": arm, "problem_id": p, "repeat_index": rep, "timestamp_utc": t, "run_id": rid or f"{arm}-{p}-{rep}-{t}",
            "incomplete_reason": reason, "diagnosis_text": text,
            "row": {"Diagnosis.success": str(d), "Mitigation.success": str(m)}}


class Tests(unittest.TestCase):
    def test_earliest_valid_run_counts_and_infrastructure_runs_do_not(self):
        rows = [run("F30 A", "p1", 0, False, False, t="2026-11-17T09:00:00Z", reason="Model key out of quota (429)."),
                run("F30 A", "p1", 0, True, True, t="2026-11-17T10:00:00Z", rid="first"),
                run("F30 A", "p1", 0, False, False, t="2026-11-17T11:00:00Z", rid="later")]
        c = ff.cells(rows, {})
        self.assertEqual(list(c), [("F30 A", "p1", 0)])
        self.assertEqual(c[("F30 A", "p1", 0)]["run_id"], "first")

    def test_calibration_drops_problems_the_null_agent_passes(self):
        rows = []
        for p, a_m, v_m in (("p1", False, True), ("p2", False, True), ("p3", True, True)):
            for rep in range(3):
                rows += [run("F30 A", p, rep, False, a_m), run("F30 V5", p, rep, False, v_m)]
        null = [{"problem_id": "p3", "row": {"Mitigation.success": "True"}, "incomplete_reason": ""},
                {"problem_id": "p1", "row": {"Mitigation.success": "False"}, "incomplete_reason": ""}]
        text = ff.calibration_report(null, ff.cells(rows, {}), ["p1", "p2", "p3"])
        self.assertIn("passes with no fix (1): p3", text)
        self.assertIn("no valid null run (1): p2", text)
        self.assertIn("| F30 V5 | 9/9 (100%) | 6/6 (100%) | 6:0, p = 0.0312 | 6:0, p = 0.0312 |", text)

    def test_holm_thresholds(self):
        h = ff.holm({"a": 0.01254, "b": 0.052, "c": 0.058, "d": 0.83})
        self.assertEqual(h["a"], (0.0125, False))
        h = ff.holm({"a": 0.010, "b": 0.020})
        self.assertEqual((h["a"][1], h["b"][1]), (True, True))

    def test_draw_takes_only_disputed_and_is_reproducible(self):
        rows, rj = [], {}
        for i in range(60):
            r = run("F30 A", f"p{i % 30}", i // 30, d=(i % 2 == 0), m=False, rid=f"r{i}")
            rows.append(r)
            rj[f"r{i}"] = (i % 2 == 0) if i < 10 else (i % 2 == 1)      # 50 disputed, 10 agreed
        c = ff.cells(rows, rj)
        items, n = ff.draw(c)
        self.assertEqual((n, len(items)), (50, 40))
        self.assertTrue(all(it["judge1"] != it["judge2"] for it in items))
        self.assertEqual([it["run_id"] for it in items], [it["run_id"] for it in ff.draw(c)[0]])

    def test_score_counts_who_the_people_side_with(self):
        key = [{"item": "F01", "judge1": True, "judge2": False}, {"item": "F02", "judge1": False, "judge2": True},
               {"item": "F03", "judge1": True, "judge2": False}]
        sheets = {"A": [{"item": "F01", "correct": "Y"}, {"item": "F02", "correct": "Y"}, {"item": "F03", "correct": "N"}],
                  "B": [{"item": "F01", "correct": "Y"}, {"item": "F02", "correct": "N"}, {"item": "F03", "correct": "N"}]}
        text = ff.score(key, sheets)
        self.assertIn("Labelers agree on 2 of 3", text)
        self.assertIn("sides with the first judge on 1 and with gpt-5.4 on 1", text)


if __name__ == "__main__":
    unittest.main()
