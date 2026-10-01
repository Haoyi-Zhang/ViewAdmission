"""Optional one-worker limits for command-line entry points, never imports."""
from __future__ import annotations
import os
try:
    import resource
except ImportError:
    resource = None

def constrain(*, cpu_seconds: int = 900, memory_bytes: int = 1024**3) -> None:
    """Lower limits only; inherited hard limits are never raised."""
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    if resource is None:
        return
    for kind, desired in ((resource.RLIMIT_AS, memory_bytes),
                          (resource.RLIMIT_CPU, cpu_seconds)):
        soft, hard = resource.getrlimit(kind)
        cap = desired if hard == resource.RLIM_INFINITY else min(desired, hard)
        if soft != resource.RLIM_INFINITY:
            cap = min(cap, soft)
        resource.setrlimit(kind, (cap, hard))
