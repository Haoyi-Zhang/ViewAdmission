"""Producer: normalized input log and endpoint certificate construction."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .algebra import Image, Relation, evaluate, normal, plus, neg, rebase_two_term, encode_image


@dataclass(frozen=True)
class Epoch:
    id: int
    r: tuple[tuple[int, int, int], ...]
    s: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        if type(self.id) is not int or self.id < 1:
            raise ValueError("epoch ID must be positive integer")
        for relation in (self.r, self.s):
            for row in relation:
                if len(row) != 3 or any(type(x) is not int for x in row):
                    raise ValueError("expected (key, value, signed weight)")

    def relation(self, name: str) -> Relation:
        return normal(((k, x), w) for k, x, w in getattr(self, name))

    def encode(self) -> dict:
        return {"id": self.id, "r": [list(x) for x in self.r],
                "s": [list(x) for x in self.s]}


def log_index(epochs: Iterable[Epoch]) -> dict[int, Epoch]:
    out: dict[int, Epoch] = {}
    for e in epochs:
        if e.id in out and out[e.id] != e:
            raise ValueError("conflicting duplicate epoch")
        out[e.id] = e
    return out


def operands(log: dict[int, Epoch], r_cut: Iterable[int],
             s_cut: Iterable[int]) -> tuple[Relation, Relation]:
    cuts = (tuple(r_cut), tuple(s_cut))
    for cut in cuts:
        if len(cut) != len(set(cut)) or any(i not in log for i in cut):
            raise ValueError("invalid operand cut")
    return tuple(plus(*(log[i].relation(name) for i in cut))
                 for name, cut in zip(("r", "s"), cuts))  # type: ignore


def prefix(log: dict[int, Epoch], h: int) -> tuple[Relation, Relation]:
    if type(h) is not int or h < 0:
        raise ValueError("invalid durable commit prefix")
    return operands(log, range(1, h + 1), range(1, h + 1))


def replay(log: dict[int, Epoch], h: int) -> Image:
    return evaluate(*prefix(log, h))


def prefix_checkpoint(log: dict[int, Epoch], h: int, c: int) -> Image:
    if not 0 <= c <= h:
        raise ValueError("checkpoint is not a prior prefix")
    image = replay(log, c)
    for i in range(c + 1, h + 1):
        image = rebase_two_term(image,
                plus(image.r, log[i].relation("r")),
                plus(image.s, log[i].relation("s")))
    return image


def certificate(log: dict[int, Epoch], h: int, r_cut: Iterable[int],
                s_cut: Iterable[int], old: Image | None = None) -> dict:
    rc, sc = sorted(r_cut), sorted(s_cut)
    anchor = old if old is not None else evaluate(*operands(log, rc, sc))
    target = retarget(log, h, rc, sc, anchor)
    return {"target": h, "r_cut": rc, "s_cut": sc,
            "anchor": encode_image(anchor), "recovered": encode_image(target)}


def retarget(log: dict[int, Epoch], h: int, rc: Iterable[int],
             sc: Iterable[int], old: Image) -> Image:
    """Read only symmetric-difference epoch-components (not full prefix payloads)."""
    if type(h) is not int or not 0 <= h <= len(log):
        raise ValueError("invalid prefix")
    wanted = set(range(1, h+1))
    if not wanted <= log.keys(): raise ValueError("prefix log hole")
    target = []
    for name, cut, value in (("r", tuple(rc), old.r), ("s", tuple(sc), old.s)):
        if len(cut) != len(set(cut)) or any(i not in log for i in cut):
            raise ValueError("invalid operand cut")
        have = set(cut)
        add = plus(*(log[i].relation(name) for i in sorted(wanted-have)))
        remove = plus(*(log[i].relation(name) for i in sorted(have-wanted)))
        target.append(plus(value, add, neg(remove)))
    return rebase_two_term(old, *target)


def guarded_recover(log: dict[int, Epoch], h: int, rc: Iterable[int],
                    sc: Iterable[int], old: Image, oracle=None, admission: str = "both",
                    *, seed: bytes | str | None = None,
                    fallback_seed: bytes | str | None = None,
                    rounds: int = 2) -> tuple[dict, bool]:
    """Admit a fixed candidate or fall back to empty-anchor replay.

    ``both`` checks the anchor and target with independent SQLite evaluation;
    ``target`` checks only the target with SQLite; ``structural`` uses the exact
    output-sensitive checker; and ``factorized`` commits the target before a
    fresh post-commit challenge.  A rejected fallback is checked again.

    Supplying seeds is only for deterministic experiments.  If factorized
    admission reaches the fallback, a distinct ``fallback_seed`` is required so
    that the fallback is fixed before its challenge.  With no supplied seeds,
    both challenges are sampled locally after the corresponding commitment.
    Missing or malformed authoritative inputs remain errors: fallback never
    bypasses admission.
    """
    from .checker import verify, verify_replay, Rejected
    from .factorized import (
        FactorizedRejected,
        commit_image,
        fresh_seed,
        verify_factorized,
        verify_structural,
    )
    if admission not in {"both", "target", "structural", "factorized"}:
        raise ValueError("admission must be both, target, structural, or factorized")
    records = [e.encode() for e in log.values()]

    def admit(candidate: dict, challenge: bytes | str | None) -> None:
        if admission == "both":
            verify(records, h, candidate, oracle)
        elif admission == "target":
            verify_replay(records, h, candidate["recovered"], oracle)
        elif admission == "structural":
            verify_structural(records, h, candidate["recovered"])
        else:
            commitment = commit_image(candidate["recovered"])
            verify_factorized(
                records,
                h,
                candidate["recovered"],
                commitment=commitment,
                seed=fresh_seed() if challenge is None else challenge,
                rounds=rounds,
            )

    candidate = certificate(log, h, rc, sc, old)
    rejection = (Rejected, FactorizedRejected)
    try:
        admit(candidate, seed)
        return candidate, False
    except rejection:
        fallback = certificate(log, h, [], [], evaluate({}, {}))
        if admission == "factorized" and seed is not None and fallback_seed is None:
            raise ValueError("deterministic factorized fallback requires a distinct fallback_seed")
        admit(fallback, fallback_seed)
        return fallback, True
