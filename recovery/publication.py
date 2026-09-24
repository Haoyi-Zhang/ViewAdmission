"""Logical immutable-object publication model, NOT a filesystem implementation.

Each flush publishes one entire immutable object. Publishing a root is atomic
and permitted only after all six referenced objects are durable. A simulated
crash discards staged objects; no sector tearing or OS durability is modeled.
"""
from __future__ import annotations
from copy import deepcopy

PARTS = ("r", "s", "selection", "joined", "grouped", "metadata")


class RecoveryPending(RuntimeError):
    pass


class Store:
    def __init__(self, initial: dict) -> None:
        if set(initial) != set(PARTS):
            raise ValueError("invalid initial image")
        self.stable = {("initial", key): deepcopy(value) for key, value in initial.items()}
        self.staged: dict = {}
        self.root = "initial"

    def prepare(self, image: dict) -> None:
        if set(image) != set(PARTS):
            raise ValueError("invalid image")
        self.staged = deepcopy(image)

    def flush(self, part: str) -> None:
        if part not in PARTS or part not in self.staged:
            raise ValueError("unstaged part")
        if ("candidate", part) in self.stable:
            if self.stable[("candidate", part)] != self.staged[part]:
                raise ValueError("immutable object collision")
        self.stable[("candidate", part)] = deepcopy(self.staged[part])

    def publish(self) -> None:
        if any(("candidate", part) not in self.stable for part in PARTS):
            raise ValueError("root would refer to a missing object")
        self.root = "candidate"

    def crash(self) -> None:
        self.staged = {}

    def read(self) -> dict:
        try:
            return {part: deepcopy(self.stable[(self.root, part)]) for part in PARTS}
        except KeyError as exc:
            raise ValueError("dangling root") from exc

    def read_committed(self, durable_h: int) -> dict:
        """Do not serve a complete but stale root while recovery is pending."""
        if type(durable_h) is not int or durable_h < 0:
            raise ValueError("invalid durable marker")
        image = self.read()
        metadata = image["metadata"]
        if (not isinstance(metadata,dict) or set(metadata) != {"target"}
            or type(metadata["target"]) is not int
            or metadata["target"] != durable_h):
            raise RecoveryPending("root is not the required committed prefix")
        return image
