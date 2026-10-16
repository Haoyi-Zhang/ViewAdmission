# Post-Commit Admission for Crash-Recovered Relational Views

Finite, single-node five-relation recovery and admission model.

## Reproduction

From this directory run:

```sh
python3 run_complete.py --out reproduced --compare results
```

From the complete project root, the equivalent command is:

```sh
python3 artifact/run_complete.py --out reproduced --compare artifact/results
```

Output and comparison paths are relative to the current working directory.
A missing comparison directory is rejected before starting the experiments.
The output directory must not already exist. Use normal Python, not `python -O`:
the runner refuses optimized execution rather than disabling scientific checks.
The implementation uses the Python standard library and SQLite. Reproduction
was tested with CPython 3.13.5 on Linux; the runners use the POSIX `resource`
module, so native Windows is not a supported execution environment. Use a Linux
environment for the documented commands. No cross-platform test is claimed.
It needs no GPU, paid service, external account, or private dataset.

The store enforces its own complete-candidate admission binding at publication
and service. Exact and randomized checkers share a conservative integer domain;
the production randomized interface fixes a prime. The fallback producer shares
its rebase implementation with the initial candidate producer. It is not an
independent replay implementation. Each new fallback still needs commitment,
a distinct normalized challenge, and admission. The independent SQL path checks
endpoints.

The publication campaign executes all logical store transitions, while caching
only deterministic fingerprint decisions with identical complete arguments
across flush permutations. A paired regression disables that reuse. Negative
controls are genuine rejected calls. This is a finite logical persistence model,
not a filesystem or a claim about physical power loss.

Timing and auxiliary-allocation diagnostics are not universal speedup claims.
Resident inputs and the store's complete-candidate snapshots count toward total
memory. The prime-field error bound is conditional on a fixed supported
candidate and fresh independent challenges; binding does not make it zero error.

The saved unit-test report records 60 passing tests. Before the five saved-paired-
measurement guards, source discovery found 82 methods. A CPython 3.12.14 native-Windows discovery run executed
82: 79 passed, two failed and one errored because POSIX `resource` is unavailable.
This is not a successful full POSIX reproduction. The six added streaming
methods and three existing portable group-total regressions passed separately.

Current factorized checking stores each untagged modular base total once per
historical join key, rather than repeating it in every round. Round-specific
tagged sums, challenge derivation/order, complete commitments, integer envelopes,
zero-key retention and all report fields are unchanged. This reduces repeated
untagged additions/storage, not sensitive input scans or the randomized error
bound. Frozen timings and allocation diagnostics precede this change.

Three separate portable methods use owned benign integer relations, independent
nested-loop replay/expanded fingerprint definitions, signed cancellation,
rounds 1/2/8 and ordinary logical publication. They need only current included
sources and the standard library, with no network, provider or external target:

```sh
python -B -m unittest discover -s regressions -p test_group_totals.py -v
```

The scientific CI runs them in a separate required step and preserves its log.
They do not enter `tests/`, its 82-method inventory or the frozen 60-test record.
These narrow finite checks are portable; the complete POSIX reproduction above
is unchanged and is not claimed rerun or cross-platform validated. No new
latency, memory measurement, soundness probability or physical recovery claim.

The retained results/execution.json records the frozen run, and a fresh output
has its own execution.json. verify_results.py reconciles saved raw rows; it does
not infer new executions from past pass markers. Full output must match the
frozen semantic columns; timing/allocation diagnostics may differ by host.
Proofs, support conditions, baseline definitions and event boundaries are in
proofs/model.md, proofs/arguments.md and claim_evidence_ledger.csv.

## Exact sorted-merge mode and paired measurements

`verify_streaming` is a same-information zero-error checker. It independently
aggregates and compares each authoritative base, releasing that map before
the next base. It then checks selection as a sorted subsequence, join rows in
matching base-key blocks, and groups as products of block masses. It does not
build derived maps or an expected join relation. Sorted candidate bases do not
remove the exact aggregation needed for unsorted signed authority: auxiliary
space is O(E + B_max) in that phase and constant cursor state for derived checks.
It uses no historical-key accumulator after base validation. The randomized
mode retains O(E + r*K_hist) field/index state and its original error bound.

The mode is integrated in `guarded_recover`, `Store.admit`, the committed store
descriptor and the demo, including checked fallback and publication/service
binding. Cryptographic commitments and post-commit challenge rules are unchanged.

```sh
python3 -B demo.py --poison --admission streaming
python3 -B -m unittest discover -s tests -p test_streaming.py -v
python3 -B admission_benchmark.py --out paired-lifecycle --repeats 3
```

