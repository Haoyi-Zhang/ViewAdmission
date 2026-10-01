# Arguments, counterexamples, and executable correspondence

This note expands the paper’s proofs and maps each proof obligation to code and
raw evidence.  Finite checks support the implementation and boundary cases; they
are not represented as machine-checked general proofs.

## A. Conditional mixed-cut retargeting

Let the retained operands be `R_A` and `S_B`, the target be `R_h` and `S_h`, and
`d_R=R_h-R_A`, `d_S=S_h-S_B`.  Integer-bag join is bilinear:

```text
J(R_A+d_R, S_B+d_S)
 = J(R_A,S_B)
 + J(d_R,S_B)
 + J(R_A,d_S)
 + J(d_R,d_S)
 = J(R_A,S_B) + J(d_R,S_B) + J(R_h,d_S).
```

Selection and grouping are finite linear maps, so updating them by the induced
delta produces `Q(R_h,S_h)` when the complete anchor was exactly `Q(R_A,S_B)`.
The order “update R then join d_S against R_h” is a factorization of the
algebraic expansion, not a durability order.

**Counterexample to the missing cross term.**  Start from empty operands and
insert one matching row into both sides.  `J(d_R,S_B)` and `J(R_A,d_S)` are both
zero, while `J(d_R,d_S)` is the entire target join.

**Executable correspondence.**

- `recovery/algebra.py`: integer-bag operations and views;
- `recovery/engine.py`: mixed-cut certificate and `retarget`;
- `reproduce.py::algebra_rows`: 625 scalar assignments;
- `results/algebra.csv`: complete forms pass all 625; omission passes only 225
  and therefore fails 400;
- `tests/test_recovery.py::test_cross_term_needed`.

This argument is established IVM algebra.  It is retained to make the producer’s
precondition and the endpoint gap explicit.

## B. Exact deltas preserve anchor residual

Let a retained image be `W~=Q(R_A,S_B)+E`, component by component.  The exact
producer adds the fixed difference `Q(R_h,S_h)-Q(R_A,S_B)`.  Therefore:

```text
T(W~) = W~ + Q(R_h,S_h) - Q(R_A,S_B)
      = Q(R_h,S_h) + E.
```

Every nonzero residual is preserved.  A transition equation can prove that the
producer applied its own delta but cannot establish target equality unless it
also establishes a valid anchor.

**Executable correspondence.**

- `tests/test_recovery.py::test_poison_is_not_healed`;
- `reproduce.py::cut_rows` injects one extra anchor join tuple in every one of
  11,529 endpoint configurations;
- `results/cuts.csv` columns `residual_preserved`, `poison_rejected`, and
  `fallback_ok` are true in every row.

## C. Exactness of structural admission

The checker reconstructs exact target base maps `R_h` and `S_h`.  Equality of
candidate bases and selection is direct.  For each candidate join key
`(k,a,b)`, it requires weight `R_h(k,a)S_h(k,b)`.  Canonicalization gives at most
one candidate row per key.  The expected support cardinality is:

```text
N_J = sum_k |supp R_h(k,.)| * |supp S_h(k,.)|.
```

Every nonzero expected product has one key in this support set.  If all supplied
rows have the correct key/weight and the number of supplied keys is exactly
`N_J`, no expected key can be missing and no extra key can be present.  Computing each grouped weight as the product of the two authoritative
per-key base masses and comparing it with the candidate group fixes the final
component; no second scan or copy of the candidate join is required.  Within the common supported integer domain, acceptance is equivalent to the
exact five-relation image.

The checker builds per-key base maps and scans source/candidate rows in expected
O(L+C) dictionary time, plus ID normalization. Let H_R and H_S count the peak
base-map tuple slots during prefix aggregation, including keys later reduced
to zero; E counts epoch metadata and K_hist historical join keys. Its auxiliary
state is O(E+H_R+H_S+K_hist), not simply the final support. It does not build an
expected join or copy the candidate join inside verify_structural. Resident
candidate inputs and complete Store snapshots remain O(C) outside that checker.
The production factorized checker recomputes coordinate tags and has no
payload cache. Its auxiliary state is O(E+r*K_hist), including historical keys
whose final sums vanish. With at most A retained attempts and at most C rows
per candidate, Store snapshots and generations additionally occupy O(A*C)
state, besides resident authority and producer state. Deterministic equation
memoization exists only in the finite test harness, not in this checker. The
space controls include fixed key count with growing payloads, Cartesian joins,
and canceling logs (results/memory_controls.csv).

