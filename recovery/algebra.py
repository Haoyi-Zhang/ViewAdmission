"""Integer-weighted finite relations; zero entries are removed, negatives kept.

Only the producer imports this module. The SQLite checker does not.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

Relation = dict[tuple[int, ...], int]


def normal(rows: Iterable[tuple[tuple[int, ...], int]]) -> Relation:
    out: Relation = {}
    for key, value in rows:
        if not isinstance(key, tuple) or any(type(x) is not int for x in key):
            raise ValueError("tuple coordinates must be integers")
        if type(value) is not int:
            raise ValueError("weights must be integers")
        out[key] = out.get(key, 0) + value
        if out[key] == 0:
            del out[key]
    return out


def plus(*relations: Relation) -> Relation:
    return normal((key, value) for rel in relations for key, value in rel.items())


def neg(rel: Relation) -> Relation:
    return {key: -value for key, value in rel.items()}


def select(rel: Relation) -> Relation:
    return {key: value for key, value in rel.items() if key[1] % 2 == 0}


def join(r: Relation, s: Relation) -> Relation:
    index: dict[int, list[tuple[int, int]]] = {}
    for (key, b), value in s.items():
        index.setdefault(key, []).append((b, value))
    return normal(((key, av, bv), rw * sw)
                  for (key, av), rw in r.items()
                  for bv, sw in index.get(key, []))


def group(j: Relation) -> Relation:
    return normal(((key[0],), value) for key, value in j.items())


def pairs(r: Relation, s: Relation) -> int:
    rs: dict[int, int] = {}
    ss: dict[int, int] = {}
    for k, _ in r: rs[k] = rs.get(k, 0) + 1
    for k, _ in s: ss[k] = ss.get(k, 0) + 1
    return sum(n * ss.get(k, 0) for k, n in rs.items())


@dataclass(eq=True)
class Image:
    r: Relation
    s: Relation
    selection: Relation
    joined: Relation
    grouped: Relation


def evaluate(r: Relation, s: Relation) -> Image:
    j = join(r, s)
    return Image(dict(r), dict(s), select(r), j, group(j))


def rebase(old: Image, target_r: Relation, target_s: Relation,
           cross_term: bool = True) -> Image:
    """Retarget an image. Correctness REQUIRES a correct old anchor.

    Does not validate or silently repair old view errors. Public admission is
    in checker.py; this routine remains exposed for the negative control.
    """
    dr = plus(target_r, neg(old.r))
    ds = plus(target_s, neg(old.s))
    dj = plus(join(dr, old.s), join(old.r, ds))
    if cross_term:
        dj = plus(dj, join(dr, ds))
    return Image(dict(target_r), dict(target_s),
                 plus(old.selection, select(dr)),
                 plus(old.joined, dj),
                 plus(old.grouped, group(dj)))


def rebase_two_term(old: Image, target_r: Relation, target_s: Relation) -> Image:
    dr = plus(target_r, neg(old.r))
    ds = plus(target_s, neg(old.s))
    dj = plus(join(dr, old.s), join(target_r, ds))
    return Image(dict(target_r), dict(target_s),
                 plus(old.selection, select(dr)),
                 plus(old.joined, dj), plus(old.grouped, group(dj)))


def encode_relation(rel: Relation) -> list[list[int]]:
    return [list(key) + [value] for key, value in sorted(rel.items())]


def encode_image(image: Image) -> dict[str, list[list[int]]]:
    return {name: encode_relation(getattr(image, name))
            for name in ("r", "s", "selection", "joined", "grouped")}
