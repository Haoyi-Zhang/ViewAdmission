from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
import unittest

from recovery.algebra import encode_image, evaluate
from recovery.engine import guarded_recover, log_index, operands, replay
from recovery.factorized import (
    FIELD,
    FactorizedRejected,
    adaptive_two_term_collision,
    commit_image,
    finite_field_detection_counts,
    verify_factorized,
    verify_structural,
)
from recovery.fixtures import small


class FactorizedAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = log_index(small())
        self.records = [epoch.encode() for epoch in self.log.values()]
        self.image = encode_image(replay(self.log, 5))
        self.seed = bytes.fromhex("42" * 32)

    def admitted(self, image: dict, *, rounds: int = 2, q: int = FIELD):
        return verify_factorized(
            self.records,
            5,
            image,
            commitment=commit_image(image),
            seed=self.seed,
            rounds=rounds,
            q=q,
        )

    def test_valid_target_exact_and_factorized(self):
        self.assertTrue(verify_structural(self.records, 5, self.image))
        report = self.admitted(self.image)
        self.assertTrue(report.accepted)
        self.assertEqual(report.expected_join_pairs_enumerated, 0)
        self.assertEqual(report.rounds, 2)
        self.assertEqual(report.field_bits, 127)
        self.assertEqual(report.ideal_soundness_numerator, 9)
        self.assertEqual(report.ideal_soundness_denominator, FIELD ** 2)

    def test_every_component_mutation_is_rejected(self):
        for component in ("r", "s", "selection", "joined", "grouped"):
            with self.subTest(component=component):
                bad = deepcopy(self.image)
                bad[component][0][-1] += 1
                self.assertNotEqual(commit_image(bad), commit_image(self.image))
                with self.assertRaises(FactorizedRejected):
                    verify_structural(self.records, 5, bad)
                with self.assertRaises(FactorizedRejected):
                    self.admitted(bad)

    def test_missing_and_extra_join_rows_are_rejected(self):
        missing = deepcopy(self.image)
        missing["joined"].pop()
        extra = deepcopy(self.image)
        extra["joined"].append([99, 99, 99, 1])
        for bad in (missing, extra):
            with self.assertRaises(FactorizedRejected):
                verify_structural(self.records, 5, bad)
            with self.assertRaises(FactorizedRejected):
                self.admitted(bad)

    def test_commitment_and_seed_are_validated(self):
        with self.assertRaisesRegex(FactorizedRejected, "commitment"):
            verify_factorized(
                self.records,
                5,
                self.image,
                commitment="00" * 32,
                seed=self.seed,
            )
        with self.assertRaisesRegex(FactorizedRejected, "128 bits"):
            verify_factorized(
                self.records,
                5,
                self.image,
                commitment=commit_image(self.image),
                seed=b"short",
            )

    def test_malformed_authority_and_candidate_are_rejected(self):
        with self.assertRaises(FactorizedRejected):
            self.admitted({**self.image, "r": [[0, 1, 0]]})
        with self.assertRaises(FactorizedRejected):
            verify_factorized(
                self.records[1:],
                5,
                self.image,
                commitment=commit_image(self.image),
                seed=self.seed,
            )
        duplicate = self.records + [deepcopy(self.records[0])]
        self.assertTrue(
            verify_factorized(
                duplicate,
                5,
                self.image,
                commitment=commit_image(self.image),
                seed=self.seed,
            ).accepted
        )
        conflicting = deepcopy(self.records)
        conflict = deepcopy(conflicting[0])
        conflict["r"][0][-1] += 1
        conflicting.append(conflict)
        with self.assertRaises(FactorizedRejected):
            verify_factorized(
                conflicting,
                5,
                self.image,
                commitment=commit_image(self.image),
                seed=self.seed,
            )

    def test_small_field_refuses_noninjective_integer_envelope(self):
        with self.assertRaisesRegex(FactorizedRejected, "field"):
            self.admitted(self.image, q=5)

    def test_exact_small_field_controls(self):
        rows = finite_field_detection_counts(17)
        expected = {
            1: (17, 1),
            2: (17 ** 2, 17 ** 2 - 16 ** 2),
            3: (17 ** 3, 17 ** 3 - 16 ** 3),
        }
        for row in rows:
            total, undetected = expected[row["degree"]]
            self.assertEqual(row["assignments"], total)
            self.assertEqual(row["undetected"], undetected)
            self.assertLessEqual(undetected, row["degree"] * 17 ** (row["degree"] - 1))

    def test_post_challenge_adaptation_has_explicit_collision(self):
        control = adaptive_two_term_collision(self.seed, q=101)
        self.assertEqual(control["residual_nonzero"], 1)
        self.assertEqual(control["fingerprint"], 0)
        self.assertEqual(control["collision"], 1)

    def test_factorized_checker_does_not_import_producer_or_sql_checker(self):
        source = Path(__file__).resolve().parents[1] / "recovery" / "factorized.py"
        tree = ast.parse(source.read_text())
        forbidden = {
            "algebra",
            "checker",
            "engine",
            "recovery.algebra",
            "recovery.checker",
            "recovery.engine",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module, forbidden)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name, forbidden)

    def test_guarded_factorized_admission_falls_back(self):
        # The producer API is tested after its factorized admission mode is wired.
        target, fallback = guarded_recover(
            self.log,
            5,
            [1, 3, 5],
            [2, 4],
            evaluate(*operands(self.log, [1, 3, 5], [2, 4])),
            admission="factorized",
            seed=self.seed,
            fallback_seed=bytes.fromhex("43" * 32),
        )
        self.assertFalse(fallback)
        self.assertEqual(target["recovered"], self.image)

        poisoned = replay(self.log, 5)
        poisoned.joined[(99, 99, 99)] = 1
        target, fallback = guarded_recover(
            self.log,
            5,
            [1, 3, 5],
            [2, 4],
            poisoned,
            admission="factorized",
            seed=self.seed,
            fallback_seed=bytes.fromhex("43" * 32),
        )
        self.assertTrue(fallback)
        self.assertEqual(target["recovered"], self.image)


if __name__ == "__main__":
    unittest.main()
