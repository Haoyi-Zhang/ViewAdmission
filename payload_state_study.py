"""Bounded checker-allocation study; resident inputs/candidate are excluded.

The fixed matrix is one live join key, 64/256/1024 distinct left payloads,
one right payload, two existing admission modes and three fresh-process samples.
No timing, RSS, store lifecycle, new query operator or physical crash is measured.
"""
from __future__ import annotations
import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tracemalloc

from recovery.factorized import commit_image, verify_factorized, verify_streaming

ROOT = Path(__file__).resolve().parent
SIZES = (64, 256, 1024)
MODES = ('streaming', 'factorized')
REPEATS = 3


def inputs(n):
    if n not in SIZES:
        raise ValueError('size outside the fixed matrix')
    rows = [[0, index, 1] for index in range(n)]
    records = [{'id': 1, 'r': rows, 's': [[0, 0, 1]]}]
    image = {'r': [list(row) for row in rows], 's': [[0, 0, 1]],
             'selection': [list(row) for row in rows if row[1] % 2 == 0],
             'joined': [[0, index, 0, 1] for index in range(n)],
             'grouped': [[0, n]]}
    return records, image


def sample(n, mode):
    if mode not in MODES:
        raise ValueError('unknown admission mode')
    records, image = inputs(n)
    commitment = commit_image(image)
    gc.collect()
    tracemalloc.start()
    try:
        if mode == 'streaming':
            accepted = verify_streaming(records, 1, image)
            keys = None
        else:
            # Deterministic owned fixture, not an empirical soundness estimate.
            report = verify_factorized(records, 1, image,
                        commitment=commitment, seed=b'payload-state-fixture-seed' * 2)
            accepted = report.accepted
            keys = report.peak_accumulator_keys
        live, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if not accepted:
        raise ValueError('correct owned candidate rejected')
    return {'n': n, 'mode': mode, 'accepted': True,
            'authority_rows': n + 1, 'candidate_rows': 2 * n + n // 2 + 2,
            'candidate_join_rows': n, 'live_join_keys': 1,
            'reported_accumulator_keys': keys,
            'aux_live_python_bytes': live, 'aux_peak_python_bytes': peak}


def source_bindings():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ('payload_state_study.py', 'recovery/factorized.py')}


def validate(rows):
    expected = {(n, mode, repeat) for n in SIZES for mode in MODES
                for repeat in range(REPEATS)}
    seen = set()
    for row in rows:
        key = (row['n'], row['mode'], row['repeat'])
        if key not in expected or key in seen:
            raise ValueError('invalid or duplicate sample identity')
        seen.add(key)
        n = row['n']
        if (row['accepted'] is not True or row['authority_rows'] != n + 1
                or row['candidate_rows'] != 2 * n + n // 2 + 2
                or row['candidate_join_rows'] != n or row['live_join_keys'] != 1):
            raise ValueError('incorrect denominator or rejected candidate')
        if row['reported_accumulator_keys'] != (1 if row['mode'] == 'factorized' else None):
            raise ValueError('incorrect accumulator scope')
        live, peak = row['aux_live_python_bytes'], row['aux_peak_python_bytes']
        if type(live) is not int or type(peak) is not int or not 0 <= live <= peak:
            raise ValueError('invalid allocation sample')
    if seen != expected:
        raise ValueError('incomplete fixed matrix')
    return [{'n': n, 'mode': mode,
             'median_aux_peak_python_bytes': statistics.median(
                 row['aux_peak_python_bytes'] for row in rows
                 if row['n'] == n and row['mode'] == mode)}
            for n in SIZES for mode in MODES]


def table_tex(summary):
    values = {(row['n'], row['mode']): row['median_aux_peak_python_bytes']
              for row in summary}
    lines = [r'\begin{table}[t]', r'\centering',
             r'\caption{One-key asymmetric payload controls: median checker-only Python allocation over three fresh processes. Resident inputs and candidate excluded.}',
             r'\label{tab:payload-state}', r'\begin{tabular}{rrr}', r'\toprule',
             r'Left payloads & Sorted merge (bytes) & Factorized (bytes) \\', r'\midrule']
    for n in SIZES:
        lines.append(f"{n:,} & {values[n, 'streaming']:,.0f} & {values[n, 'factorized']:,.0f}" + r' \\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\end{table}']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', nargs=2)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--check', type=Path)
    parser.add_argument('--tex', type=Path)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(sample(int(args.child[0]), args.child[1])))
        return
    if args.check:
        result = json.loads(args.check.read_text(encoding='utf-8'))
        summary = validate(result['samples'])
        if result['source_bindings'] != source_bindings() or result['summary'] != summary:
            raise ValueError('source or summary drift')
        if args.tex and args.tex.read_text(encoding='utf-8') != table_tex(summary):
            raise ValueError('paper table differs from raw samples')
        print('PASS: 18 source-bound allocation samples and derived table')
        return
    if not args.out or args.out.exists():
        parser.error('--out must name a new file')
    before = source_bindings()
    rows = []
    for n in SIZES:
        for mode in MODES:
            for repeat in range(REPEATS):
                command = [sys.executable, '-B', str(Path(__file__).resolve()),
                           '--child', str(n), mode]
                proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                rows.append(dict(json.loads(proc.stdout), repeat=repeat))
    summary = validate(rows)
    if source_bindings() != before:
        raise ValueError('measured sources changed')
    result = {'source_bindings': before, 'samples': rows, 'summary': summary,
              'environment': {'python': sys.version, 'platform': platform.platform(),
                              'workers': 1, 'fresh_processes': 18},
              'scope': 'Checker-only tracemalloc, excludes resident input and candidate; no timing, RSS or lifecycle claim'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    if args.tex:
        args.tex.write_text(table_tex(summary), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
