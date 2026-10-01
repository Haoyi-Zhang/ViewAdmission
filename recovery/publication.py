"""Admission-gated logical immutable objects and atomic service root.

Trusted constructor fixes authority and configuration. The producer API cannot
supply an accepted flag. Interpreter-private state is trusted: this is not a
Python sandbox, filesystem, concurrent writer, or physical power-loss model.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from .factorized import (FIELD, MAX_INT, FactorizedRejected, _authority,
                         _seed_bytes, commit_image, fresh_seed,
                         verify_factorized, verify_structural)
from .checker import verify_replay

PARTS = ("r", "s", "selection", "joined", "grouped", "metadata")
QUERY = "two-bases/even-left-selection/equi-key-join/group-key-counts/v1"

class RecoveryPending(RuntimeError):
    """A complete old root is not the requested authorized prefix."""

def _digest(value):
    result = hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=True).iterencode(value):
        result.update(chunk.encode("ascii"))
    return result.hexdigest()

class Store:
    def __init__(self, initial: dict, *, records: list | None = None,
                 target: int = 0, mode: str = "factorized", rounds: int = 2,
                 _entropy=None):
        if mode not in {"factorized", "structural", "target"}:
            raise ValueError("unsupported mode")
        if type(rounds) is not int or not 1 <= rounds <= 8:
            raise ValueError("invalid rounds")
        self.__records = deepcopy([] if records is None else records)
        _authority(self.__records, target)
        self.__config = {"target": target, "mode": mode, "rounds": rounds,
                         "field": FIELD, "integer_max": MAX_INT, "query": QUERY,
                         "encoding": "canonical-json-v1", "authority": _digest(self.__records)}
        self.__entropy = fresh_seed if _entropy is None else _entropy
        self.__used = set()
        self.__sessions = {}
        self.__next = 1
        self.__active = None
        self.__roots = {"initial": None}
        self._check(initial, 0)
        if any(initial[k] for k in PARTS if k != "metadata"):
            raise ValueError("bootstrap must be empty prefix zero")
        self.__initial = _digest(initial)
        self.stable = {("initial", k): deepcopy(v) for k, v in initial.items()}
        self.staged = {}
        self.root = "initial"

    @staticmethod
    def _check(image, h):
        if not isinstance(image, dict) or set(image) != set(PARTS):
            raise ValueError("invalid complete image")
        m = image["metadata"]
        if (not isinstance(m, dict) or set(m) != {"target"}
                or type(m["target"]) is not int or m["target"] != h):
            raise ValueError("metadata differs from trusted target")
        commit_image({k: image[k] for k in PARTS if k != "metadata"})

    def prepare(self, image):
        self._check(image, self.__config["target"])
        self.staged = deepcopy(image)
        self.__active = None

    def commit(self):
        self._check(self.staged, self.__config["target"])
        sid = self.__next
        self.__next += 1
        image = deepcopy(self.staged)
        self.__sessions[sid] = {"image": image, "descriptor": deepcopy(self.__config),
                                "binding": _digest([self.__config, image]),
                                "seed": None, "decision": None}
        self.__active = sid
        return sid

    def _session(self):
        if self.__active is None or self.__active not in self.__sessions:
            raise ValueError("no committed candidate")
        return self.__sessions[self.__active]

    def challenge(self):
        r = self._session()
        if r["seed"] is None:
            seed = _seed_bytes(self.__entropy())
            if seed in self.__used:
                raise ValueError("normalized challenge seed reused")
            # One durable logical event before returning entropy to the caller.
            self.__used.add(seed)
            r["seed"] = seed
        return r["seed"]

    def admit(self):
        r = self._session()
        if r["seed"] is None:
            raise ValueError("admission before durable challenge")
        if r["decision"] is False:
            raise FactorizedRejected("candidate already rejected")
        if r["decision"] is True:
            return True
        image = r["image"]
        self._check(image, self.__config["target"])
        if _digest([self.__config, image]) != r["binding"]:
            raise ValueError("commit binding changed")
        candidate = {k: image[k] for k in PARTS if k != "metadata"}
        try:
            if self.__config["mode"] == "factorized":
                seed = hashlib.sha256(r["seed"] + bytes.fromhex(r["binding"])).digest()
                verify_factorized(self.__records, self.__config["target"], candidate,
                                  commitment=commit_image(candidate), seed=seed,
                                  rounds=self.__config["rounds"])
            elif self.__config["mode"] == "structural":
                verify_structural(self.__records, self.__config["target"], candidate)
            else:
                verify_replay(self.__records, self.__config["target"], candidate)
        except ValueError:
            r["decision"] = False
            raise
        r["decision"] = True
        return True

    def resume(self, sid):
        if type(sid) is not int or sid not in self.__sessions:
            raise ValueError("unknown session")
        self.__active = sid
        self.staged = deepcopy(self.__sessions[sid]["image"])

    def _generation(self):
        return "uncommitted" if self.__active is None else f"candidate:{self.__active}"

    def flush(self, part):
        if part not in PARTS or part not in self.staged:
            raise ValueError("unstaged part")
        k = (self._generation(), part)
        if k in self.stable and self.stable[k] != self.staged[part]:
            raise ValueError("immutable object collision")
        self.stable[k] = deepcopy(self.staged[part])

    def _bound(self, generation, sid):
        r = self.__sessions.get(sid)
        if r is None or r["decision"] is not True:
            raise ValueError("no trusted admission")
        if r["descriptor"] != self.__config:
            raise ValueError("configuration changed")
        try:
            image = {p: self.stable[(generation, p)] for p in PARTS}
        except KeyError as e:
            raise ValueError("missing durable object") from e
        self._check(image, self.__config["target"])
        if _digest([self.__config, image]) != r["binding"]:
            raise ValueError("durable bytes differ from admitted candidate")
        return image

    def publish(self, durable_h=None):
        if durable_h is not None and (type(durable_h) is not int or durable_h != self.__config["target"]):
            raise ValueError("wrong publication marker")
        self._session()
        g = self._generation()
        self._bound(g, self.__active)
        self.__roots[g] = self.__active
        self.root = g

    def crash(self):
        self.staged = {}
        self.__active = None

    def read(self):
        if self.root == "initial":
            image = {p: self.stable[("initial", p)] for p in PARTS}
            if _digest(image) != self.__initial:
                raise ValueError("bootstrap modified")
        else:
            sid = self.__roots.get(self.root)
            if sid is None:
                raise ValueError("unbound root")
            image = self._bound(self.root, sid)
        return deepcopy(image)

    def read_committed(self, h):
        if type(h) is not int or not 0 <= h <= MAX_INT:
            raise ValueError("invalid marker")
        image = self.read()
        if image["metadata"]["target"] != h:
            raise RecoveryPending("complete root is not requested target")
        return image
