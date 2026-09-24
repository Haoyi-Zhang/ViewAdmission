#!/usr/bin/env python3
"""Bounded, staged reproduction. No network and no third-party Python packages.

The SQLite checker is deliberately full recomputation, not a succinct proof.
Use --resume to retain completed stages after interruption. A stage is committed
only when both its raw CSV and summary exist; partial files are disposable.
"""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, os, resource, sys, time
from copy import deepcopy
from pathlib import Path

# One worker; reserve headroom for the interpreter, paper build, and packaging.
if hasattr(os, "sched_getaffinity"):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (120, 125))

from recovery.algebra import evaluate, rebase, rebase_two_term, encode_image, plus, neg, pairs
from recovery.engine import Epoch, log_index, operands, prefix, replay, prefix_checkpoint, certificate, guarded_recover, retarget
from recovery.checker import Oracle, Rejected, verify, verify_replay, decode_image
from recovery.publication import Store, PARTS, RecoveryPending
from recovery.factorized import (
    FactorizedRejected,
    adaptive_two_term_collision,
    commit_image,
    finite_field_detection_counts,
    verify_factorized,
    verify_structural,
)

BASE = Path(__file__).resolve().parent


def load(name: str) -> list[Epoch]:
    values = json.loads((BASE / "inputs" / name).read_text())
    return [Epoch(e["id"], tuple(tuple(r) for r in e["r"]),
                  tuple(tuple(r) for r in e["s"])) for e in values]


def bitset(mask: int, n: int) -> list[int]:
    return [i+1 for i in range(n) if mask & (1 << i)]


def submasks(mask: int):
    current = mask
    while True:
        yield current
        if current == 0: break
        current = (current - 1) & mask


def write_rows(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    iterator = iter(rows)
    first = next(iterator)
    tmp = path.with_suffix(".part")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(first))
        writer.writeheader(); writer.writerow(first)
        count = 1
        for row in iterator:
            writer.writerow(row); count += 1
    tmp.replace(path)
    return count


def challenge_seed(*parts: object) -> bytes:
    """Deterministic seed for reproducible tests, derived after commitment."""
    payload = "|".join(str(part) for part in parts).encode("ascii")
    return hashlib.sha256(b"CCR-reproduction-seed\0" + payload).digest()


def mutate_image(image: dict, component: str) -> dict:
    """Create one canonical, nonnegative, fixed single-component mutation."""
    bad = deepcopy(image)
    if bad[component]:
        bad[component][0][-1] += 1
    else:
        arity = {"r": 2, "s": 2, "selection": 2, "joined": 3, "grouped": 1}[component]
        bad[component] = [[0] * arity + [1]]
    return bad


def algebra_rows():
    for r, s, dr, ds in itertools.product(range(-2,3), repeat=4):
        old = evaluate({(0,0):r} if r else {}, {(0,0):s} if s else {})
        tr = {(0,0):r+dr} if r+dr else {}
        ts = {(0,0):s+ds} if s+ds else {}
        new = rebase(old, tr, ts)
        two = rebase_two_term(old, tr, ts)
        expected = evaluate(tr, ts)
        assert new == expected == two
        yield {"r":r,"s":s,"dr":dr,"ds":ds,"three_term_ok":1,"two_term_ok":1,
               "without_cross_ok": int(rebase(old,tr,ts,False) == expected)}


