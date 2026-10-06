"""Raw parsing costs differ from deduplicated prefix aggregation costs."""
from copy import deepcopy
import unittest
from recovery.factorized import (FactorizedRejected, commit_image,
                                 verify_factorized, verify_structural)

EMPTY = {name: [] for name in ("r", "s", "selection", "joined", "grouped")}


class AuthorityScanTests(unittest.TestCase):
    def checkers(self, records, h=0):
        yield lambda: verify_structural(records, h, EMPTY)
        yield lambda: verify_factorized(records, h, EMPTY,
            commitment=commit_image(EMPTY), seed=b"s" * 32)

    def test_repeated_empty_epochs_are_parsed_but_deduplicated(self):
        for n in (1, 8, 64):
            records = [{"id": 1, "r": [], "s": []} for _ in range(n)]
            for check in self.checkers(records, 1):
                self.assertTrue(check())
            report = list(self.checkers(records, 1))[1]()
            self.assertEqual(report.authoritative_epoch_count, 1)
            self.assertEqual(report.authoritative_prefix_rows, 0)

    def test_unacknowledged_rows_are_parsed_not_aggregated(self):
        for n in (1, 8, 64):
            records = [{"id": 1, "r": [[0, i, 1] for i in range(n)], "s": []}]
            report = list(self.checkers(records))[1]()
            self.assertEqual(report.authoritative_prefix_rows, 0)
            malformed = deepcopy(records)
            malformed[0]["r"][-1][-1] = True
            for check in self.checkers(malformed):
                with self.assertRaises(FactorizedRejected):
                    check()

    def test_conflicting_empty_duplicate_is_not_ignored(self):
        records = [{"id": 1, "r": [], "s": []},
                   {"id": 1, "r": [[0, 0, 1]], "s": []}]
        for check in self.checkers(records):
            with self.assertRaises(FactorizedRejected):
                check()


if __name__ == "__main__":
    unittest.main()
