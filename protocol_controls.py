#!/usr/bin/env python3
"""Finite API/domain/equation controls; memory is measured as verifier auxiliary state."""
from __future__ import annotations
import argparse,csv,hashlib,itertools,json,tracemalloc
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from recovery import factorized as fp
from recovery.publication import Store,PARTS,RecoveryPending
from recovery.checker import verify_replay
from recovery.engine import Epoch,log_index,guarded_recover
from recovery.algebra import evaluate,encode_image
EMPTY={name:[] for name in fp.RELATION_ARITIES}
RECORDS=[{"id":1,"r":[[1,2,1]],"s":[[1,3,1]]}]
GOOD={"r":[[1,2,1]],"s":[[1,3,1]],"selection":[[1,2,1]],"joined":[[1,2,3,1]],"grouped":[[1,1]]}
INITIAL={**EMPTY,"metadata":{"target":0}}
TARGET={**GOOD,"metadata":{"target":1}}
def check(value,message):
    if not value:raise AssertionError(message)
def rejects(call,kind=ValueError):
    try:call()
    except kind:return 1
    raise AssertionError("required rejection did not occur")
def store(mode="factorized",entropy=None):
    counter=itertools.count()
    return Store(INITIAL,records=RECORDS,target=1,mode=mode,
                 _entropy=entropy or (lambda:hashlib.sha256(str(next(counter)).encode()).digest()))
def setup(s,image=TARGET):
    s.prepare(image);sid=s.commit();s.challenge();s.admit();return sid
def flush(s):
    for p in PARTS:s.flush(p)
def protocol_rows():
    for mode in ("structural","factorized","target"):
        s=store(mode);s.prepare(TARGET);flush(s)
        yield {"mode":mode,"case":"unadmitted-all-flushed","rejected":rejects(s.publish)}
        s=store(mode);setup(s);flush(s)
        yield {"mode":mode,"case":"wrong-marker","rejected":rejects(lambda:s.publish(0))}
        for part in PARTS:
            s=store(mode);setup(s);flush(s)
            s.stable[(s._generation(),part)]={"target":1,"accepted":True} if part=="metadata" else []
            yield {"mode":mode,"case":"after-admission-"+part,"rejected":rejects(s.publish)}
            s=store(mode);setup(s);flush(s);s.publish()
            s.stable[(s.root,part)]={"target":0} if part=="metadata" else []
            yield {"mode":mode,"case":"after-publication-"+part,"rejected":rejects(lambda:s.read_committed(1))}
        s=store(mode);bad=deepcopy(TARGET);bad["metadata"]["accepted"]=True
        yield {"mode":mode,"case":"forged-metadata","rejected":rejects(lambda:s.prepare(bad))}
        s=store(mode)
        yield {"mode":mode,"case":"challenge-before-commit","rejected":rejects(s.challenge)}
        s.prepare(TARGET);sid=s.commit()
        yield {"mode":mode,"case":"admit-before-challenge","rejected":rejects(s.admit)}
        seed=s.challenge();s.crash();s.resume(sid);check(s.challenge()==seed,"challenge not durable")
        s.admit();flush(s);s.publish();s.crash();check(s.read_committed(1)==TARGET,"valid root")
        yield {"mode":mode,"case":"stale-marker","rejected":rejects(lambda:s.read_committed(0),RecoveryPending)}
    for cut in range(5):
        s=store();bad=deepcopy(TARGET);bad["joined"][0][-1]+=1
        s.prepare(bad);s.commit();first=s.challenge();rejects(s.admit)
        sid=None
        for e in ("prepare","commit","challenge","admit")[:cut]:
            if e=="prepare":s.prepare(TARGET)
            elif e=="commit":sid=s.commit()
            elif e=="challenge":check(s.challenge()!=first,"fallback seed reuse")
            else:s.admit()
        s.crash();pending=rejects(lambda:s.read_committed(1),RecoveryPending)
        if sid is None:s.prepare(TARGET);sid=s.commit()
        else:s.resume(sid)
        check(s.challenge()!=first,"fallback restart seed reuse");s.admit();flush(s);s.publish()
        check(s.read_committed(1)==TARGET,"fallback service")
        yield {"mode":"factorized","case":"fallback-cut-"+str(cut),"rejected":pending}
    seed=b'a'*32
    for value in (seed,seed.hex()):
        source=iter((seed,value));s=store(entropy=lambda:next(source))
        s.prepare(TARGET);s.commit();s.challenge();s.prepare(TARGET);s.commit()
        yield {"mode":"factorized","case":"repeat-seed-"+type(value).__name__,"rejected":rejects(s.challenge)}
        log=log_index([Epoch(1,((1,2,1),),((1,3,1),))]);old=evaluate({},{});old.joined[(99,99,99)]=1
        yield {"mode":"factorized","case":"equivalent-fallback-"+type(value).__name__,"rejected":rejects(lambda:guarded_recover(log,1,[],[],old,admission="factorized",seed=seed,fallback_seed=value))}
