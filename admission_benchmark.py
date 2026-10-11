#!/usr/bin/env python3
"""Paired synthetic admission diagnostics, including the real Store lifecycle.

Timing and allocation runs are separate and each uses a fresh child process.
Python allocation tracing includes input construction, producer, authority copy,
candidate snapshots, all durable objects, publication and service. Peak RSS also
includes interpreter/native allocation; it is not interchangeable with tracing.
No equation memoization, network service, external dataset or target is used.
"""
from __future__ import annotations
import argparse
import csv
import gc
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

from recovery.algebra import evaluate
from recovery.engine import Epoch, certificate, log_index
from recovery.factorized import commit_image, verify_factorized, verify_structural, verify_streaming
from recovery.checker import verify_replay
from recovery.publication import Store, PARTS

BASE = Path(__file__).resolve().parent
MODES = ("target", "structural", "streaming", "factorized")


def peak_rss_bytes():
    if os.name != "nt":
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value if sys.platform == "darwin" else value * 1024
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
             "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
             "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return counters.PeakWorkingSetSize


def records_for(family, n):
    if family == "generated":
        return json.loads((BASE / "inputs" / f"generated-{n}.json").read_text())
    if family == "cartesian":
        return [{"id": 1, "r": [[0, i, 1] for i in range(n)],
                 "s": [[0, i, 1] for i in range(n)]}]
    if family == "cancellation":
        return [
            {"id": 1, "r": [row for i in range(n) for row in ([i, i, 1], [i, i, -1])],
             "s": [row for i in range(n) for row in ([i, i, 1], [i, i, -1])]}]
    raise ValueError("unknown synthetic family")


def check_candidate(mode, records, h, image):
    if mode == "factorized":
        return verify_factorized(records, h, image, commitment=commit_image(image), seed=b"owned-benchmark" * 3)
    return {"target": verify_replay, "structural": verify_structural,
            "streaming": verify_streaming}[mode](records, h, image)


