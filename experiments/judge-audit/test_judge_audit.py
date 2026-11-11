import csv, random, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
import judge_audit as ja

COLS = ["run_id", "problem_id", "config_label", "judge_model_id", "diagnosis_pass", "mitigation_pass", "e2e_pass", "diagnosis_text"]


def fake(path, configs, per=40, seed=1):
    rng = random.Random(seed)
    rows = []
    for c in configs:
        for i in range(per):
            rows.append({"run_id": f"{c}-{i}", "problem_id": f"p{i % 12}", "config_label": c, "judge_model_id": "j",
                         "diagnosis_pass": str(rng.random() < .4), "mitigation_pass": "True", "e2e_pass": "False",
                         "diagnosis_text": f"diag {c} {i}"})
    rows.append({"run_id": "floor", "problem_id": "p1", "config_label": "dumb-baseline", "judge_model_id": "j",
                 "diagnosis_pass": "False", "diagnosis_text": "x"})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)


class AuditTests(unittest.TestCase):
    def test_draw_and_score(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            fake(t / "r3.csv", ["A", "B", "C", "D"]); fake(t / "r2.csv", ["X", "Y"], seed=2)
            args = ["draw", "--r3", str(t / "r3.csv"), "--r2", str(t / "r2.csv"), "--labelers", "Om,No,An", "--out", str(t / "o")]
            sys.argv = ["x"] + args; ja.main()
            key = ja.read_csv(t / "o/key.csv")
            self.assertEqual(len(key), 60)
            self.assertEqual(sum(k["anchor"] == "1" for k in key), 15)
            self.assertFalse(any("dumb" in k["config_label"] for k in key))
            for st in {k["stratum"] for k in key}:
                rows = [k for k in key if k["stratum"] == st]
                self.assertEqual(len(rows), 12)
                self.assertEqual(sum(k["judge_diagnosis_pass"] == "True" for k in rows), 6)
                per_problem = {}
                for k in rows: per_problem[k["problem_id"]] = per_problem.get(k["problem_id"], 0) + 1
                self.assertLessEqual(max(per_problem.values()), 2)
            for w in ("Om", "No", "An"):
                sheet = ja.read_csv(t / f"o/sheet_{w}.csv")
                self.assertEqual(len(sheet), 30)
                self.assertNotIn("config_label", sheet[0]); self.assertNotIn("judge_diagnosis_pass", sheet[0])
            # a second draw with the same seed is identical
            sys.argv = ["x"] + args[:-1] + [str(t / "o2")]; ja.main()
            self.assertEqual((t / "o/key.csv").read_text(), (t / "o2/key.csv").read_text())
            # simulate labelers who agree with the judge 90% of the time
            rng = random.Random(5); byid = {k["item_id"]: k for k in key}
            for w in ("Om", "No", "An"):
                rows = ja.read_csv(t / f"o/sheet_{w}.csv")
                for r in rows:
                    j = byid[r["item_id"]]["judge_diagnosis_pass"] == "True"
                    r["overall_correct"] = "Y" if (j if rng.random() < .9 else not j) else "N"
                ja.write_csv(t / f"o/filled_{w}.csv", ja.SHEET_COLS, rows)
            sys.argv = ["x", "score", "--key", str(t / "o/key.csv"), "--sheets"] + [str(t / f"o/filled_{w}.csv") for w in ("Om", "No", "An")]
            ja.main()


if __name__ == "__main__":
    unittest.main()