The six streaming tests include 112 targets and 560 component mutations per method against
independent nested-loop expectations, SQL-both, SQL-target, structural, streaming
and factorized checking. Four actual store modes execute 208 paired direct and
fallback logical crash/reentry schedules without equation reuse. These checks
are additional; the frozen 11,529-endpoint/46,800-schedule packets do not claim
new-mode coverage.

The benchmark uses a fresh child process for each measurement, one worker,
three repetitions, identical inputs/candidate information, and the actual
producer and store. SQL-both is an anchor-and-target diagnostic, not a store
mode, and is not charged as a target-only lifecycle comparator. New output
contains raw phase samples, summary.csv, and environment.json. The earlier retained
`results/admission-lifecycle.csv` and environment JSON record Windows/CPython
3.12.14 diagnostics for 36 workload/mode combinations (108 paired repetitions;
four separate measurement processes per repetition). Times are untraced;
checker-only and whole-lifecycle tracemalloc runs are separate. Whole-lifecycle
tracing starts before input creation and includes producer, authority copy,
prepare, committed snapshot, admission, durable objects, publication, service
and reentry. It measures one retained generation, not arbitrary retained attempts.
Tracemalloc excludes native SQLite allocation; process peak RSS includes native
allocation and the interpreter. No claimed memory metric is inferred from a
standalone verifier peak.

For the 16,384-row Cartesian join, structural/streaming/factorized lifecycle
peaks are effectively identical at 10.487 MiB even though checker peaks differ.
At 2,048 canceled keys, factorized auxiliary state is 986,299 bytes versus
1,016 for streaming; factorized checking is also slower. These are retained
negative findings. Many payloads per historical key can favor randomized
authority-state asymptotics, but the current measurements establish neither a
latency advantage nor lower whole-lifecycle memory. Existing raw results and
macros are unchanged; no current timing is attributed to the old Linux run.

`verify_results.py` checks the distinct degree-1/2/3 control identities, all
32 adaptive-control identities, and their arithmetic fields, in addition to
endpoint and publication coverage. It does not turn algebra controls into an
empirical estimate of production false acceptance. Complexity accounting
distinguishes all raw epoch records/rows from the deduplicated prefix rows.

## Source-bound paired study

The three paper schematics are generated directly as embedded-font vector PDFs
by `figures/draw_schematics.py` (Python/Matplotlib). This optional presentation
dependency is separate from the standard-library scientific checks. The paper
builder regenerates and copies these assets into its clean build directory.
Two standard-library controls check the actual cut-membership and protocol-edge
specifications without importing Matplotlib or changing scientific case counts.

```sh
python figures/draw_schematics.py --output-dir /tmp/viewadmission-figures
python -B -m unittest discover -s regressions -p test_figure_contract.py -v
```

`results/admission-paired` contains the adopted current-source run: 36 workload/
mode combinations, three repetitions and four separate measurement processes
per repetition, for 108 paired samples and 432 processes. The benchmark, seven
recovery modules and three generated input files were captured before the run
and unchanged afterward. Public source bindings normalize UTF-8 line endings
for portable comparison. The environment records Windows 11 Pro build 28000,
CPython 3.12.14, SQLite 3.53.1 and the Intel Core i7-12700KF.

```sh
python -B verify_admission_measurements.py
python -B verify_admission_measurements.py --paper ../paper
python -B -m unittest discover -s tests -p test_admission_measurements.py -v
```

The optional manuscript path must already exist. Reconciliation verifies all
sample identities, admission/service results, lifecycle phases, medians and
measured source/input bindings before generating the manuscript table. The five
portable regression methods reject missing/duplicate samples, failed service,
nonfinite or inconsistent summary values and incomplete bindings. They pass in
ordinary and optimized Python without rerunning timings.

Current measurements include the scalar untagged-key optimization. The earlier
`admission-lifecycle.csv` remains a separate retained study, not a causal
before/after optimization control. For Cartesian-128, current structural,
streaming and factorized lifecycle peaks all round to 10.487 MiB. Canceled-key
factorized auxiliary state remains 986,299 bytes, compared with 1,016 for
streaming. The main manuscript uses the adopted current-source table.

The scientific workflow is configured to run the complete command from this flat artifact
repository root on Ubuntu 24.04/Python 3.12, with a 900-second whole-command
wall limit, one worker, and a 1 GiB address-space cap. It retains raw output
and the command transcript even on failure. The separate repository-integrity
workflow checks source/configuration syntax only.
