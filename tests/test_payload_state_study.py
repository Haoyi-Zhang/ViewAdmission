"""Reconcile bounded allocation evidence; never require a host-specific speedup."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from payload_state_study import inputs, source_bindings, table_tex, validate
from recovery.factorized import verify_streaming


class PayloadStateTests(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((ROOT / 'results/payload-state.json').read_text(encoding='utf-8'))

    def test_source_bound_complete_matrix_and_derived_medians(self):
        self.assertEqual(self.result['source_bindings'], source_bindings())
        self.assertEqual(validate(self.result['samples']), self.result['summary'])
        self.assertEqual(len(self.result['samples']), 18)

    def test_missing_duplicate_and_wrong_denominator_are_refused(self):
        for kind in ('missing', 'duplicate', 'count'):
            rows = copy.deepcopy(self.result['samples'])
            if kind == 'missing':
                rows.pop()
            elif kind == 'duplicate':
                rows[-1] = rows[0]
            else:
                rows[0]['candidate_rows'] += 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate(rows)

    def test_table_has_all_modes_sizes_and_no_performance_gate(self):
        table = table_tex(self.result['summary'])
        self.assertIn('Sorted merge (bytes)', table)
        self.assertIn('Factorized (bytes)', table)
        self.assertEqual(table.count(' & '), 8)

    def test_owned_asymmetric_input_is_an_exact_valid_bag_image(self):
        records, image = inputs(64)
        self.assertTrue(verify_streaming(records, 1, image))
        self.assertEqual(len(image['joined']), 64)
        self.assertEqual(image['grouped'], [[0, 64]])