def domain_rows():
    M=fp.MAX_INT
    cases=[("variation",[{"id":1,"r":[[0,0,M]],"s":[]},{"id":2,"r":[[0,0,-M]],"s":[]},{"id":3,"r":[[0,0,1]],"s":[[0,0,1]]}],encode_image(evaluate({(0,0):1},{(0,0):1})),False),
           ("positive-endpoint",[{"id":1,"r":[[0,0,M]],"s":[[0,0,1]]}],encode_image(evaluate({(0,0):M},{(0,0):1})),True),
           ("negative-minimum",[{"id":1,"r":[[0,0,-(1<<63)]],"s":[]}],EMPTY,False),
           ("negative-nonbag",[{"id":1,"r":[[0,0,-M]],"s":[]}],EMPTY,False)]
    for name,records,image,expected in cases:
        for mode,fun in (("target",verify_replay),("structural",fp.verify_structural),("factorized",fp.verify_factorized)):
            kw={"commitment":fp.commit_image(image),"seed":b'x'*32} if mode=="factorized" else {}
            try:fun(records,len(records),image,**kw);accepted=True
            except ValueError:accepted=False
            check(accepted==expected,name+mode)
            yield {"case":name,"mode":mode,"accepted":int(accepted),"expected":int(expected)}
    for q in (4,17,101,True,fp.FIELD+2):
        rejects(lambda:fp.verify_factorized([],0,EMPTY,commitment=fp.commit_image(EMPTY),seed=b'x'*32,q=q))
        yield {"case":"nonproduction-modulus-"+str(q),"mode":"factorized","accepted":0,"expected":0}
def tag_rows():
    def tags(i,d,c):
        if d=="r-key":return {1:2,2:3}.get(c[0],4)
        if d=="r-value":return {1:5,2:7}.get(c[0],6)
        return 1+int.from_bytes(hashlib.sha256(repr((d,c)).encode()).digest()[:4],"big")%16
    def verify(image,override=tags):
        return fp._verify_factorized(RECORDS,1,image,commitment=fp.commit_image(image),seed=b't'*32,rounds=1,q=17,_tag_override=override)
    check(verify(GOOD).accepted,"honest small-field candidate")
    bad=deepcopy(GOOD);bad["r"]=[[2,1,1]];rejects(lambda:verify(bad))
    def merged(i,d,c):return {1:2,2:3}.get(c[0],4) if d in {"r-key","r-value"} else tags(i,d,c)
    check(verify(bad,merged).accepted,"domain-merge control did not expose transpose collision")
    yield {"case":"key-payload-domain-merge","correct_control":1,"weakened_behavior_observed":1}
    bad=deepcopy(GOOD);bad["joined"][0][-1]=2;rejects(lambda:verify(bad))
    def omit(expected,observed):
        for name in fp.RELATION_ARITIES:
            if name!="joined" and observed[name]!=expected[name]:raise fp.FactorizedRejected(name)
    with patch.object(fp,"_compare_fingerprints",omit):check(verify(bad).accepted,"omitted join equation control")
    yield {"case":"omitted-join-equation","correct_control":1,"weakened_behavior_observed":1}
    with patch.object(fp,"_join_term",lambda key,left,right:key*(left+right)):
        rejects(lambda:verify(GOOD))
    yield {"case":"sum-instead-of-product","correct_control":1,"weakened_behavior_observed":1}
def memory_rows():
    for n in (8,32,128):
        records=[{"id":1,"r":[[0,i,1] for i in range(n)],"s":[[0,i,1] for i in range(n)]}]
        image=encode_image(evaluate({(0,i):1 for i in range(n)},{(0,i):1 for i in range(n)}))
        for mode,fun in (("structural",fp.verify_structural),("factorized",fp.verify_factorized)):
            commitment=fp.commit_image(image)
            kw={"commitment":commitment,"seed":b'm'*32} if mode=="factorized" else {}
            tracemalloc.start();result=fun(records,1,image,**kw);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            if mode=="factorized":check(result.tag_cache_entries==0 and result.peak_accumulator_keys==1,"payload-sensitive verifier cache")
            yield {"family":"cartesian-fixed-K","n":n,"mode":mode,"resident_input_rows":2*n,
                   "candidate_join_rows":n*n,"aux_peak_bytes":peak,"tag_cache_entries":0,
                   "peak_keys":1,"final_aggregate_entries":""}
        records=[{"id":1,"r":[row for i in range(n) for row in ([i,i,1],[i,i,-1])],"s":[]}]
        log=fp._log(records);stats={};result=fp._aggregate(log,1,"r",metrics=stats)
        check(result=={} and stats["peak_entries"]==1,"cancellation retained dead keys")
        yield {"family":"cancellation","n":n,"mode":"aggregate","resident_input_rows":2*n,
               "candidate_join_rows":0,"aux_peak_bytes":"","tag_cache_entries":0,
               "peak_keys":stats["peak_entries"],"final_aggregate_entries":len(result)}
def write(path,rows):
    rows=list(rows)
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return len(rows)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    counts={name:write(a.out/(name+'.csv'),fun()) for name,fun in (("protocol_controls",protocol_rows),("domain_controls",domain_rows),("tag_controls",tag_rows),("memory_controls",memory_rows))}
    zeros=sum(2*x*y*z%4==0 for x,y,z in itertools.product(range(4),repeat=3));check(zeros==56,"mod4 count")
    from fractions import Fraction
    p=Fraction(9,fp.FIELD**2);check(Fraction(9,2**254)<p<Fraction(1,2**250),"probability bound")
    summary={"counts":counts,"mod4_zeros":zeros,"mod4_assignments":64,"exact_probability_numerator":9,"exact_probability_denominator":fp.FIELD**2,
             "ideal_bound_less_than_two_to_minus_250":True,"memory_scope":"auxiliary allocations after resident inputs are built; store snapshots excluded and separately documented"}
    (a.out/'protocol_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
