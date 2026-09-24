"""Exact small fixture and deterministic valid signed-update generator."""
from __future__ import annotations
import random
from .engine import Epoch


def small(n: int = 5) -> list[Epoch]:
    all_epochs = [
      Epoch(1, ((0,0,1),), ((0,0,1),)),
      Epoch(2, ((0,1,2),), ((1,1,1),)),
      Epoch(3, ((1,2,1),), ((0,1,2),)),
      Epoch(4, ((0,0,-1),), ((0,0,-1),)),
      Epoch(5, ((0,1,-1),), ((0,1,-1),))]
    if not 0 <= n <= 5: raise ValueError("fixture has at most five epochs")
    return all_epochs[:n]


def generated(n: int, seed: int = 20260914) -> list[Epoch]:
    if not 1 <= n <= 4096: raise ValueError("bounded generator requires 1..4096 epochs")
    rng = random.Random(seed)
    state = {"r": {}, "s": {}}
    result = []
    for i in range(1, n+1):
        deltas = {}
        for name in ("r", "s"):
            live = state[name]
            if live and rng.random() < 0.30:
                key = rng.choice(sorted(live))
                weight = -1
            else:
                key = (rng.randrange(8), rng.randrange(24))
                weight = 1
            live[key] = live.get(key, 0) + weight
            if live[key] == 0: del live[key]
            deltas[name] = ((key[0], key[1], weight),)
        result.append(Epoch(i, deltas["r"], deltas["s"]))
    return result
