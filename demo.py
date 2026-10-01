#!/usr/bin/env python3
"""Small complete recovery -> admission -> logical-publication demonstration.

The deterministic seeds in factorized mode are test fixtures only.  Production
callers leave them unset so that each seed is sampled after its candidate is
committed.
"""
import argparse,json
from pathlib import Path
from recovery.engine import Epoch,log_index,operands,guarded_recover,replay
from recovery.algebra import evaluate,encode_image
from recovery.publication import Store,PARTS,RecoveryPending


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--poison",action="store_true")
    ap.add_argument("--admission",choices=("both","target","structural","factorized"),default="factorized")
    args=ap.parse_args()
    records=json.loads((Path(__file__).resolve().parent/"inputs/small.json").read_text())
    log=log_index([Epoch(e["id"],tuple(map(tuple,e["r"])),tuple(map(tuple,e["s"]))) for e in records])
    rc,sc=[1,3,5],[2,4];old=evaluate(*operands(log,rc,sc))
    if args.poison:old.joined[(99,99,99)]=1
    kwargs={}
    if args.admission=="factorized":
        # Reproducible fixture challenges. guarded_recover fixes and commits the
        # primary and fallback candidates before consuming the corresponding seed.
        kwargs={"seed":bytes.fromhex("42"*32),"fallback_seed":bytes.fromhex("43"*32)}
    cert,fallback=guarded_recover(log,5,rc,sc,old,admission=args.admission,**kwargs)
    initial={**encode_image(replay(log,0)),"metadata":{"target":0}}
    candidate={**cert["recovered"],"metadata":{"target":5}}
    store=Store(initial, records=records, target=5,
                mode="target" if args.admission == "both" else args.admission,
                _entropy=lambda: b"P"*32)
    store.prepare(candidate)
    session=store.commit();store.challenge();store.admit()
    for part in PARTS[:3]:store.flush(part)
    store.crash();assert store.read()==initial
    try:
        store.read_committed(5)
        raise AssertionError("served stale root")
    except RecoveryPending:pass
    store.resume(session)
    for part in PARTS:store.flush(part)
    store.publish();store.crash();assert store.read()==candidate==store.read_committed(5)
    print(json.dumps({"admission":args.admission,"fallback_used":fallback,"published":store.read(),"model":"logical atomic objects; no filesystem"},indent=2))

if __name__=="__main__":main()
