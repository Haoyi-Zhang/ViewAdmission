# Formal model and trust boundary

This note fixes the mathematical and executable model used by the paper and
artifact.  It is normative for interpreting the claims; an implementation
outside these assumptions needs a new argument.

## 1. Finite integer bags

A relation of arity `d` is a finite map from integer tuples to integer weights.
Missing tuples have weight zero and zero-weight entries are omitted.  Addition,
subtraction, scalar multiplication, and equality are pointwise over the
integers.  Signed bags are allowed during recovery; the final authorized image
must have nonnegative canonical weights.

Base relations have schemas:

- `R(key,a)`;
- `S(key,b)`.

For finite bags `R` and `S`, the fixed view image is:

- `Sel(R)(key,a) = R(key,a)` when `a` is even, otherwise zero;
- `Join(R,S)(key,a,b) = R(key,a) * S(key,b)`;
- `Group(R,S)(key) = sum_{a,b} Join(R,S)(key,a,b)`.

The image `Q(R,S)` is the ordered five-component object
`(R,S,Sel(R),Join(R,S),Group(R,S))`.

The grouped relation is a bag sum of join multiplicities.  It is not a count of
serialized rows.  SQL NULLs, floating point, collation, `DISTINCT`, outer joins,
recursion, user-defined code, and arbitrary aggregates are absent.

## 2. Epoch log and server authority

An epoch is `(id, delta_R, delta_S)` with a positive integer `id` and finite
signed bags for both deltas.  The durable record set may arrive out of order.
Exact repeated records with the same ID are one logical input; conflicting
records with the same ID are invalid.

A trusted durable marker `h >= 0` authorizes exactly the ID prefix
`P_h={1,...,h}`.  Every ID in the prefix must exist.  Records after `h` may exist
but do not contribute to the authorized target.  The target bases are:

```text
R_h = sum_{i=1..h} delta_R_i
S_h = sum_{i=1..h} delta_S_i
```

They and every component of `Q(R_h,S_h)` must be canonical nonnegative bags.
The marker is supplied independently of the recovery candidate/certificate and
cannot be increased by the producer.

This is server-side durable-prefix semantics.  No server state in the model
proves whether a reply reached a client.  Exactly-once external side effects are
not claimed.

## 3. Mixed-cut anchor and producer

A retained anchor declares two sets `A` and `B` of available epoch IDs.  Its base
operands are:

```text
R_A = sum_{i in A} delta_R_i
S_B = sum_{i in B} delta_S_i
```

The conditional producer theorem assumes the full retained image is exactly
`Q(R_A,S_B)`.  Define:

```text
d_R = sum_{i in P_h \ A} delta_R_i - sum_{i in A \ P_h} delta_R_i
d_S = sum_{i in P_h \ B} delta_S_i - sum_{i in B \ P_h} delta_S_i
```

Then `R_A+d_R=R_h` and `S_B+d_S=S_h`.  The producer updates the join with:

```text
J' = J(R_A,S_B) + J(d_R,S_B) + J(R_h,d_S)
```

which includes the cross term through `R_h=R_A+d_R`.  Selection and grouping
are updated linearly.  This theorem does not validate the anchor.

## 4. Candidate encoding

A candidate is one metadata target and exactly five relation arrays named
`r`, `s`, `selection`, `joined`, and `grouped`.  Each relation:

- has the fixed arity for its component;
- contains only integer coordinates and log weights in the symmetric range
  [-M,M], M=2^63-1; -2^63 is deliberately outside this supported domain;
- is lexicographically sorted;
- has no duplicate tuple key;
- has no zero weight;
- is nonnegative for target admission.

The equation-checker encoding is a compact, key-sorted UTF-8 JSON serialization
of all five relations. `commit_image` returns its SHA-256 digest. The Store
additionally binds that complete image, its target metadata, and the trusted
configuration in a separate store-level commitment.  The commitment
is an executable binding mechanism, not a theorem of information-theoretic
commitment and not a signature.

## 5. Independent exact admission

### SQL modes

The SQLite checker has its own parser and query realization.  Mode `both`
reconstructs and compares anchor plus target; mode `target` reconstructs only the
authorized target.  These are exact executable oracles within SQLite’s accepted
integer envelope, but they materialize the expected join.

### Structural mode

The structural checker independently aggregates `R_h` and `S_h`; compares bases
and selection exactly; checks each candidate join tuple weight equals the base
product; requires candidate join support cardinality
`sum_k |supp R_h(k,.)| |supp S_h(k,.)|`; and compares grouped sums.  Canonical
uniqueness plus product/support equality makes it exact without constructing the
expected join.

## 6. Post-commit factorized admission

The mathematical protocol is:

1. freeze and canonicalize all candidate bytes;
2. compute the candidate commitment;
3. sample independent uniform challenge functions in a prime field;
4. scan the authoritative prefix and candidate to compare five fingerprints;
5. publish only if every round and component accepts.