def run_child(family, n, mode, measure):
    gc.collect()
    traced = measure == "lifecycle"
    if measure == "lifecycle": tracemalloc.start()
    started = time.perf_counter_ns()
    phases = []
    def checkpoint(phase):
        current, peak = tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (0, 0)
        phases.append({"phase": phase, "elapsed_ns": time.perf_counter_ns() - started,
                       "live_python_bytes": current, "peak_python_bytes": peak})
    records = records_for(family, n)
    h = max(e["id"] for e in records)
    checkpoint("input")
    log = log_index(Epoch(e["id"], tuple(map(tuple, e["r"])), tuple(map(tuple, e["s"]))) for e in records)
    producer = certificate(log, h, [], [], evaluate({}, {}))
    image = producer["recovered"]
    checkpoint("producer")
    if measure in ("aux", "checker-time"):
        # Inputs, complete candidate and its commitment already exist. As in the
        # retained controls, this peak must not be described as total memory.
        commitment = commit_image(image)
        if measure == "aux": tracemalloc.start()
        checker_started = time.perf_counter_ns()
        if mode == "factorized":
            result = verify_factorized(records, h, image, commitment=commitment, seed=b"owned-benchmark" * 3)
        else: result = check_candidate(mode, records, h, image)
        if not result: raise AssertionError("correct candidate rejected")
        checker_ns = time.perf_counter_ns() - checker_started
        if measure == "checker-time": return {"checker_ns": checker_ns}
        live, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {"aux_peak_python_bytes": peak, "aux_live_python_bytes": live}
    empty = {name: [] for name in image}
    store = Store({**empty, "metadata": {"target": 0}}, records=records, target=h, mode=mode,
                  _entropy=lambda: b"owned-lifecycle-seed" * 2)
    checkpoint("store-authority-copy")
    complete = {**image, "metadata": {"target": h}}
    store.prepare(complete)
    checkpoint("prepare")
    sid = store.commit()
    checkpoint("commit")
    store.challenge()
    checkpoint("challenge")
    store.admit()
    checkpoint("admit")
    for part in PARTS: store.flush(part)
    checkpoint("flush")
    store.publish()
    checkpoint("publish")
    served = store.read_committed(h)
    if served != complete: raise AssertionError("published target differs")
    checkpoint("serve")
    store.crash()
    store.resume(sid)
    store.admit()
    if store.read_committed(h) != complete: raise AssertionError("reentry differs")
    checkpoint("reentry")
    elapsed = time.perf_counter_ns() - started
    live, peak = tracemalloc.get_traced_memory() if traced else (None, None)
    if traced: tracemalloc.stop()
    return {"lifecycle_ns": elapsed,
            "lifecycle_peak_python_bytes": peak, "lifecycle_live_python_bytes": live,
            "process_peak_rss_bytes": peak_rss_bytes(), "phases": phases,
            "authority_rows": sum(len(e["r"]) + len(e["s"]) for e in records),
            "candidate_rows": sum(len(rows) for rows in image.values()),
            "candidate_join_rows": len(image["joined"]), "accepted_and_served": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--child", nargs=4, metavar=("FAMILY", "N", "MODE", "MEASURE"))
    args = ap.parse_args()
    if args.child:
        family, n, mode, measure = args.child
        print(json.dumps(run_child(family, int(n), mode, measure)))
        return
    if args.out is None or args.out.exists() or args.repeats < 1:
        ap.error("--out must name a new directory and --repeats must be positive")
    rows = []
    for family, sizes in (("generated", (16, 64, 256)), ("cartesian", (8, 32, 128)),
                          ("cancellation", (128, 512, 2048))):
        for n in sizes:
            for mode in MODES:
                for repeat in range(args.repeats):
                    row = {"family": family, "n": n, "mode": mode, "repeat": repeat}
                    for measure in ("checker-time", "time", "aux", "lifecycle"):
                        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                            "--child", family, str(n), mode, measure], capture_output=True, text=True, timeout=90)
                        if result.returncode: raise RuntimeError(result.stderr)
                        row[measure] = json.loads(result.stdout)
                    rows.append(row)
            print(f"completed {family} n={n}: all four production admission modes", flush=True)
    summary = []
    for family, n, mode in dict.fromkeys((r["family"], r["n"], r["mode"]) for r in rows):
        group = [r for r in rows if (r["family"], r["n"], r["mode"]) == (family, n, mode)]
        median = lambda section, key: statistics.median(r[section][key] for r in group)
        summary.append({"family": family, "n": n, "mode": mode, "repeats": args.repeats,
            "authority_rows": group[0]["time"]["authority_rows"],
            "candidate_rows": group[0]["time"]["candidate_rows"],
            "candidate_join_rows": group[0]["time"]["candidate_join_rows"],
            "checker_ms": median("checker-time", "checker_ns") / 1e6,
            "lifecycle_ms": median("time", "lifecycle_ns") / 1e6,
            "aux_peak_python_bytes": median("aux", "aux_peak_python_bytes"),
            "lifecycle_peak_python_bytes": median("lifecycle", "lifecycle_peak_python_bytes"),
            "lifecycle_live_python_bytes": median("lifecycle", "lifecycle_live_python_bytes"),
            "untraced_peak_rss_bytes": median("time", "process_peak_rss_bytes")})
    args.out.mkdir(parents=True)
    (args.out / "raw.json").write_text(json.dumps(rows, indent=2) + "\n")
    with (args.out / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (args.out / "environment.json").write_text(json.dumps({"python": sys.version,
        "platform": platform.platform(), "machine": platform.machine(), "workers": 1,
        "repeats": args.repeats, "modes": MODES,
        "timing": "fresh process; untraced; standalone checker and complete lifecycle measured in separate processes",
        "allocation": "separate fresh processes; tracemalloc; inputs through one committed generation and reentry",
        "RSS": "process high-water working set, including interpreter/native allocation",
        "entropy": "deterministic fixture only; no production soundness estimate",
        "retention": "one generation; no reclamation or many-attempt memory bound"}, indent=2) + "\n")


if __name__ == "__main__": main()