**Executable correspondence.**

- `recovery/factorized.py::verify_structural`;
- `tests/test_factorized.py::test_valid_target_exact_and_factorized`;
- `tests/test_factorized.py::test_missing_and_extra_join_rows_are_rejected`;
- `results/cuts.csv`: `structural_ok=1` in all 11,529 rows;
- `results/workloads.csv`: all 180 generated rows accept.

## D. Factorized expected join identity

For one round, assign independent field tags `x_k`, `y_a`, and `z_b`.  The direct
candidate join fingerprint is:

```text
Phi(J_hat) = sum_{k,a,b} J_hat(k,a,b) x_k y_a z_b.
```

For the true bag join, finite distributivity gives:

```text
Phi(J(R_h,S_h))
 = sum_k x_k * (sum_a R_h(k,a)y_a) * (sum_b S_h(k,b)z_b).
```

The right side stores two tagged sums per key and contains no enumeration over
expected `(a,b)` pairs.  Candidate processing remains linear in the supplied
join because every supplied byte must be bound and inspected.

**Executable correspondence.**

- `recovery/factorized.py::verify_factorized`;
- report field `expected_join_pairs_enumerated=0`;
- `results/reconciliation.json::factorized_protocol`;
- unit test enforcing that the checker imports neither producer nor SQL checker.

## E. Completeness and fixed-candidate soundness

For the correct image on the common supported domain in model.md Section 7,
every direct candidate fingerprint equals its independently computed expectation,
so completeness is perfect. Domain rejection is not a false negative under
this conditional completeness statement.

For an incorrect candidate, choose one nonzero component residual.  Base and
selection residual fingerprints have degree at most two, join residuals degree
at most three, and grouped residuals degree one.  Integer-envelope admission
ensures at least one nonzero integer coefficient remains nonzero in the field.
The residual fingerprint is therefore a nonzero polynomial of degree at most
three.  Schwartz–Zippel bounds its root probability under a uniform challenge by
`3/q`.  Since total acceptance implies this one residual vanishes, no union
bound over five components is necessary.  Independent challenges multiply the
bound to `(3/q)^r`.

The candidate-fixity quantifier is essential.  The theorem is:

```text
for every fixed incorrect candidate C:
    Pr_challenge[Verify(C, challenge)=accept] <= 3/q.
```

It is not a guarantee against choosing `C` after learning `challenge`.

**Executable correspondence.**

- `FIELD = 2^127-1`, frozen rounds `r=2`;
- `finite_field_detection_counts(17)` enumerates exact degree-1, degree-2, and
  degree-3 residual families over all 5,219 field assignments and obtains the
  exact expected root counts;
- `adaptive_two_term_collision` constructs a nonzero residual after seeing a
  challenge; 32/32 campaign controls succeed;
- 57,645 one-component mutations per mode (five components over 11,529 endpoints)
  are rejected separately by structural and factorized admission;
- `tests/test_factorized.py::test_small_field_refuses_noninjective_integer_envelope`
  checks envelope rejection.

Observed zero misses do not replace the theorem and do not justify an empirical
failure probability estimate.

## F. Why the commitment covers all five components

The protocol must bind the exact bytes later scanned by the verifier.  Binding
only the join would let a producer change a base, selection, group, metadata, or
encoding after learning tags while keeping join bytes fixed.  Canonical
serialization binds the five arrays at the equation-checker interface. The
Store separately binds the full image, metadata, authority and fixed checker
configuration, preventing lifecycle ambiguity under the executable hash
assumption. It validates metadata before invoking the equation checker and
revalidates the complete binding at publication and service.

If a producer is rejected and replay fallback is used, the fallback has new
provenance and can have different bytes.  It is therefore serialized and
committed anew, then receives a distinct seed.  Treating replay as trusted would
reintroduce the endpoint gap at the fallback boundary.

**Executable correspondence.**

- `canonical_image_bytes`, `commit_image`, and `_image` in
  `recovery/factorized.py`;
