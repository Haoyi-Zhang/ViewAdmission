# Post-commit admission for crash-recovered relational views

This is the standalone reproducibility repository for the paper
**Post-Commit Admission for Crash-Recovered Relational Views**.  It implements a
small finite bag-relational recovery model, two independent admission checkers,
logical publication, exact counterexamples, and the complete retained finite
campaign.  It does not require the paper directory, network access, a package
manager, a GPU, or an external service.

## Scope

The authoritative input is a finite log of integer-weighted deltas for two base
relations `R(key,a)` and `S(key,b)`.  A trusted marker `h` authorizes exactly the
prefix `1..h`.  The target image contains:

- `r` and `s` base bags;
- `selection`: rows of `r` with even payload `a`;
- `joined`: the bag equijoin on `key`;
- `grouped`: per-key sums of join multiplicities;
- metadata naming target `h`.

The producer can retarget a valid mixed-cut image whose `R` and `S` operands were
formed from different epoch subsets.  Admission is independent of that producer.
The repository excludes arbitrary SQL, NULLs, floating-point arithmetic,
concurrent updates, distributed recovery, public authenticity, physical storage
faults, and client-observed acknowledgement semantics.

## Requirements

- Python 3.11 or newer;
- Python standard library, including `sqlite3`;
- a POSIX-like environment for the optional resource limits in `run_all.py`.

No third-party Python dependency is installed or downloaded.  The implementation
uses one worker.  `run_all.py` applies one-core affinity where available, a
1 GiB address-space limit, a 120-second child CPU limit, and a 180-second
subprocess timeout.

## Complete reproduction

From this directory, choose a new output directory:

```sh
python3 run_all.py --out reproduced --compare results
```

The output path must not already exist.  The command:

1. regenerates all finite sweeps and raw CSV/JSON results;
2. runs 42 unit tests;
3. checks five stored positive/counterexample cases;
4. runs an end-to-end poisoned-candidate recovery with factorized admission and
   independently admitted replay fallback;
5. performs deep SQL-oracle controls and compares every deterministic raw column
   against `results/` (timing columns are excluded);
6. writes one reconciliation and execution record.

A successful run exits with status zero.  On the frozen environment, the final
campaign used one worker, about 31.2 child CPU seconds, 31.2 wall seconds, and
155,668 KiB peak child RSS.  These measurements are diagnostic, not production
performance claims.

To reproduce without comparing with the retained packet:

```sh
python3 run_all.py --out reproduced
```

To run only tests:

```sh
python3 run_tests.py
```

To run one finite stage in resumable mode:

```sh
python3 reproduce.py --mode full --stage cuts --out partial
python3 reproduce.py --mode full --stage publication --out partial --resume
```

Stages are `algebra`, `cuts`, `publication`, `receipts`, `workloads`, and
`soundness`.  `--resume` refuses to replace an already completed stage file.

## Admission modes

`recovery.engine.guarded_recover` supports four modes.

### `both`

The independent SQLite wrapper reconstructs and checks both the retained anchor
and target.  This is exact but deliberately expensive and is used as a strong
diagnostic baseline.

### `target`

The independent SQLite wrapper reconstructs only the authorized target.  It is
exact, catches a poisoned producer endpoint, and may trigger replay fallback.
It still constructs the expected target join.

### `structural`

`recovery.factorized.verify_structural` is an exact checker independent of the
producer and SQLite wrapper.  It builds exact target base maps, compares the
selection, verifies each supplied join weight, requires the exact join support
cardinality, and checks grouped counts.  It never constructs an expected join,
but it must read every supplied candidate tuple.

### `factorized`

`recovery.factorized.verify_factorized` binds the canonical complete candidate
with SHA-256, samples/uses a fresh seed only after commitment, and compares two
rounds of five domain-separated fingerprints.  Its expected join fingerprint is
factorized by key:

```text
sum_k x_k * (sum_a R(k,a) y_a) * (sum_b S(k,b) z_b)
```

The frozen field is the prime `2^127-1`.  Conservative integer envelope checks
reject instances that could erase a nonzero coefficient modulo the field.  For
a fixed pre-challenge candidate, the paper proves one-round false acceptance at
most `3/q`; independent repetition gives `(3/q)^r`.  The executable hash
construction is a private randomized admission check, not a digital signature,
zero-knowledge proof, or publicly verifiable certificate.

A rejected candidate can fall back to replay, but fallback bytes are canonicalized,
recommitted, and challenged with an independent seed.  No fallback bypasses
admission.

## Frozen results

| Check | Retained result |
|---|---:|
| Scalar bilinear assignments | 625; omission fails 400 |
| Mixed-cut endpoints | 11,529 |
| Factorized component mutations | 57,645 rejected; 0 misses |
| Logical publication schedules | 46,800 |
| Receipt/effect schedules | 120; naive receipt marker fails 72 |
| Exact small-field assignments | 5,219 |
| Known-challenge adaptive collisions | 32 / 32 constructed |
| Generated workloads | 180 |
| Unit tests | 42 / 42 pass |
| Expected join tuples enumerated by factorized expectation | 0 |

The exact per-stage counts and measured resources are in
`results/*_summary.json`, `results/reconciliation.json`, and
`results/execution.json`.  Raw rows are retained in CSV form.  `verify_results.py`
checks uniqueness, coverage formulas, invariant columns, deep SQLite controls,
small-field counts, and deterministic equality with a comparison packet.

## Repository layout

```text
README.md
LICENSE
claim_evidence_ledger.csv
external_resources.csv
cases/                    fixed positive and counterexample records
inputs/                   exact small and generated stream inputs
proofs/model.md           definitions, assumptions, and trust boundary
proofs/arguments.md       theorem-by-theorem argument and code correspondence
recovery/algebra.py       bag operations and fixed view image
recovery/engine.py        log normalization, producer, fallback, admission modes
recovery/checker.py       independent SQLite replay/checking path
recovery/factorized.py    exact structural and post-commit factorized checkers
recovery/publication.py   immutable-object / atomic-root logical state machine
reproduce.py              finite campaign and raw rows
verify_results.py         reconciliation, comparison, and LaTeX macro emission
run_tests.py              test entry point
run_all.py                complete one-worker reproduction
results/                  retained raw and summary evidence
```

The producer, SQLite checker, structural/factorized checker, and publication
state machine are separate modules.  The factorized checker imports neither the
producer nor the SQLite checker; tests enforce that separation.

## Interpreting success

A successful reproduction establishes that the supplied code regenerates and
reconciles the declared finite evidence.  It does not by itself prove a general
theorem, validate a real filesystem, authenticate the authoritative log, show
workload representativeness, or constitute independent peer review.  General
arguments and assumptions are stated in `proofs/`; every material manuscript
claim is mapped to proof/test/raw evidence in `claim_evidence_ledger.csv`.

## License and external material

New repository code and documentation are licensed under the included MIT
license.  Python, SQLite, cited publications, and publisher template files are
not relicensed or bundled here.  `external_resources.csv` records the scholarly,
official, and runtime resources used for calibration or checking.  No external
paper PDF, font, model, private dataset, or publisher style file is included in
this standalone repository.
