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

The saved unit-test report records 60 passing tests; the current source defines
76 discoverable methods. The retained pass count covers that saved run, not a
verified run of the entire current suite.

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
They do not enter `tests/`, its 76-method inventory or the frozen 60-test record.
These narrow finite checks are portable; the complete POSIX reproduction above
is unchanged and is not claimed rerun or cross-platform validated. No new
latency, memory measurement, soundness probability or physical recovery claim.

The retained results/execution.json records the frozen run, and a fresh output
has its own execution.json. verify_results.py reconciles saved raw rows; it does
not infer new executions from past pass markers. Full output must match the
frozen semantic columns; timing/allocation diagnostics may differ by host.
Proofs, support conditions, baseline definitions and event boundaries are in
proofs/model.md, proofs/arguments.md and claim_evidence_ledger.csv.

`verify_results.py` checks the distinct degree-1/2/3 control identities, all
32 adaptive-control identities, and their arithmetic fields, in addition to
endpoint and publication coverage. It does not turn algebra controls into an
empirical estimate of production false acceptance. Complexity accounting
distinguishes all raw epoch records/rows from the deduplicated prefix rows.

The scientific workflow is configured to run the complete command from this flat artifact
repository root on Ubuntu 24.04/Python 3.12, with a 900-second whole-command
wall limit, one worker, and a 1 GiB address-space cap. It retains raw output
and the command transcript even on failure. The separate repository-integrity
workflow checks source/configuration syntax only.
