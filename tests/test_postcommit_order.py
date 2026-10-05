"""Focused order and residual-scope regressions; no benchmark execution."""
import unittest
from unittest.mock import patch

from recovery import engine, factorized
from recovery.algebra import Image, evaluate, join, group, plus, neg


class PostCommitOrder(unittest.TestCase):
    def run_order(self, fallback):
        events = []
        draws = iter((b'a' * 32, b'b' * 32))
        candidate = {'recovered': {}}

        def construct(*args):
            events.append('candidate')
            return candidate

        def commit(image):
            events.append('commit')
            return 'local-test-commitment'

        def fresh():
            events.append('entropy')
            return next(draws)

        def check(*args, **kwargs):
            events.append('check')
            if fallback and events.count('check') == 1:
                raise factorized.FactorizedRejected('local rejection control')

        with patch.object(engine, 'certificate', side_effect=construct), \
             patch.object(factorized, 'commit_image', side_effect=commit), \
             patch.object(factorized, 'fresh_seed', side_effect=fresh), \
             patch.object(factorized, 'verify_factorized', side_effect=check):
            _, used = engine.guarded_recover({}, 0, [], [], evaluate({}, {}), admission='factorized')
        self.assertEqual(used, fallback)
        self.assertEqual(events, ['candidate', 'commit', 'entropy', 'check'] * (2 if fallback else 1))

    def test_default_candidate_order(self):
        self.run_order(False)

    def test_default_fallback_order(self):
        self.run_order(True)

    def test_equal_normalized_test_seeds_rejected(self):
        with self.assertRaises(ValueError):
            engine.guarded_recover({}, 0, [], [], evaluate({}, {}), admission='factorized',
                                   seed=b'a' * 32, fallback_seed=(b'a' * 32).hex())

    def test_default_candidate_passes_real_admission(self):
        log = engine.log_index([engine.Epoch(1, ((0, 0, 1),), ((0, 0, 1),))])
        candidate, used = engine.guarded_recover(log, 1, [], [], evaluate({}, {}), admission='factorized')
        self.assertFalse(used)
        factorized.verify_structural([log[1].encode()], 1, candidate['recovered'])

    def test_base_error_propagates_to_derived_components(self):
        log = engine.log_index([engine.Epoch(1, ((0, 0, 1),), ((0, 0, 1),))])
        old = Image({(0, 0): 1}, {}, {}, {}, {})
        new = engine.retarget(log, 1, [], [], old)
        truth = engine.replay(log, 1)
        self.assertEqual(plus(new.r, neg(truth.r)), {(0, 0): 1})
        extra = join({(0, 0): 1}, {(0, 0): 1})
        self.assertEqual(plus(new.joined, neg(truth.joined)), extra)
        self.assertEqual(plus(new.grouped, neg(truth.grouped)), group(extra))

    def test_correct_bases_preserve_join_error(self):
        log = engine.log_index([engine.Epoch(1, ((0, 0, 1),), ((0, 0, 1),))])
        residual = {(5, 6, 7): 1}
        old = Image({}, {}, {}, residual, {})
        new = engine.retarget(log, 1, [], [], old)
        self.assertEqual(plus(new.joined, neg(engine.replay(log, 1).joined)), residual)


if __name__ == '__main__':
    unittest.main()