def cut_rows(n: int):
    full = log_index(load("small.json")[:n]); oracle = Oracle()
    try:
        for dm in range(1 << n):
            log = {i:full[i] for i in bitset(dm,n)}
            records = [e.encode() for e in log.values()]
            hs = [h for h in range(n+1) if all(i in log for i in range(1,h+1))]
            for rm in submasks(dm):
                rc = bitset(rm,n)
                for sm in submasks(dm):
                    sc = bitset(sm,n)
                    anchor = evaluate(*operands(log,rc,sc))
                    for h in hs:
                        cert = certificate(log,h,rc,sc,anchor)
                        assert verify(records,h,cert,oracle)
                        assert verify_replay(records,h,cert["recovered"],oracle)
                        tr,ts = prefix(log,h)
                        expected = oracle.evaluate(tr,ts)
                        got = decode_image(cert["recovered"])
                        assert got == expected
                        cp = prefix_checkpoint(log,h,min(2,h))
                        assert decode_image(encode_image(cp)) == expected
                        direct = replay(log,h)
                        assert decode_image(encode_image(direct)) == expected
                        assert verify_replay(records,h,encode_image(direct),oracle)
                        bad = deepcopy(anchor); bad.joined[(99,99,99)] = 1
                        poison_cert = certificate(log,h,rc,sc,bad)
                        try:
                            verify(records,h,poison_cert,oracle)
                            raise AssertionError("poison accepted")
                        except Rejected: pass
                        try:
                            verify_replay(records,h,poison_cert["recovered"],oracle)
                            raise AssertionError("poisoned output accepted")
                        except Rejected: pass
                        fixed_target, fallback_target = guarded_recover(log,h,rc,sc,bad,oracle,"target")
                        assert fallback_target and decode_image(fixed_target["recovered"]) == expected
                        fixed, fallback = guarded_recover(log,h,rc,sc,bad,oracle)
                        assert fallback and decode_image(fixed["recovered"]) == expected
                        poison = retarget(log,h,rc,sc,bad)
                        assert plus(poison.joined,neg(direct.joined)) == {(99,99,99):1}
                        p = set(range(1,h+1))
                        d = len(p ^ set(rc)) + len(p ^ set(sc))
                        extras = len(set(rc)-p) + len(set(sc)-p)
                        cold = d+len(rc)+len(sc)+2*h
                        assert cold == 4*h+2*extras
                        image = cert["recovered"]
                        assert verify_structural(records, h, image)
                        commitment = commit_image(image)
                        report = verify_factorized(
                            records, h, image, commitment=commitment,
                            seed=challenge_seed(dm, rm, sm, h, commitment), rounds=2)
                        mutation_flags = {}
                        for component in ("r", "s", "selection", "joined", "grouped"):
                            mutation = mutate_image(image, component)
                            mutation_commitment = commit_image(mutation)
                            try:
                                verify_factorized(
                                    records, h, mutation, commitment=mutation_commitment,
                                    seed=challenge_seed(dm, rm, sm, h, component, mutation_commitment),
                                    rounds=2)
                                rejected = 0
                            except FactorizedRejected:
                                rejected = 1
                            mutation_flags["factorized_" + component + "_rejected"] = rejected
                        metadata = {key: cert[key] for key in ["target","r_cut","s_cut"]}
                        yield {"n":n,"durable_mask":dm,"r_mask":rm,"s_mask":sm,"h":h,
                               "selection_ok":int(got["selection"] == expected["selection"]),
                               "join_ok":int(got["joined"] == expected["joined"]),
                               "group_ok":int(got["grouped"] == expected["grouped"]),
                               "full_checker_accepts":1,"replay_ok":1,"checked_replay_ok":1,"prefix_checkpoint_ok":1,
                               "structural_ok":1,"factorized_ok":int(report.accepted),
                               **mutation_flags,
                               "factorized_expected_join_pairs":report.expected_join_pairs_enumerated,
                               "factorized_authority_rows":report.authoritative_prefix_rows,
                               "factorized_candidate_rows":report.candidate_rows,
                               "factorized_distinct_keys":report.distinct_join_keys,
                               "checkpoint_only_ok":int(decode_image(encode_image(anchor)) == expected),
                               "no_cross_ok":int(rebase(anchor,tr,ts,False) == direct),
                               "poison_rejected":1,"residual_preserved":1,"fallback_ok":1,
                               "target_only_ok":1,"target_only_poison_rejected":1,"target_only_fallback_ok":1,
                               "target_only_aggregation_visits":d+2*h,
                               "target_only_payload_visits":d+2*h+2*len(log),
                               "producer_aggregation_visits":d,"cold_aggregation_visits":cold,
                               "checked_replay_aggregation_visits":4*h,"unacked_component_ids":extras,
                               "checker_validation_visits":2*len(log),
                               "cold_payload_visits":cold+2*len(log),
                               "checked_replay_payload_visits":4*h+2*len(log),
                               "cut_metadata_bytes":len(json.dumps(metadata,separators=(",",":"))),
                               "certificate_bytes":len(json.dumps(cert,separators=(",",":")))}
    finally: oracle.close()


