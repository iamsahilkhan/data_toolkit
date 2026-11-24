import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze import auroc, kappa  # noqa: E402


class TestKappa(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertEqual(kappa(["yes", "no", "yes"], ["yes", "no", "yes"]), 1.0)

    def test_chance_level(self):
        self.assertAlmostEqual(kappa(["yes", "yes", "no", "no"], ["yes", "no", "yes", "no"]), 0.0)

    def test_empty(self):
        self.assertNotEqual(kappa([], []), kappa([], []))  # nan


class TestAuroc(unittest.TestCase):
    def test_perfect_separation(self):
        self.assertEqual(auroc([0.9, 0.8, 0.1, 0.2], [True, True, False, False]), 1.0)

    def test_ties_count_half(self):
        self.assertEqual(auroc([0.5, 0.5], [True, False]), 0.5)


class TestReport(unittest.TestCase):
    def test_runs_on_full_labels(self):
        items = json.load(open(ROOT / "data" / "items.json"))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "labels.csv"
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["id", "verdict", "rule", "confidence", "note", "seconds", "labelled_at"])
                for i, it in enumerate(items):
                    v = "yes" if i % 3 == 0 else "no"
                    w.writerow([it["id"], v, "P2" if v == "yes" else "", "high", "", 30, "2026-01-01"])
            out = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze.py"), str(path)],
                                 capture_output=True, text=True, check=True).stdout
        self.assertIn("Same verdict on hidden repeats", out)
        self.assertIn("| Median seconds per conversation | 30 |", out)


class TestGold(unittest.TestCase):
    def test_reference_against_itself(self):
        ref = ROOT / "reference" / "reference_labels.csv"
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "analyze.py"), str(ref), "--gold", str(ref)],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("| Same verdict | 100 of 100 (100%), kappa 1.00 |", out)


class TestCompare(unittest.TestCase):
    def test_policy_versions(self):
        ref = ROOT / "reference"
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "compare.py"), str(ref / "reference_labels.csv"),
                              str(ref / "reference_labels_v2.csv")],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("| borderline | 35 | 2 |", out)


class TestSeverity(unittest.TestCase):
    def test_every_flagged_label_is_graded(self):
        for name in ("reference_labels.csv", "reference_labels_v2.csv"):
            for r in csv.DictReader(open(ROOT / "reference" / name, encoding="utf-8")):
                if r["verdict"] == "no":
                    self.assertEqual(r["severity"], "", r["id"])
                else:
                    self.assertIn(r["severity"], {"1", "2", "3"}, r["id"])


class TestBuildApp(unittest.TestCase):
    def test_app_has_every_item_and_v2_controls(self):
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_app.py")], check=True,
                       capture_output=True, cwd=tempfile.gettempdir())
        html = (ROOT / "app" / "label.html").read_text()
        for it in json.load(open(ROOT / "data" / "items.json")):
            self.assertIn('"' + it["id"] + '"', html)
        self.assertIn('data-v="P7"', html)
        self.assertIn('id="sev"', html)


if __name__ == "__main__":
    unittest.main()
