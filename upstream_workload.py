"""Replay reviewed upstream IVM inputs through owned checkers and logical store."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import re

from recovery.algebra import evaluate, encode_image
from recovery.engine import Epoch, certificate, log_index, operands
from recovery.checker import Oracle, aggregate, verify_replay
from recovery.factorized import (RELATION_ARITIES, verify_structural, verify_streaming,
    verify_factorized, commit_image)
from recovery.publication import Store, PARTS, RecoveryPending

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'external_inputs/feldera-join-inputs.rs'

def input_records(project=True):
    text=SOURCE.read_text(encoding='utf-8')
    sides=[]
    for side in (1,2):
        body=text.split(f'let mut input{side} = ',1)[1].split('.into_iter();',1)[0]
        batches=[]
        for block in re.findall(r'vec!\[(.*?)\]',body,re.S):
            rows=[]
            for key,payload,weight in re.findall(r'Tup2\(Tup2\((\d+), "([a-z])"\.to_string\(\)\), (-?\d+)(?:i64)?\)',block):
                key,weight=int(key),int(weight)
                if not project or key in (1,2):
                    rows.append([key,ord(payload)-ord('a'),weight])
            batches.append(rows)
        if len(batches)!=5:
            raise ValueError('upstream source batch parse failed')
        sides.append(batches)
    return [dict(id=i+1,r=r,s=s) for i,(r,s) in enumerate(zip(*sides))]

def calls(records,h,image):
    return dict(target=lambda:verify_replay(records,h,image),
        structural=lambda:verify_structural(records,h,image),
        streaming=lambda:verify_streaming(records,h,image),
        factorized=lambda:verify_factorized(records,h,image,
            commitment=commit_image(image),seed=b'upstream-fixed-input-control'*2))

def run():
    records=input_records()
    log=log_index([Epoch(row['id'],tuple(map(tuple,row['r'])),tuple(map(tuple,row['s']))) for row in records])
    oracle=Oracle()
    rows=[]
    try:
        for h in range(1,6):
            # Upstream inputs; owned recovery schedule, not an observed crash.
            rc=[i for i in range(1,h+1) if i%2]
            sc=[i for i in range(1,h+1) if not i%2]
            anchor=evaluate(*operands(log,rc,sc))
            expected=oracle.evaluate(aggregate({r['id']:r for r in records},list(range(1,h+1)),'r'),
                                     aggregate({r['id']:r for r in records},list(range(1,h+1)),'s'))
            expected={name:[list(key)+[weight] for key,weight in sorted(rel.items())]
                      for name,rel in expected.items()}
            good=certificate(log,h,rc,sc,anchor)['recovered']
            if good!=expected:
                raise ValueError('upstream retarget disagrees with independent SQL')
            accepted={mode:bool(call()) for mode,call in calls(records,h,good).items()}
            rejected={mode:0 for mode in accepted}
            for part,arity in RELATION_ARITIES.items():
                bad=deepcopy(good)
                if bad[part]: bad[part][0][-1]+=1
                else: bad[part]=[[0]*arity+[1]]
                for mode,call in calls(records,h,bad).items():
                    try: call()
                    except ValueError: rejected[mode]+=1
            # Derived anchor poison persists despite a correct transition.
            poisoned=deepcopy(anchor)
            first=next(iter(poisoned.joined), (1,0,1))
            poisoned.joined[first]=poisoned.joined.get(first,0)+1
            poison=certificate(log,h,rc,sc,poisoned)['recovered']
            if poison==good:
                raise ValueError('residual unexpectedly repaired by producer')
            published={}
            for mode in accepted:
                seq=iter((b'a'*32,b'b'*32))
                initial={name:[] for name in RELATION_ARITIES}|{'metadata':{'target':0}}
                store=Store(initial,records=records,target=h,mode=mode,_entropy=lambda:next(seq))
                store.prepare(poison|{'metadata':{'target':h}})
                store.commit(); store.challenge()
                try:
                    store.admit()
                except ValueError:
                    pass
                else:
                    raise ValueError('poison admitted by store')
                # Fully flushed wrong image is still not publishable.
                for part in PARTS: store.flush(part)
                try: store.publish()
                except ValueError: pass
                else: raise ValueError('unadmitted image published')
                try: store.read_committed(h)
                except RecoveryPending: pass
                else: raise ValueError('bootstrap served as target')
                store.prepare(good|{'metadata':{'target':h}})
                sid=store.commit(); seed=store.challenge()
                store.crash(); store.resume(sid)
                if store.challenge()!=seed:
                    raise ValueError('resume changed challenge')
                store.admit()
                for part in reversed(PARTS): store.flush(part)
                store.publish(); store.crash()
                published[mode]=store.read_committed(h)==good|{'metadata':{'target':h}}
            if not all(accepted.values()) or set(rejected.values())!={5} or not all(published.values()):
                raise ValueError('upstream admission predicates failed')
            rows.append(dict(h=h,r_cut=rc,s_cut=sc,candidate=good,poison=poison,
                join_rows=len(good['joined']),candidate_rows=sum(map(len,good.values())),
                accepted=accepted,component_rejections=rejected,checked_fallback_published=published))
    finally:
        oracle.close()
    # Full signed-ZSet input has negative base weights: do not claim support.
    full=input_records(False)
    invalid={name:[] for name in RELATION_ARITIES}
    full_results={}
    for mode,call in calls(full,5,invalid).items():
        try: call()
        except ValueError: full_results[mode]='rejected: full signed stream outside nonnegative target domain'
        else: raise ValueError('unsupported full stream accepted')
    return dict(source_revision='ae84fbb9fdb66d1d9e88154ccd9deeac12185007',
        provenance='upstream IVM regression inputs; owned recovery and corruption controls',
        retained_keys=[1,2],records=records,rows=rows,full_signed_stream=full_results,
        prefix_targets=5,methods=4,positive_checks=20,component_rejections=100,
        checked_publication_reentries=20,trusted_maintained_synopsis=False,
        scope='No Feldera execution, physical crash, observed incident, timing, or deployment-demand measurement')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--out',type=Path)
    group.add_argument('--check',type=Path)
    args=parser.parse_args()
    result=run()
    if args.check:
        if json.loads(args.check.read_text(encoding='utf-8')) != result:
            raise ValueError('retained upstream workload outcomes differ from current replay')
    else:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('prefix_targets','positive_checks','component_rejections','checked_publication_reentries')}))
