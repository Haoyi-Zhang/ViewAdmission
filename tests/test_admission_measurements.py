"""Saved current measurements must reconcile; no expensive test-time rerun."""
import copy
import csv
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from verify_admission_measurements import validate,table_tex

class PairedMeasurements(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'results/admission-paired'
        self.raw=json.loads((folder/'raw.json').read_text())
        with (folder/'summary.csv').open(newline='') as stream:
            self.summary=list(csv.DictReader(stream))
        self.environment=json.loads((folder/'environment.json').read_text())
        self.bindings=json.loads((folder/'source-inputs.json').read_text())
    def check(self):
        return validate(self.raw,self.summary,self.environment,self.bindings)
    def test_complete_source_bound_samples_and_medians(self):
        self.assertEqual(self.check()['measurement_processes'],432)
    def test_missing_duplicate_or_failed_sample_rejected(self):
        original=copy.deepcopy(self.raw)
        for mutation in ('missing','duplicate','not_served'):
            with self.subTest(mutation=mutation):
                self.raw=copy.deepcopy(original)
                if mutation=='missing':self.raw.pop()
                elif mutation=='duplicate':self.raw[-1]=self.raw[0]
                else:self.raw[0]['time']['accepted_and_served']=False
                with self.assertRaises(ValueError):self.check()
    def test_summary_nonfinite_or_wrong_median_rejected(self):
        for value in ('nan','inf','-1','123456'):
            with self.subTest(value=value):
                self.summary[0]['checker_ms']=value
                with self.assertRaises(ValueError):self.check()
    def test_input_binding_must_cover_every_measured_source(self):
        self.bindings['files'].pop(next(iter(self.bindings['files'])))
        with self.assertRaises(ValueError):self.check()
    def test_manuscript_table_is_derived_from_the_same_rows(self):
        text=table_tex(self.summary)
        self.assertEqual(text.count(r'\begin{table}'),1)
        self.assertEqual(text.count(r'\end{table}'),1)
        self.assertEqual(sum(text.count(' & '+name+' & ') for name in
            ('SQL-target','Structural','Sorted merge','Factorized')),12)
        row=next(r for r in self.summary if r['family']=='cartesian' and
                 int(r['n'])==128 and r['mode']=='factorized')
        self.assertIn(f"{float(row['checker_ms']):.2f} & {float(row['lifecycle_ms']):.2f}",text)

if __name__=='__main__':unittest.main()