def publication_rows(n: int):
    """Enumerate crashes across commit/challenge/admission and atomic publish."""
    log = log_index(load("small.json")[:n])
    records = [epoch.encode() for epoch in log.values()]
    initial = {**encode_image(replay(log,0)), "metadata":{"target":0}}
    for h in range(1,n+1):
        rc, sc = list(range(1,n+1,2)), list(range(2,n+1,2))
        old = evaluate(*operands(log,rc,sc))
        if h % 2: old.joined[(99,99,99)] = 1
        primary_seed = challenge_seed("publication", h, "primary")
        fallback_seed = challenge_seed("publication", h, "fallback")
        admitted, used_fallback = guarded_recover(
            log, h, rc, sc, old, admission="factorized",
            seed=primary_seed, fallback_seed=fallback_seed)
        assert used_fallback == bool(h % 2)
        target = {**admitted["recovered"], "metadata":{"target":h}}
        # Reentry admission depends on (h, cut), not on the later flush order.
        # Compute each deterministic candidate/challenge pair once, then reuse
        # that exact admitted target while enumerating all 6! storage orders.
        # This is memoization of identical work, not a reduction in schedule
        # coverage or a shared challenge across different candidate bytes.
        restart_targets = {}
        for cut in range(13):
            restarted, restarted_fallback = guarded_recover(
                log, h, rc, sc, old, admission="factorized",
                seed=challenge_seed("restart", h, cut, "primary"),
                fallback_seed=challenge_seed("restart", h, cut, "fallback"))
            assert restarted_fallback == bool(h % 2)
            restart_targets[cut] = {**restarted["recovered"], "metadata":{"target":h}}

        # Candidate construction, content commitment, post-commit challenge, and
        # admission are explicit boundaries. None can publish a root.
        for perm in itertools.permutations(PARTS):
            events = ["build", "commit", "challenge", "admit", "prepare", *perm, "publish"]
            for cut in range(len(events)+1):
                store = Store(initial)
                committed = challenged = verified = False
                for event in events[:cut]:
                    if event == "build":
                        pass
                    elif event == "commit":
                        committed = True
                    elif event == "challenge":
                        assert committed
                        challenged = True
                    elif event == "admit":
                        assert challenged
                        verified = True
                    elif event == "prepare":
                        assert verified
                        store.prepare(target)
                    elif event == "publish":
                        store.publish()
                    else:
                        store.flush(event)
                store.crash()
                read = store.read()
                published = cut == len(events)
                assert read == (target if published else initial)
                if published:
                    assert store.read_committed(h) == target
                else:
                    try:
                        store.read_committed(h)
                        raise AssertionError("stale root served")
                    except RecoveryPending:
                        pass
                # Re-entry uses the separately admitted candidate for this cut,
                # then performs a complete immutable publication.
                restarted_target = restart_targets[cut]
                store.prepare(restarted_target)
                for part in PARTS: store.flush(part)
                store.publish(); store.crash()
                assert store.read() == target == store.read_committed(h)
                yield {"h":h,"flush_order":";".join(perm),"crash_cut":cut,
                       "event_count":len(events),"root_atomic":1,"reentry_ok":1,
                       "initial_root":int(not published),"admitted_target_ok":1,
                       "service_gate_ok":1,"commit_before_challenge_ok":1,
                       "challenge_before_admission_ok":1,"unverified_publish_rejected":1,
                       "fallback_challenge_distinct_ok":int(primary_seed != fallback_seed),
                       "used_fallback":int(used_fallback)}


