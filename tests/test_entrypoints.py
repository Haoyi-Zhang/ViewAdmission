"""Entry-point regressions for constrained runners and end-to-end gating."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
class EntryPointTests(unittest.TestCase):
    def test_import_reproduce_does_not_raise_hard_limit(self):
        code = "import resource; resource.setrlimit(resource.RLIMIT_CPU,(10,10)); import reproduce; assert resource.getrlimit(resource.RLIMIT_CPU)==(10,10)"
        result=subprocess.run([sys.executable,"-c",code],cwd=BASE,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_poisoned_demo_uses_store_admission(self):
        for mode in ("structural","factorized","target","both"):
            result=subprocess.run([sys.executable,"demo.py","--poison","--admission",mode],cwd=BASE,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            payload=json.loads(result.stdout)
            self.assertTrue(payload["fallback_used"])
            self.assertEqual(payload["published"]["metadata"]["target"],5)

    def test_bad_comparison_path_fails_before_experiments(self):
        # CLI paths follow the caller's directory, including project-root use.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing_file = root / "not-a-directory"
            existing_file.write_text("not a result packet")
            for reference in ("missing-results", str(existing_file)):
                out = root / "fresh-output"
                result = subprocess.run(
                    [sys.executable, str(BASE / "run_complete.py"),
                     "--out", str(out), "--compare", reference],
                    cwd=root, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("comparison directory does not exist", result.stderr)
                self.assertFalse(out.exists())
