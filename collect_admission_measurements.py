"""Collect a fresh source-bound paired study without replacing retained results.

The unchanged benchmark owns all 432 measurement children. This wrapper captures
the measured source/inputs before and after, records the actual local environment,
and validates the completed 108 paired samples before reporting success.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys

from verify_admission_measurements import verify_saved

ROOT = Path(__file__).resolve().parent


def normalized_digest(path):
    return hashlib.sha256(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()


def source_inputs(root=ROOT):
    paths = [root / "admission_benchmark.py", *sorted((root / "recovery").glob("*.py")),
             *(root / "inputs" / f"generated-{n}.json" for n in (16, 64, 256))]
    return {p.relative_to(root).as_posix(): normalized_digest(p) for p in paths}


def finish_collection(folder, before, after, started, *, root=ROOT):
    if before != after:
        raise ValueError("Measured source/input changed during collection")
    environment_path = folder / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    raw = json.loads((folder / "raw.json").read_text(encoding="utf-8"))
    if len(raw) != 108 or any(set(("checker-time", "time", "aux", "lifecycle")) - set(r) for r in raw):
        raise ValueError("Incomplete paired collection")
    bindings = {"normalization": "UTF-8/LF", "files": before,
                "collection_driver": {"file": "collect_admission_measurements.py",
                                      "digest": normalized_digest(root / "collect_admission_measurements.py")}}
    environment.update(started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                       cpu=platform.processor(), sqlite=sqlite3.sqlite_version,
                       measurement_processes=4 * len(raw), paired_repetitions=len(raw),
                       workload_mode_combinations=len({(r["family"], r["n"], r["mode"]) for r in raw}),
                       source_binding="source-inputs.json", source_inputs_unchanged=True,
                       resource_protocol="sequential fresh children; no exclusive host claim")
    environment_path.write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")
    (folder / "source-inputs.json").write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
    return verify_saved(folder=folder, root=root)


def collect(folder, *, root=ROOT):
    if folder.exists():
        raise ValueError("Choose a new output directory; retained results are not overwritten")
    before = source_inputs(root)
    started = datetime.now(timezone.utc).isoformat()
    subprocess.run([sys.executable, "-B", str(root / "admission_benchmark.py"),
                    "--out", str(folder.resolve()), "--repeats", "3"],
                   cwd=root, check=True, timeout=900)
    return finish_collection(folder, before, source_inputs(root), started, root=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(collect(args.out)))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Collection incomplete: {error}\n")


if __name__ == "__main__":
    main()