- `guarded_recover` in `recovery/engine.py`;
- commitment/seed validation and fallback tests in `tests/test_factorized.py`;
- 46,800 publication rows exercise commit-before-challenge, challenge-before-admission,
  and unverified-publish rejection. Exactly 28,080 take a fallback with a new
  commitment/challenge; 18,720 take a direct path. A fallback-only condition is
  vacuous on direct rows. Five additional fine fallback cuts are tested
  separately, not crossed with every flush order.
- The 1/33/817 product-polynomial counts and 32/32 adaptive collisions are algebra
  controls, not complete-admission attacks or tag-separation tests. The separate
  test-only tag injection executes actual fingerprint equations with complete
  canonical candidates and matched envelopes; relation omission, domain mixing,
  and wrong factorization are required to fail. Production rejects small q.

## G. No-synopsis read lower bound

Fix a correct instance `I` and one sensitive cell `j`.  By sensitivity there is
a valid `I^(j)` differing only at `j` that requires rejection.  Couple the
checker on the same random tape.  If that execution does not read `j`, its
observations on `I` and `I^(j)` are identical.  Perfect completeness requires
acceptance on `I` for every tape, so every tape skipping `j` also accepts
`I^(j)`.  False acceptance at most `epsilon` therefore gives:

```text
Pr[skip j] <= epsilon,
Pr[read j] >= 1-epsilon.
```

For sensitive-cell indicators `X_j`, linearity of expectation yields
`E[sum_j X_j] >= (1-epsilon)m_s`; independence among reads is unnecessary.

This lower bound is tied to the absence of a trusted synopsis depending on the
cells.  Authenticated indexes, maintained digests, proof objects, interactive
provers, and trusted hardware invalidate its premise by supplying additional
information.  The result therefore supports only “avoid expected join
expansion,” never “sublinear verification.”

## H. Logical publication safety

Use three invariants:

1. **Root validity:** the root is the fixed empty bootstrap at zero, or names
   a complete candidate bound to a positive trusted admission decision.
2. **Private construction:** staged/partially flushed candidate objects are not
   reachable from the root.
3. **Monotone gate:** for an admitted generation, commitment, marker, object
   names, parameters, and decision never change.

Build, commit, challenge, verify, and individual object flushes do not change the
root, so they preserve the invariants.  The root swing is guarded by durability
of all named immutable objects plus a matching trusted session decision and descriptor, so its atomic
execution establishes the invariants for the new root.  A crash can discard
private state but leaves the old atomic root and immutable durable objects.
Reentry begins from that complete root and must pass the same gate before
another swing. Service additionally requires the root target to equal the
requested h; otherwise it raises RecoveryPending. An old complete root cannot
answer a new-target request. Randomized admission makes this a decision-binding
invariant with probabilistic semantic soundness, not a zero-error semantic
invariant. For A adaptive attempts with fresh independent post-commit challenges,
a union bound gives at most A*(3/q)^r; repeated reads are not additional trials.

**Executable correspondence.**

- `recovery/publication.py`;
- five targets × 720 object flush orders × 13 crash cuts = 46,800 raw cases;
- all publication invariant columns are true in
  `results/publication.csv` and summary;
- `tests/test_recovery.py::test_publication_fence` and
  `test_stale_root_not_served`.

The enumeration is exhaustive only for the declared logical events.  It is not
a physical crash test.

## I. Server marker versus client receipt

Construct two histories with identical server durable state: the server commits
prefix `h` and sends a reply.  In one history the reply reaches the client; in
the other it is lost just before the crash.  Any server-only recovery algorithm
sees the same durable log and marker in both histories.  It cannot output two
different “last client-observed” answers.  Receiver evidence or an external
protocol is necessary.

`cases/case-d.json`, `check_cases.py`, and 120 receipt/effect schedules encode
this distinction.  A naive durable receipt marker matches exactly-once effects
in only 48 schedules and fails in 72.

## J. Equality of images does not identify a unique prefix

Insert/delete cancellation can make two different prefix indices produce the
same five-relation image.  Therefore target image equality alone cannot infer a
unique durable marker.  The marker remains independent trusted authority and is
stored/checked as metadata.  `cases/case-e.json` is the executable witness.

## K. Evidence limits

The artifact establishes exact results for its frozen finite domains, execution
paths, and logical schedules.  It does not establish workload prevalence,
production speed, public authenticity, storage physics, or generalized SQL
coverage.  The paper’s algebraic and lower-bound proofs are human-readable
arguments, not proof-assistant output.  Review of this packet is a self-audit,
not independent validation.
