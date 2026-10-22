"""Collection metadata and alternate output paths, without rerunning timings."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collect_admission_measurements import collect, finish_collection, source_inputs
from verify_admission_measurements import verify_saved


class AdmissionCollection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name) / "paired"
        shutil.copytree(ROOT / "results/admission-paired", self.folder)

    def test_alternate_directory_reconciles_retained_fixture(self):
        self.assertEqual(verify_saved(folder=self.folder)["samples"], 108)

    def test_collection_metadata_and_driver_binding(self):
        bindings = source_inputs()
        result = finish_collection(self.folder, bindings, bindings, "unit-test fixture")
        self.assertTrue(result["matched"])
        environment = json.loads((self.folder / "environment.json").read_text())
        self.assertEqual(environment["measurement_processes"], 432)
        self.assertEqual(environment["workload_mode_combinations"], 36)
        self.assertTrue(environment["source_inputs_unchanged"])
        self.assertIn("collection_driver", json.loads((self.folder / "source-inputs.json").read_text()))

    def test_source_change_rejected_before_receipt_update(self):
        before = source_inputs()
        after = dict(before, admission_benchmark="changed")
        original = (self.folder / "environment.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "changed during collection"):
            finish_collection(self.folder, before, after, "unit-test fixture")
        self.assertEqual((self.folder / "environment.json").read_bytes(), original)

    def test_existing_output_never_starts_benchmark(self):
        with patch("collect_admission_measurements.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "new output"):
                collect(self.folder)
            run.assert_not_called()

    def test_incomplete_collection_is_not_finalized(self):
        raw = json.loads((self.folder / "raw.json").read_text())
        (self.folder / "raw.json").write_text(json.dumps(raw[:-1]))
        with self.assertRaisesRegex(ValueError, "Incomplete paired"):
            finish_collection(self.folder, source_inputs(), source_inputs(), "unit-test fixture")

    def test_changed_collection_driver_is_rejected(self):
        bindings = source_inputs()
        finish_collection(self.folder, bindings, bindings, "unit-test fixture")
        path = self.folder / "source-inputs.json"
        record = json.loads(path.read_text())
        record["collection_driver"]["digest"] = "0" * 64
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "Collection driver changed"):
            verify_saved(folder=self.folder)


if __name__ == "__main__":
    unittest.main()