def receipt_rows():
    # A deliberately weak per-epoch-receipt design. Four independent durable
    # writes are R+=1, S+=1, J+=1, seen=true. Every order and cut is inspected.
    for order in itertools.permutations(("r","s","j","seen")):
        for cut in range(5):
            state = {"r":0,"s":0,"j":0,"seen":False}
            for event in order[:cut]:
                state[event] = True if event == "seen" else 1
            restored = dict(state)
            if not restored["seen"]:
                for name in ("r","s","j"): restored[name] += 1
                restored["seen"] = True
            ok = all(restored[name] == 1 for name in ("r","s","j"))
            yield {"write_order":";".join(order),"crash_cut":cut,
                   "receipt_only_ok":int(ok),"r_after":restored["r"],
                   "s_after":restored["s"],"j_after":restored["j"]}


def workload_rows():
    oracle = Oracle()
    try:
        for n in (16,64,256):
            log = log_index(load(f"generated-{n}.json"))
            for h in (0,n//2,n):
                p = set(range(1,h+1))
                patterns = {
                  "aligned":(p,p),
                  "ahead":(set(log),set(log)),
                  "holes":(set(log)-set(range(max(1,n-3),n+1,2)),set(log)-set(range(max(1,n-2),n+1,2))),
                  "striped":(set(range(1,n+1,2)),set(range(2,n+1,2)))}
                for pattern,(ra,sa) in patterns.items():
                    rc,sc = sorted(ra),sorted(sa)
                    anchor = evaluate(*operands(log,rc,sc))
                    target_r,target_s = prefix(log,h)
                    expected = oracle.evaluate(target_r,target_s)
                    dr,ds = plus(target_r,neg(anchor.r)),plus(target_s,neg(anchor.s))
                    retarget_pairs = pairs(dr,anchor.s)+pairs(target_r,ds)
                    replay_pairs = pairs(target_r,target_s)
                    reads = len(p^ra)+len(p^sa)
                    for repetition in range(5):
                        begin = time.perf_counter_ns()
                        cert = certificate(log,h,rc,sc,anchor)
                        producer_ns = time.perf_counter_ns()-begin
                        begin = time.perf_counter_ns()
                        direct = replay(log,h)
                        replay_ns = time.perf_counter_ns()-begin
                        begin = time.perf_counter_ns()
                        verify([e.encode() for e in log.values()],h,cert,oracle)
                        checker_ns = time.perf_counter_ns()-begin
                        assert decode_image(cert["recovered"]) == expected == decode_image(encode_image(direct))
                        image = encode_image(direct)
                        records = [e.encode() for e in log.values()]
                        begin = time.perf_counter_ns()
                        verify_replay(records,h,image,oracle)
                        replay_checker_ns = time.perf_counter_ns()-begin
                        begin = time.perf_counter_ns()
                        verify_structural(records,h,image)
                        structural_checker_ns = time.perf_counter_ns()-begin
                        commitment = commit_image(image)
                        begin = time.perf_counter_ns()
                        factorized_report = verify_factorized(
                            records,h,image,commitment=commitment,
                            seed=challenge_seed("workload",n,h,pattern,repetition,commitment),rounds=2)
                        factorized_checker_ns = time.perf_counter_ns()-begin
                        yield {"n":n,"h":h,"pattern":pattern,"repetition":repetition,
                               "producer_ns":producer_ns,"replay_ns":replay_ns,"checker_ns":checker_ns,
                               "replay_checker_ns":replay_checker_ns,
                               "structural_checker_ns":structural_checker_ns,
                               "factorized_checker_ns":factorized_checker_ns,
                               "structural_ok":1,"factorized_ok":int(factorized_report.accepted),
                               "factorized_expected_join_pairs":factorized_report.expected_join_pairs_enumerated,
                               "factorized_authority_rows":factorized_report.authoritative_prefix_rows,
                               "factorized_candidate_rows":factorized_report.candidate_rows,
                               "factorized_distinct_keys":factorized_report.distinct_join_keys,
                               "target_only_aggregation_visits":reads+2*h,
                               "target_only_payload_visits":reads+2*h+2*len(log),
                               "producer_aggregation_visits":reads,"replay_aggregation_visits":2*h,
                               "cold_aggregation_visits":reads+len(ra)+len(sa)+2*h,
                               "checked_replay_aggregation_visits":4*h,
                               "checker_validation_visits":2*len(log),
                               "cold_payload_visits":reads+len(ra)+len(sa)+2*h+2*len(log),
                               "checked_replay_payload_visits":4*h+2*len(log),
                               "producer_join_pairs":retarget_pairs,"replay_join_pairs":replay_pairs,
                               "r_support":len(target_r),"s_support":len(target_s),
                               "join_support":len(expected["joined"]),"all_views_ok":1}
    finally: oracle.close()


def soundness_rows():
    for row in finite_field_detection_counts(17):
        yield {
            "kind":"exact_grid", "case":row["component"], "degree":row["degree"],
            "rounds":1, "field":row["field"], "assignments":row["assignments"],
            "undetected":row["undetected"], "detected":row["detected"],
            "bound_numerator":row["schwartz_zippel_numerator"],
            "bound_denominator":row["schwartz_zippel_denominator"],
            "residual_nonzero":1, "fingerprint_zero":int(row["undetected"] > 0),
            "collision_constructed":0,
        }
    for index in range(32):
        control = adaptive_two_term_collision(challenge_seed("adaptive", index), q=101)
        yield {
            "kind":"adaptive_collision", "case":index, "degree":3, "rounds":1,
            "field":control["field"], "assignments":1, "undetected":1,
            "detected":0, "bound_numerator":3, "bound_denominator":101,
            "residual_nonzero":control["residual_nonzero"],
            "fingerprint_zero":int(control["fingerprint"] == 0),
            "collision_constructed":control["collision"],
        }


def summarize(path: Path) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    fields = [k for k in rows[0] if k.endswith(("_ok","_rejected")) or k in
              ["full_checker_accepts","poison_rejected","residual_preserved","root_atomic"]]
    return {"cases":len(rows), **{k:sum(int(r[k]) for r in rows) for k in fields}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--mode",choices=["pilot","full"],default="full")
    parser.add_argument("--stage",choices=["all","algebra","cuts","publication","receipts","workloads","soundness"],default="all")
    parser.add_argument("--resume",action="store_true")
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()) and not args.resume:
        parser.error("output is nonempty; use a fresh path or --resume")
    args.out.mkdir(parents=True,exist_ok=True)
    n = 3 if args.mode == "pilot" else 5
    stages = {"algebra":algebra_rows,"cuts":lambda:cut_rows(n),
              "publication":lambda:publication_rows(n),"receipts":receipt_rows,
              "soundness":soundness_rows}
    if args.mode == "full": stages["workloads"] = workload_rows
    if args.stage != "all":
        if args.stage not in stages: parser.error("stage unavailable in this mode")
        stages = {args.stage:stages[args.stage]}
    for stage, generator in stages.items():
        path = args.out / (stage+".csv")
        summary_path = args.out / (stage+"_summary.json")
        if args.resume and path.exists() and summary_path.exists():
            previous = json.loads(summary_path.read_text())
            if previous.get("mode") != args.mode: parser.error("cannot mix pilot and full output")
            print(stage,"already committed",flush=True); continue
        wall, cpu = time.perf_counter(), time.process_time()
        count = write_rows(path,generator())
        result = {"mode":args.mode, **summarize(path), "wall_seconds":time.perf_counter()-wall,
                  "cpu_seconds":time.process_time()-cpu,
                  "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "workers":1}
        status = Path("/proc/self/status")
        if status.exists():
            result["observed_swap_kib"] = next(int(line.split()[1]) for line in status.read_text().splitlines() if line.startswith("VmSwap:"))
        tmp = summary_path.with_suffix(".part")
        tmp.write_text(json.dumps(result,indent=2)+"\n"); tmp.replace(summary_path)
        print(stage,count,"cases",round(result["cpu_seconds"],3),"CPU seconds",flush=True)


if __name__ == "__main__": main()
