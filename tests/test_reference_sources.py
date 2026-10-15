"""Check that the STREAM source record identifies the cited journal article."""
import csv
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class ReferenceSourceTests(unittest.TestCase):
    def test_stream_record_identifies_journal_article(self):
        with (ROOT/'external_resources.csv').open(encoding='utf-8',newline='') as handle:
            rows=[row for row in csv.DictReader(handle) if row['key']=='stream']
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual(row['title'],'{STREAM}: The Stanford Stream Data Manager')
        self.assertEqual(row['source_url'],'https://courses.cs.washington.edu/courses/cse550/22au/papers/CSE550.Stream.pdf')
        self.assertIn('The STREAM Group',row['scope'])
        self.assertIn('Data Engineering Bulletin',row['scope'])

if __name__=='__main__':
    unittest.main()
