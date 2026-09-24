#!/usr/bin/env python3
"""Read the exact delivered witnesses and independently check their outcomes."""
import json
from pathlib import Path
from recovery.checker import verify, verify_replay, Rejected, Oracle, trusted_log, aggregate
BASE=Path(__file__).resolve().parent

def main():
    checked=[]
    for filename in ("case-a.json","case-b.json","case-c.json"):
        case=json.loads((BASE/"cases"/filename).read_text())
        outcomes=[]
        for target_only in (False,True):
            try:
                if target_only: verify_replay(case["log"],case["durable_h"],case["certificate"]["recovered"])
                else: verify(case["log"],case["durable_h"],case["certificate"])
                outcomes.append(True)
            except Rejected: outcomes.append(False)
        expected=[True,True] if filename=="case-a.json" else [False,False]
        assert outcomes==expected,(filename,outcomes)
        checked.append({"case":filename,"two_endpoint_accepts":outcomes[0],"target_only_accepts":outcomes[1]})
    c=json.loads((BASE/"cases/case-d.json").read_text())
    assert c["server_before"]==c["server_after"] and c["receiver_before"]!=c["receiver_after"]
    checked.append({"case":"case-d.json","server_indistinguishable":True})
    c=json.loads((BASE/"cases/case-e.json").read_text()); log=trusted_log(c["log"]); sql=Oracle()
    try:
        states=[]
        for h in (c["h_left"],c["h_right"]):
            states.append(sql.evaluate(aggregate(log,list(range(1,h+1)),"r"),aggregate(log,list(range(1,h+1)),"s")))
        assert states[0]==states[1] and c["h_left"]!=c["h_right"]
    finally: sql.close()
    checked.append({"case":"case-e.json","distinct_prefixes_equal_images":True})
    print(json.dumps({"checked_cases":checked},indent=2))

if __name__=="__main__":main()
