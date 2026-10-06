"""Narrow regressions for arithmetic-control coverage, not empirical soundness."""
from copy import deepcopy
from pathlib import Path
import unittest
from verify_results import read_rows, validate_soundness

BASE = Path(__file__).resolve().parents[1]


class SoundnessResultTests(unittest.TestCase):
    def setUp(self):
        self.rows = read_rows(BASE / "results", "soundness")

    def test_saved_control_domain(self):
        exact, adaptive = validate_soundness(self.rows)
        self.assertEqual(sum(int(r["assignments"]) for r in exact), 5219)
        self.assertEqual(len(adaptive), 32)

    def test_duplicate_degree_cannot_replace_join_control(self):
        self.rows[2] = deepcopy(self.rows[0])
        with self.assertRaisesRegex(ValueError, "identity/uniqueness"):
            validate_soundness(self.rows)

    def test_case_must_have_its_declared_degree(self):
        self.rows[2].update(degree="1", assignments="17", undetected="1", detected="16")
        with self.assertRaisesRegex(ValueError, "degree"):
            validate_soundness(self.rows)

    def test_duplicate_adaptive_identity(self):
        self.rows[-1]["case"] = "0"
        with self.assertRaisesRegex(ValueError, "identity/uniqueness"):
            validate_soundness(self.rows)

    def test_missing_case(self):
        self.rows.pop()
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_soundness(self.rows)

    def test_exact_arithmetic_columns(self):
        for name in ("detected", "bound_numerator", "bound_denominator", "rounds",
                     "field", "residual_nonzero", "collision_constructed"):
            with self.subTest(name=name):
                bad = deepcopy(self.rows)
                bad[2][name] = "-1"
                with self.assertRaises(ValueError):
                    validate_soundness(bad)

    def test_adaptive_arithmetic_columns(self):
        for name in ("degree", "rounds", "field", "assignments", "detected",
                     "undetected", "bound_numerator", "bound_denominator",
                     "residual_nonzero", "fingerprint_zero", "collision_constructed"):
            with self.subTest(name=name):
                bad = deepcopy(self.rows)
                bad[3][name] = "-1"
                with self.assertRaises(ValueError):
                    validate_soundness(bad)


if __name__ == "__main__":
    unittest.main()
