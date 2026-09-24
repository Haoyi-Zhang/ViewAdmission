"""Independent, full-recomputation SQLite admission checker.

This module deliberately does not import the producer's algebra or engine.
It is not a succinct verifier and does not provide cryptographic authenticity.
Inputs must come from an independently supplied authoritative log and durable
commit marker. All tested SQL integers are within the conservative bound below.
"""
from __future__ import annotations
import sqlite3
from typing import Any

MAX_INT = (1 << 63) - 1


class Rejected(ValueError):
    pass


def read_relation(rows: Any, arity: int) -> dict[tuple[int, ...], int]:
    if not isinstance(rows, list):
        raise Rejected("relation is not a list")
    out = {}
    previous = None
    for row in rows:
        if not isinstance(row, list) or len(row) != arity + 1:
            raise Rejected("invalid relation row")
        if any(type(x) is not int or abs(x) > MAX_INT for x in row):
            raise Rejected("noninteger or out-of-range value")
        key, value = tuple(row[:-1]), row[-1]
        if value == 0 or (previous is not None and key <= previous):
            raise Rejected("relation is not strictly canonical")
        out[key] = value
        previous = key
    return out


def decode_image(image: Any) -> dict:
    names = {"r": 2, "s": 2, "selection": 2, "joined": 3, "grouped": 1}
    if not isinstance(image, dict) or set(image) != set(names):
        raise Rejected("wrong image schema")
    return {key: read_relation(image[key], arity) for key, arity in names.items()}


class Oracle:
    def __init__(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("CREATE TABLE r(k INTEGER,a INTEGER,w INTEGER);"
                              "CREATE TABLE s(k INTEGER,b INTEGER,w INTEGER);")

    def close(self) -> None:
        self.db.close()

    def evaluate(self, r: dict, s: dict) -> dict:
        # Bound absolute intermediate sums, not just the final signed total.
        br = sum(abs(x) for x in r.values())
        bs = sum(abs(x) for x in s.values())
        if br > MAX_INT or bs > MAX_INT or br * bs > MAX_INT:
            raise Rejected("SQL exact-integer envelope exceeded")
        for rel in (r, s):
            if any(type(c) is not int or abs(c) > MAX_INT for key in rel for c in key):
                raise Rejected("SQL coordinate envelope exceeded")
        self.db.execute("DELETE FROM r")
        self.db.execute("DELETE FROM s")
        self.db.executemany("INSERT INTO r VALUES(?,?,?)", ((*key, w) for key, w in r.items()))
        self.db.executemany("INSERT INTO s VALUES(?,?,?)", ((*key, w) for key, w in s.items()))
        queries = {
          "selection": "SELECT k,a,SUM(w) FROM r WHERE a % 2 = 0 GROUP BY k,a HAVING SUM(w) != 0",
          "joined": "SELECT r.k,r.a,s.b,SUM(r.w*s.w) FROM r JOIN s ON r.k=s.k GROUP BY r.k,r.a,s.b HAVING SUM(r.w*s.w) != 0",
          "grouped": "SELECT r.k,SUM(r.w*s.w) FROM r JOIN s ON r.k=s.k GROUP BY r.k HAVING SUM(r.w*s.w) != 0"}
        return {"r": dict(r), "s": dict(s), **{
            name: {tuple(row[:-1]): row[-1] for row in self.db.execute(q)}
            for name, q in queries.items()}}


def trusted_log(records: Any) -> dict[int, dict]:
    if not isinstance(records, list):
        raise Rejected("log must be an array")
    out: dict[int, dict] = {}
    for e in records:
        if not isinstance(e, dict) or set(e) != {"id", "r", "s"}:
            raise Rejected("wrong epoch schema")
        i = e["id"]
        if type(i) is not int or not 0 < i <= MAX_INT:
            raise Rejected("invalid epoch ID")
        for name in ("r", "s"):
            if not isinstance(e[name], list):
                raise Rejected("epoch relation must be a list")
            for row in e[name]:
                if (not isinstance(row, list) or len(row) != 3 or
                    any(type(x) is not int or abs(x) > MAX_INT for x in row)):
                    raise Rejected("invalid epoch delta")
        if i in out and out[i] != e:
            raise Rejected("conflicting duplicate epoch")
        out[i] = e
    return out


def aggregate(log: dict, cut: list[int], name: str) -> dict:
    if (not isinstance(cut, list) or any(type(i) is not int for i in cut)
        or cut != sorted(set(cut)) or any(i not in log for i in cut)):
        raise Rejected("invalid or unavailable cut")
    result: dict[tuple[int, int], int] = {}
    absolute_bound = 0
    for i in cut:
        for k, value, weight in log[i][name]:
            absolute_bound += abs(weight)
            if absolute_bound > MAX_INT:
                raise Rejected("log aggregate integer envelope exceeded")
            key = (k, value)
            result[key] = result.get(key, 0) + weight
    return {key: w for key, w in result.items() if w != 0}


def verify(records: list[dict], durable_h: int, cert: Any,
           oracle: Oracle | None = None) -> bool:
    log = trusted_log(records)
    if type(durable_h) is not int or not 0 <= durable_h <= len(log):
        raise Rejected("invalid durable marker")
    if any(i not in log for i in range(1, durable_h + 1)):
        raise Rejected("acknowledged prefix has a log hole")
    if (not isinstance(cert, dict) or
        set(cert) != {"target", "r_cut", "s_cut", "anchor", "recovered"}):
        raise Rejected("wrong certificate schema")
    if type(cert["target"]) is not int or cert["target"] != durable_h:
        raise Rejected("certificate target differs from independent marker")
    anchor = decode_image(cert["anchor"])
    recovered = decode_image(cert["recovered"])
    r = aggregate(log, cert["r_cut"], "r")
    s = aggregate(log, cert["s_cut"], "s")
    p = list(range(1, durable_h + 1))
    tr, ts = aggregate(log, p, "r"), aggregate(log, p, "s")
    if any(w < 0 for rel in (tr, ts) for w in rel.values()):
        raise Rejected("target prefix is not a valid bag")
    own = oracle is None
    sql = Oracle() if own else oracle
    assert sql is not None
    try:
        if anchor != sql.evaluate(r, s):
            raise Rejected("anchor is not the stated relational state")
        if recovered != sql.evaluate(tr, ts):
            raise Rejected("recovered image differs from replay")
    finally:
        if own: sql.close()
    return True


def verify_replay(records: list[dict], durable_h: int, recovered: Any,
                  oracle: Oracle | None = None) -> bool:
    """Strong replay baseline: check the complete target, with no anchor claim."""
    log = trusted_log(records)
    if type(durable_h) is not int or not 0 <= durable_h <= len(log):
        raise Rejected("invalid durable marker")
    p = list(range(1, durable_h + 1))
    if any(i not in log for i in p):
        raise Rejected("acknowledged prefix has a log hole")
    got = decode_image(recovered)
    tr, ts = aggregate(log, p, "r"), aggregate(log, p, "s")
    if any(w < 0 for rel in (tr, ts) for w in rel.values()):
        raise Rejected("target prefix is not a valid bag")
    own = oracle is None
    sql = Oracle() if own else oracle
    assert sql is not None
    try:
        if got != sql.evaluate(tr, ts):
            raise Rejected("recovered image differs from replay")
    finally:
        if own: sql.close()
    return True
