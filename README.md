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

The retained results/execution.json records the frozen run, and a fresh output
has its own execution.json. verify_results.py reconciles saved raw rows; it does
not infer new executions from past pass markers. Full output must match the
frozen semantic columns; timing/allocation diagnostics may differ by host.
Proofs, support conditions, baseline definitions and event boundaries are in
proofs/model.md, proofs/arguments.md and claim_evidence_ledger.csv.
