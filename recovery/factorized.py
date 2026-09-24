"""Independent exact and post-commit randomized admission checkers.

The module deliberately imports neither the producer algebra nor the recovery
engine.  ``verify_structural`` is an exact output-sensitive baseline: it
materializes the target base relations but never materializes an expected join.
``verify_factorized`` verifies the same fixed five-relation image with
factorized polynomial fingerprints.  It scans the authoritative prefix and the
candidate, stores only per-join-key field accumulators after log normalization,
and never enumerates expected join tuples.

The randomized theorem is information-theoretic for independently uniform field
challenges sampled after the candidate is fixed.  The executable derives those
challenges from a secret seed with SHAKE-256 and therefore additionally relies
on the usual pseudorandomness/collision-resistance assumptions of that binding.
It is not a signature, a proof of source authenticity, or a verifier for
arbitrary SQL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable

MAX_INT = (1 << 63) - 1
# 2^127 - 1 is a Mersenne prime.  The implementation uses exact Python integers.
FIELD = (1 << 127) - 1
RELATION_ARITIES = {
    "r": 2,
    "s": 2,
    "selection": 2,
    "joined": 3,
    "grouped": 1,
}


class FactorizedRejected(ValueError):
    """The authority, commitment, or candidate did not satisfy admission."""


@dataclass(frozen=True)
class FactorizedReport:
    accepted: bool
    rounds: int
    field: int
    field_bits: int
    ideal_soundness_numerator: int
    ideal_soundness_denominator: int
    authoritative_epoch_count: int
    authoritative_prefix_rows: int
    candidate_rows: int
    distinct_join_keys: int
    expected_join_pairs_enumerated: int
    candidate_commitment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _integer(value: Any, message: str) -> int:
    if type(value) is not int or abs(value) > MAX_INT:
        raise FactorizedRejected(message)
    return value


def _canonical_relation(rows: Any, arity: int, *, nonnegative: bool) -> list[list[int]]:
    if not isinstance(rows, list):
        raise FactorizedRejected("relation is not a list")
    previous: tuple[int, ...] | None = None
    for row in rows:
        if not isinstance(row, list) or len(row) != arity + 1:
            raise FactorizedRejected("invalid relation row")
        for value in row:
            _integer(value, "noninteger or out-of-range relation value")
        key, weight = tuple(row[:-1]), row[-1]
        if weight == 0 or (nonnegative and weight < 0):
            raise FactorizedRejected("candidate is not a canonical nonnegative bag")
        if previous is not None and key <= previous:
            raise FactorizedRejected("relation is not strictly canonical")
        previous = key
    return rows


def _image(image: Any, *, nonnegative: bool = True) -> dict[str, list[list[int]]]:
    if not isinstance(image, dict) or set(image) != set(RELATION_ARITIES):
        raise FactorizedRejected("wrong image schema")
    return {
        name: _canonical_relation(image[name], arity, nonnegative=nonnegative)
        for name, arity in RELATION_ARITIES.items()
    }


def _log(records: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(records, list):
        raise FactorizedRejected("log must be an array")
    out: dict[int, dict[str, Any]] = {}
    for epoch in records:
        if not isinstance(epoch, dict) or set(epoch) != {"id", "r", "s"}:
            raise FactorizedRejected("wrong epoch schema")
        epoch_id = _integer(epoch["id"], "invalid epoch ID")
        if epoch_id <= 0:
            raise FactorizedRejected("invalid epoch ID")
        for side in ("r", "s"):
            if not isinstance(epoch[side], list):
                raise FactorizedRejected("epoch relation must be a list")
            for row in epoch[side]:
                if not isinstance(row, list) or len(row) != 3:
                    raise FactorizedRejected("invalid epoch delta")
                for value in row:
                    _integer(value, "invalid epoch delta")
        if epoch_id in out and out[epoch_id] != epoch:
            raise FactorizedRejected("conflicting duplicate epoch")
        out[epoch_id] = epoch
    return out


def _authority(records: Any, durable_h: Any) -> tuple[dict[int, dict[str, Any]], int]:
    log = _log(records)
    h = _integer(durable_h, "invalid durable marker")
    if h < 0:
        raise FactorizedRejected("invalid durable marker")
    if any(epoch_id not in log for epoch_id in range(1, h + 1)):
        raise FactorizedRejected("acknowledged prefix has a log hole")
    return log, h


def canonical_image_bytes(image: Any) -> bytes:
    """Return the sole byte representation used by the executable commitment."""
    checked = _image(image, nonnegative=True)
    return json.dumps(checked, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def commit_image(image: Any) -> str:
    """Bind an immutable candidate before the verifier seed is sampled."""
    return hashlib.sha256(canonical_image_bytes(image)).hexdigest()


def fresh_seed() -> bytes:
    """Generate a verifier challenge seed for non-test use."""
    import secrets
    return secrets.token_bytes(32)


def _seed_bytes(seed: bytes | str) -> bytes:
    if isinstance(seed, str):
        try:
            seed = bytes.fromhex(seed)
        except ValueError as exc:
            raise FactorizedRejected("challenge seed is not hexadecimal") from exc
    if not isinstance(seed, bytes) or len(seed) < 16:
        raise FactorizedRejected("challenge seed must contain at least 128 bits")
    return seed


def _field_element(seed: bytes, round_index: int, domain: str, coordinates: tuple[int, ...],
                   q: int = FIELD) -> int:
    """Domain-separated rejection sampling from SHAKE-256 into F_q."""
    if type(round_index) is not int or round_index < 0:
        raise FactorizedRejected("invalid challenge round")
    if type(q) is not int or q <= 3:
        raise FactorizedRejected("invalid field")
    payload = bytearray(b"CCR-FP-v1\0")
    payload.extend(len(seed).to_bytes(2, "big")); payload.extend(seed)
    encoded_domain = domain.encode("ascii")
    payload.extend(len(encoded_domain).to_bytes(2, "big")); payload.extend(encoded_domain)
    payload.extend(round_index.to_bytes(4, "big"))
    payload.extend(len(coordinates).to_bytes(2, "big"))
    for value in coordinates:
        _integer(value, "challenge coordinate out of range")
        payload.extend(value.to_bytes(9, "big", signed=True))
    # 256 bits are ample for the 127-bit production field.  Rejection removes
    # modulo bias and is retained for the small-field finite controls as well.
    limit = (1 << 256) - ((1 << 256) % q)
    counter = 0
    while True:
        probe = hashlib.shake_256(bytes(payload) + counter.to_bytes(4, "big")).digest(32)
        value = int.from_bytes(probe, "big")
        if value < limit:
            return value % q
        counter += 1


def _mod(value: int, q: int) -> int:
    return value % q


def _add(table: dict[int, list[int]], key: int, round_index: int, value: int,
         rounds: int, q: int) -> None:
    row = table.setdefault(key, [0] * rounds)
    row[round_index] = (row[round_index] + value) % q


def verify_factorized(records: Any, durable_h: Any, recovered: Any, *,
                      commitment: str, seed: bytes | str, rounds: int = 2,
                      q: int = FIELD) -> FactorizedReport:
    """Verify the target image without constructing the expected join.

    ``commitment`` must be computed before ``seed`` is sampled.  The function
    recomputes the commitment and binds every challenge to it.  For ideal
    independent field challenges, a fixed incorrect image is accepted with
    probability at most ``(3/q)**rounds`` provided the integer-envelope checks
    below pass.  Completeness is exact.
    """
    if type(rounds) is not int or not 1 <= rounds <= 8:
        raise FactorizedRejected("round count must be in 1..8")
    if type(q) is not int or q <= 3:
        raise FactorizedRejected("invalid field")
    candidate = _image(recovered, nonnegative=True)
    actual_commitment = hashlib.sha256(canonical_image_bytes(candidate)).hexdigest()
    if not isinstance(commitment, str) or commitment != actual_commitment:
        raise FactorizedRejected("candidate commitment mismatch")
    challenge_seed = _seed_bytes(seed)
    log, h = _authority(records, durable_h)

    expected = {name: [0] * rounds for name in RELATION_ARITIES}
    observed = {name: [0] * rounds for name in RELATION_ARITIES}
    r_by_key: dict[int, list[int]] = {}
    s_by_key: dict[int, list[int]] = {}
    r_count_by_key: dict[int, list[int]] = {}
    s_count_by_key: dict[int, list[int]] = {}
    l1_r = l1_s = 0
    prefix_rows = 0

    bound = challenge_seed + bytes.fromhex(actual_commitment)
    tag_cache: dict[tuple[int, str, tuple[int, ...]], int] = {}

    def tag(round_index: int, domain: str, *coords: int) -> int:
        # Binding the content identifier into the challenge prevents a caller
        # from reusing the same derived challenge for different candidates.
        # Coordinates recur across the authority and candidate scans, so cache
        # derived field elements without changing the ideal-random-function model.
        cache_key = (round_index, domain, tuple(coords))
        if cache_key not in tag_cache:
            tag_cache[cache_key] = _field_element(bound, round_index, domain, cache_key[2], q)
        return tag_cache[cache_key]

    # Authority scan.  Direct base/selection fingerprints need no target map;
    # join and group need only one accumulator per join key and round.
    for epoch_id in range(1, h + 1):
        epoch = log[epoch_id]
        for side in ("r", "s"):
            for key, value, weight in epoch[side]:
                prefix_rows += 1
                if side == "r":
                    l1_r += abs(weight)
                else:
                    l1_s += abs(weight)
                if l1_r >= q or l1_s >= q:
                    raise FactorizedRejected("authority integer envelope exceeds field")
                for round_index in range(rounds):
                    if side == "r":
                        term = weight * tag(round_index, "r-key", key) * tag(round_index, "r-value", value)
                        expected["r"][round_index] = (expected["r"][round_index] + term) % q
                        if value % 2 == 0:
                            sel = weight * tag(round_index, "sel-key", key) * tag(round_index, "sel-value", value)
                            expected["selection"][round_index] = (expected["selection"][round_index] + sel) % q
                        _add(r_by_key, key, round_index,
                             weight * tag(round_index, "join-r-value", value), rounds, q)
                        _add(r_count_by_key, key, round_index, weight, rounds, q)
                    else:
                        term = weight * tag(round_index, "s-key", key) * tag(round_index, "s-value", value)
                        expected["s"][round_index] = (expected["s"][round_index] + term) % q
                        _add(s_by_key, key, round_index,
                             weight * tag(round_index, "join-s-value", value), rounds, q)
                        _add(s_count_by_key, key, round_index, weight, rounds, q)

    for key in set(r_by_key) | set(s_by_key):
        r_values = r_by_key.get(key, [0] * rounds)
        s_values = s_by_key.get(key, [0] * rounds)
        r_counts = r_count_by_key.get(key, [0] * rounds)
        s_counts = s_count_by_key.get(key, [0] * rounds)
        for round_index in range(rounds):
            expected["joined"][round_index] = (
                expected["joined"][round_index]
                + tag(round_index, "join-key", key) * r_values[round_index] * s_values[round_index]
            ) % q
            expected["grouped"][round_index] = (
                expected["grouped"][round_index]
                + tag(round_index, "group-key", key) * r_counts[round_index] * s_counts[round_index]
            ) % q

    max_candidate = {name: 0 for name in RELATION_ARITIES}
    candidate_rows = 0
    for name, rows in candidate.items():
        for row in rows:
            candidate_rows += 1
            *coordinates, weight = row
            max_candidate[name] = max(max_candidate[name], abs(weight))
            for round_index in range(rounds):
                if name == "r":
                    term = weight * tag(round_index, "r-key", coordinates[0]) * tag(round_index, "r-value", coordinates[1])
                elif name == "s":
                    term = weight * tag(round_index, "s-key", coordinates[0]) * tag(round_index, "s-value", coordinates[1])
                elif name == "selection":
                    term = weight * tag(round_index, "sel-key", coordinates[0]) * tag(round_index, "sel-value", coordinates[1])
                elif name == "joined":
                    term = (weight * tag(round_index, "join-key", coordinates[0])
                            * tag(round_index, "join-r-value", coordinates[1])
                            * tag(round_index, "join-s-value", coordinates[2]))
                else:
                    term = weight * tag(round_index, "group-key", coordinates[0])
                observed[name][round_index] = (observed[name][round_index] + term) % q

    # Conservative integer embedding.  If an integer coefficient differs, this
    # ensures it remains nonzero in F_q before Schwartz--Zippel is applied.
    true_bounds = {
        "r": l1_r,
        "s": l1_s,
        "selection": l1_r,
        "joined": l1_r * l1_s,
        "grouped": l1_r * l1_s,
    }
    for name in RELATION_ARITIES:
        if max_candidate[name] + true_bounds[name] >= q:
            raise FactorizedRejected(f"{name} coefficient envelope is not injective in the field")

    for name in RELATION_ARITIES:
        if observed[name] != expected[name]:
            raise FactorizedRejected(f"{name} fingerprint differs from authoritative replay")

    return FactorizedReport(
        accepted=True,
        rounds=rounds,
        field=q,
        field_bits=q.bit_length(),
        ideal_soundness_numerator=3 ** rounds,
        ideal_soundness_denominator=q ** rounds,
        authoritative_epoch_count=len(log),
        authoritative_prefix_rows=prefix_rows,
        candidate_rows=candidate_rows,
        distinct_join_keys=len(set(r_by_key) | set(s_by_key)),
        expected_join_pairs_enumerated=0,
        candidate_commitment=actual_commitment,
    )


def _aggregate(log: dict[int, dict[str, Any]], h: int, side: str) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = {}
    absolute = 0
    for epoch_id in range(1, h + 1):
        for key, value, weight in log[epoch_id][side]:
            absolute += abs(weight)
            if absolute > MAX_INT:
                raise FactorizedRejected("authority integer envelope exceeded")
            pair = (key, value)
            result[pair] = result.get(pair, 0) + weight
    return {key: weight for key, weight in result.items() if weight}


def _dict(rows: Iterable[list[int]]) -> dict[tuple[int, ...], int]:
    return {tuple(row[:-1]): row[-1] for row in rows}


def verify_structural(records: Any, durable_h: Any, recovered: Any) -> bool:
    """Exact output-sensitive baseline with no expected-join materialization.

    It materializes R and S, checks every candidate join tuple locally, and uses
    the product of nonzero supports per key to establish join completeness.
    """
    candidate_rows = _image(recovered, nonnegative=True)
    candidate = {name: _dict(rows) for name, rows in candidate_rows.items()}
    log, h = _authority(records, durable_h)
    r = _aggregate(log, h, "r")
    s = _aggregate(log, h, "s")
    if any(weight < 0 for relation in (r, s) for weight in relation.values()):
        raise FactorizedRejected("target prefix is not a valid bag")
    if candidate["r"] != r or candidate["s"] != s:
        raise FactorizedRejected("candidate base relation differs from authoritative replay")
    selection = {key: weight for key, weight in r.items() if key[1] % 2 == 0}
    if candidate["selection"] != selection:
        raise FactorizedRejected("candidate selection differs from authoritative replay")

    r_by_key: dict[int, dict[int, int]] = {}
    s_by_key: dict[int, dict[int, int]] = {}
    for (key, value), weight in r.items():
        r_by_key.setdefault(key, {})[value] = weight
    for (key, value), weight in s.items():
        s_by_key.setdefault(key, {})[value] = weight
    expected_support = sum(len(values) * len(s_by_key.get(key, {}))
                           for key, values in r_by_key.items())
    if len(candidate["joined"]) != expected_support:
        raise FactorizedRejected("candidate join support is incomplete or contains extras")
    for (key, left, right), weight in candidate["joined"].items():
        expected_weight = r_by_key.get(key, {}).get(left, 0) * s_by_key.get(key, {}).get(right, 0)
        if expected_weight == 0 or weight != expected_weight:
            raise FactorizedRejected("candidate join tuple is incorrect")

    grouped: dict[tuple[int], int] = {}
    for key in set(r_by_key) | set(s_by_key):
        value = sum(r_by_key.get(key, {}).values()) * sum(s_by_key.get(key, {}).values())
        if value:
            grouped[(key,)] = value
    if candidate["grouped"] != grouped:
        raise FactorizedRejected("candidate group result differs from authoritative replay")
    return True


def finite_field_detection_counts(q: int = 17) -> list[dict[str, int | str]]:
    """Exact small-field controls for degree-1/2/3 single-monomial errors."""
    if type(q) is not int or q < 5:
        raise ValueError("q must be at least five")
    rows: list[dict[str, int | str]] = []
    for component, degree in (("grouped", 1), ("base_or_selection", 2), ("joined", 3)):
        total = q ** degree
        accepted = 0
        for values in __import__("itertools").product(range(q), repeat=degree):
            product = 1
            for value in values:
                product = (product * value) % q
            accepted += int(product == 0)
        rows.append({
            "component": component,
            "degree": degree,
            "field": q,
            "assignments": total,
            "undetected": accepted,
            "detected": total - accepted,
            "schwartz_zippel_numerator": degree,
            "schwartz_zippel_denominator": q,
        })
    return rows


def adaptive_two_term_collision(seed: bytes | str, *, q: int = 101) -> dict[str, Any]:
    """Construct a challenge-adaptive nonzero residual with zero fingerprint.

    This is a finite-field negative control, not an admissible production image:
    it deliberately violates the post-commit timing contract.
    """
    seed_bytes = _seed_bytes(seed)
    commitment = hashlib.sha256(b"adaptive-control").digest()
    bound = seed_bytes + commitment
    first = (_field_element(bound, 0, "join-key", (1,), q)
             * _field_element(bound, 0, "join-r-value", (1,), q)
             * _field_element(bound, 0, "join-s-value", (1,), q)) % q
    second = (_field_element(bound, 0, "join-key", (2,), q)
              * _field_element(bound, 0, "join-r-value", (2,), q)
              * _field_element(bound, 0, "join-s-value", (2,), q)) % q
    # (delta_1, delta_2) = (second, -first) is nonzero unless both terms are
    # zero.  Deterministically try further coordinates in that rare case.
    coordinate = 2
    while first == 0 and second == 0:
        coordinate += 1
        second = (_field_element(bound, 0, "join-key", (coordinate,), q)
                  * _field_element(bound, 0, "join-r-value", (coordinate,), q)
                  * _field_element(bound, 0, "join-s-value", (coordinate,), q)) % q
    delta_first, delta_second = second % q, (-first) % q
    residual = (delta_first * first + delta_second * second) % q
    return {
        "field": q,
        "first_term": first,
        "second_term": second,
        "delta_first": delta_first,
        "delta_second": delta_second,
        "residual_nonzero": int(delta_first != 0 or delta_second != 0),
        "fingerprint": residual,
        "collision": int(residual == 0 and (delta_first != 0 or delta_second != 0)),
    }
