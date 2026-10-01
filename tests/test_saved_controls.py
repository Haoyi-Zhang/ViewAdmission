"""Saved-result validation must fail on corrupted scientific evidence."""
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from verify_results import CONTROL_STAGES, validate_controls

BASE = Path(__file__).resolve().parents[1]

class SavedControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in (*[s + '.csv' for s in CONTROL_STAGES], 'protocol_summary.json'):
            shutil.copyfile(BASE/'results'/name, self.root/name)
    def tearDown(self):
        self.tmp.cleanup()
    def change(self, name, edit):
        path = self.root/(name+'.csv')
        with path.open(newline='') as stream:
            reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
        edit(rows)
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
    def test_saved_controls_pass(self):
        self.assertEqual(validate_controls(self.root)['protocol_controls'], 63)
    def test_failed_rejection_is_rejected(self):
        self.change('protocol_controls', lambda rows: rows[0].update(rejected='0'))
        with self.assertRaises(ValueError): validate_controls(self.root)
    def test_duplicate_case_is_rejected(self):
        self.change('domain_controls', lambda rows: rows.__setitem__(1, dict(rows[0])))
        with self.assertRaises(ValueError): validate_controls(self.root)
    def test_missing_mutant_is_rejected(self):
        self.change('tag_controls', lambda rows: rows[0].update(weakened_behavior_observed='0'))
        with self.assertRaises(ValueError): validate_controls(self.root)
    def test_hidden_cartesian_rows_are_rejected(self):
        self.change('memory_controls', lambda rows: rows[0].update(candidate_join_rows='0'))
        with self.assertRaises(ValueError): validate_controls(self.root)
    def test_wrong_probability_denominator_is_rejected(self):
        path = self.root/'protocol_summary.json'; data = json.loads(path.read_text())
        data['exact_probability_denominator'] = 2**254
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError): validate_controls(self.root)