The implementation uses prime field `q=2^127-1`.  A seed sampled after
commitment is expanded with SHAKE-256 using domains that include commitment,
round, relation, coordinate position, and coordinate value.  Rejection sampling
maps output uniformly to the field under the random-oracle-style executable
model.  The proof itself assumes uniform independent field challenges; it does
not derive information-theoretic randomness from SHAKE.

For a bag component `X(v_1,...,v_d)`, the direct fingerprint is a sum of weights
times one challenge tag per coordinate.  For the join, expected-side evaluation
is factorized:

```text
sum_k x_k * A_k * B_k
A_k = sum_a R_h(k,a) y_a
B_k = sum_b S_h(k,b) z_b
```

The candidate join is scanned directly with the matching `x_k y_a z_b` tag.
The checker also compares direct fingerprints for both bases, selection, and
grouped counts.  Five separate component checks prevent one relation from being
ignored.

The candidate must be fixed before challenge generation.  If a challenge is
known first, `adaptive_two_term_collision` constructs a nonzero two-term
residual whose fingerprint is zero.

## 7. Common integer domain and field lifting

Let M=2^63-1. In every target-admission mode the deduplicated authorized log
must have total absolute variations V_R<=M, V_S<=M, and V_R*V_S<=M.
Candidate coordinates and weights are range-checked before equations are used;
stored weights must be positive and target bases are nonnegative in the
completeness premise. The factorized checker does not independently reconstruct
all base signs: disagreement with an invalid endpoint is covered by its random
residual check, not by an exact sign certificate.

The absolute variation bounds each true base/selection coefficient. Their
product bounds every join coefficient and each grouped sum. The checker also
requires every residual coefficient bound (true bound plus candidate bound) to
be strictly below q. Thus a nonzero integer residual cannot vanish modulo q.
Production q is fixed to the prime 2^127-1; composite moduli are rejected.
This is a conservative common support, not all small final bags: R updates
+M,-M,+1 with a final S update +1 are rejected because V_R=2M+1.

## 8. Randomized guarantee

For a fixed incorrect candidate, at least one component residual is nonzero.
After the envelope check, its fingerprint difference is a nonzero polynomial of
total degree at most three.  A uniform field challenge makes it zero with
probability at most `3/q`.  Acceptance requires all component equalities, so one
nonzero component suffices; no union bound over components is required.
Independent rounds multiply the bound.

The guarantee excludes compromised randomness, a candidate adapted after
challenge disclosure, hash collisions, parser disagreement, implementation
bugs, malicious authority/checker code, and physical persistence failures.

## 9. Publication state machine

A generation consists of five relation objects and metadata containing exactly
the target marker. The untrusted metadata cannot assert a successful decision.
A separate trusted Store session fixes the full candidate snapshot, authority,
h, mode, rounds, FIELD, MAX_I64, query and encoding descriptor. The Store hashes
the complete image together with its trusted configuration. Its admit method
calls the actual configured checker and persists the decision in that session.

Objects become durable only through individual logical flush events. The
bootstrap root is known empty at prefix zero. Every later root must bind the
same complete objects and descriptor as a positive trusted decision. publish
and read_committed both check this binding; object existence alone is not
admission. A complete old root is not service for another requested h: a target
mismatch is RecoveryPending.

A logical challenge event records its normalized seed before returning. A crash
discards staging and the active pointer, but retains durable objects, sessions,
seeds, decisions and the atomic root. A resumed session reuses its recorded
challenge; a new fallback session must commit anew and use a distinct normalized
seed. Test seeds are deterministic; probabilistic guarantees separately require
fresh independent trusted challenges. Fallback shares the producer's rebase
implementation and is not an independent replay implementation.

The binding establishes decision provenance, not zero-error truth after random
admission. Structural admission is exact on its support; randomized admission
retains the stated fixed-candidate error and computational assumptions.

This abstraction omits filesystem reorderings, fsync semantics, sector tears,
storage-controller caches, replication, concurrent writers, process races,
garbage collection, Python object-security isolation, and hardware corruption.

## 10. Trusted and untrusted elements

Trusted:

- completeness and authenticity of the authoritative log prefix and marker;
- checker implementation, canonical parser, field arithmetic, and randomness;
- SHA binding and SHAKE challenge derivation in the executable model;
- whole-object durability and atomic-root primitives of the logical state
  machine.

Untrusted / checked:

- retained mixed-cut image;
- recovery producer output;
- all candidate bytes and metadata presented for admission;
- fallback output until separately recommitted and admitted with fresh challenges.

Excluded:

- malicious or missing authority records;
- public third-party verification;
- external effects and receiver observations;
- physical/distributed storage behavior;
- workload performance or production integration.
