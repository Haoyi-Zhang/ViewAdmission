#!/usr/bin/env python3
"""Reconcile coverage, negative controls, visit accounting and derived tables.

This is a result consistency check, not a proof assistant or external review.
The full SQL check in --deep does not import the producer algebra.
"""
from __future__ import annotations
import argparse, csv, itertools, json, math, statistics
from pathlib import Path
from recovery.checker import Oracle, aggregate, trusted_log

BASE = Path(__file__).resolve().parent
STAGES = ("algebra", "cuts", "publication", "receipts", "soundness", "workloads")


def read_rows(root, name):
    with (root/(name+".csv")).open(newline="") as f:
        return list(csv.DictReader(f))


def require(test, message):
    if not test: raise ValueError(message)


def canonical_rows(rows):
    return [{k:v for k,v in r.items() if not k.endswith("_ns") and k != "aux_peak_bytes"} for r in rows]


CONTROL_STAGES = ("protocol_controls", "domain_controls", "tag_controls", "memory_controls")


def validate_controls(root, compare=None):
    """Read back saved controls independently of the control generator."""
    data = {name: read_rows(root, name) for name in CONTROL_STAGES}
    summary = json.loads((root / "protocol_summary.json").read_text())
    for name, rows in data.items():
        require(summary["counts"][name] == len(rows), name + " summary count")
        if compare is not None:
            require(canonical_rows(rows) == canonical_rows(read_rows(compare, name)),
                    name + " changed deterministic outputs")
    base_cases = {"unadmitted-all-flushed", "wrong-marker", "forged-metadata",
                  "challenge-before-commit", "admit-before-challenge", "stale-marker"}
    for part in ("r", "s", "selection", "joined", "grouped", "metadata"):
        base_cases.update({"after-admission-" + part, "after-publication-" + part})
    expected = {(mode, case) for mode in ("structural", "factorized", "target")
                for case in base_cases}
    expected |= {("factorized", "fallback-cut-" + str(i)) for i in range(5)}
    expected |= {("factorized", prefix + kind) for prefix in
                 ("repeat-seed-", "equivalent-fallback-") for kind in ("bytes", "str")}
    actual = [(r["mode"], r["case"]) for r in data["protocol_controls"]]
    require(len(actual) == len(expected) and set(actual) == expected,
            "protocol control identity/uniqueness")
    require(all(r["rejected"] == "1" for r in data["protocol_controls"]),
            "failed protocol rejection")

    field = 2**127 - 1
    expected = {(mode, case): int(case == "positive-endpoint")
                for mode in ("target", "structural", "factorized")
                for case in ("variation", "positive-endpoint", "negative-minimum", "negative-nonbag")}
    expected.update({("factorized", "nonproduction-modulus-" + str(q)): 0
                     for q in (4, 17, 101, True, field + 2)})
    seen = set()
    for row in data["domain_controls"]:
        key = (row["mode"], row["case"])
        require(key in expected and key not in seen, "domain control identity/uniqueness")
        seen.add(key)
        require(row["accepted"] == row["expected"] == str(expected[key]),
                "domain control outcome")
    require(seen == set(expected), "missing domain control")
    tags = data["tag_controls"]
    require(len(tags) == 3 and {r["case"] for r in tags} ==
            {"key-payload-domain-merge", "omitted-join-equation", "sum-instead-of-product"},
            "tag control identity/uniqueness")
    require(all(r["correct_control"] == r["weakened_behavior_observed"] == "1" for r in tags),
            "tag mutant not exposed")
    expected = {("cartesian-fixed-K", str(n), mode) for n in (8, 32, 128)
                for mode in ("structural", "factorized")}
    expected |= {("cancellation", str(n), "aggregate") for n in (8, 32, 128)}
    seen = set()
    for row in data["memory_controls"]:
        key = (row["family"], row["n"], row["mode"])
        require(key in expected and key not in seen, "memory control identity/uniqueness")
        seen.add(key); n = int(row["n"])
        require(int(row["resident_input_rows"]) == 2*n, "memory input rows")
        require(row["peak_keys"] == "1" and row["tag_cache_entries"] == "0", "memory structural count")
        if row["family"] == "cartesian-fixed-K":
            require(int(row["candidate_join_rows"]) == n*n and int(row["aux_peak_bytes"]) > 0,
                    "Cartesian candidate/allocation count")
        else:
            require(row["candidate_join_rows"] == row["final_aggregate_entries"] == "0",
                    "cancellation retained entries")
    require(seen == expected, "missing memory control")
    require(summary["mod4_zeros"] == 56 and summary["mod4_assignments"] == 64,
            "composite-ring counterexample")
    require(summary["exact_probability_numerator"] == 9 and
            summary["exact_probability_denominator"] == field**2 and
            summary["ideal_bound_less_than_two_to_minus_250"] is True,
            "probability expression mismatch")
    # Integer comparisons, rather than trusting a saved Boolean.
    require(9 * 2**250 < field**2 and field**2 < 2**254, "probability inequality")
    return {name: len(rows) for name, rows in data.items()}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--tex", type=Path)
    args=ap.parse_args()
    control_counts=validate_controls(args.results, args.compare)
    data={s:read_rows(args.results,s) for s in STAGES}
    counts={"algebra":625,"cuts":5**6-4**6,"publication":5*math.factorial(6)*13,"receipts":120,"soundness":35,"workloads":180}
    for s, rows in data.items():
        require(len(rows)==counts[s],s+" row count")
        summary=json.loads((args.results/(s+"_summary.json")).read_text())
        require(summary["cases"]==len(rows) and summary["mode"]=="full",s+" summary scope")
        flags=[k for k in rows[0] if k.endswith(("_ok","_rejected")) or k in {"full_checker_accepts","residual_preserved","root_atomic"}]
        for k in flags:
            require(all(r[k] in {"0","1"} for r in rows),s+" nonboolean flag "+k)
            require(summary[k]==sum(int(r[k]) for r in rows),s+" summary mismatch "+k)
        require(summary["workers"]==1 and summary["observed_swap_kib"]==0,s+" resource scope")
        require(summary["peak_rss_kib"]<3.5*1024**2,s+" memory bound")
        if args.compare:
            require(canonical_rows(rows)==canonical_rows(read_rows(args.compare,s)),s+" changed deterministic outputs")

    # Independently enumerate expected endpoint identities rather than trusting a count alone.
    expected={(d,a,b,h) for d in range(32) for a in range(32) if a&~d==0
              for b in range(32) if b&~d==0 for h in range(6) if ((1<<h)-1)&~d==0}
    seen=set(); oracle=Oracle()
    full=trusted_log(json.loads((BASE/"inputs/small.json").read_text()))
    try:
        for row in data["cuts"]:
            d,a,b,h=(int(row[k]) for k in ("durable_mask","r_mask","s_mask","h"))
            key=(d,a,b,h); require(key not in seen,"repeated endpoint case"); seen.add(key)
            pm=(1<<h)-1
            diff=(pm^a).bit_count()+(pm^b).bit_count()
            extras=(a&~pm).bit_count()+(b&~pm).bit_count()
            visits={"producer_aggregation_visits":diff,"cold_aggregation_visits":4*h+2*extras,
                    "checked_replay_aggregation_visits":4*h,"checker_validation_visits":2*d.bit_count(),
                    "target_only_aggregation_visits":diff+2*h,"unacked_component_ids":extras}
            for k,v in visits.items(): require(int(row[k])==v,"visit mismatch "+k)
            for head in ("cold","checked_replay","target_only"):
                require(int(row[head+"_payload_visits"])==int(row[head+"_aggregation_visits"])+2*d.bit_count(),"payload total")
            for k in ("selection_ok","join_ok","group_ok","full_checker_accepts","replay_ok","checked_replay_ok","prefix_checkpoint_ok","structural_ok","factorized_ok","factorized_r_rejected","factorized_s_rejected","factorized_selection_rejected","factorized_joined_rejected","factorized_grouped_rejected","poison_rejected","residual_preserved","fallback_ok","target_only_ok","target_only_poison_rejected","target_only_fallback_ok"):
                require(row[k]=="1","unexpected failure "+k)
            for component in ("r","s","selection","joined","grouped"):
                require(row["structural_"+component+"_rejected"]=="1","structural mutation")
            require(int(row["factorized_expected_join_pairs"])==0,"factorized checker enumerated expected join pairs")
            if args.deep:
                ids=lambda m:[i+1 for i in range(5) if m&(1<<i)]
                log={i:full[i] for i in ids(d)}
                r,s=aggregate(log,ids(a),"r"),aggregate(log,ids(b),"s")
                tr,ts=aggregate(log,list(range(1,h+1)),"r"),aggregate(log,list(range(1,h+1)),"s")
                old=oracle.evaluate(r,s); target=oracle.evaluate(tr,ts)
                require(int(row["checkpoint_only_ok"])==int(old==target),"checkpoint control disagrees with SQL")
                dr={k:tr.get(k,0)-r.get(k,0) for k in tr.keys()|r.keys()}
                ds={k:ts.get(k,0)-s.get(k,0) for k in ts.keys()|s.keys()}
                dr={k:w for k,w in dr.items() if w}; ds={k:w for k,w in ds.items() if w}
                parts=[old["joined"],oracle.evaluate(dr,s)["joined"],oracle.evaluate(r,ds)["joined"]]
                wrong={}
                for part in parts:
                    for key,w in part.items(): wrong[key]=wrong.get(key,0)+w
                wrong={k:w for k,w in wrong.items() if w}
                require(int(row["no_cross_ok"])==int(wrong==target["joined"]),"cross-term control disagrees with SQL")
        require(seen==expected,"endpoint coverage differs from mathematical domain")
    finally: oracle.close()

    require({tuple(int(r[k]) for k in ("r","s","dr","ds")) for r in data["algebra"]}==set(itertools.product(range(-2,3),repeat=4)),"scalar coverage")
    for row in data["algebra"]:
        r,s,dr,ds=(int(row[k]) for k in ("r","s","dr","ds"))
        require(row["three_term_ok"]==row["two_term_ok"]=="1","algebra failure")
        require(int(row["without_cross_ok"])==int(dr*ds==0),"scalar negative control")

    parts=("r","s","selection","joined","grouped","metadata")
    actual={(int(r["h"]),r["flush_order"],int(r["crash_cut"])) for r in data["publication"]}
    target={(h,";".join(order),cut) for h in range(1,6) for order in itertools.permutations(parts) for cut in range(13)}
    require(actual==target and len(actual)==len(data["publication"]),"publication coverage")
    for row in data["publication"]:
        for key in ("root_atomic","reentry_ok","admitted_target_ok","service_gate_ok","commit_before_challenge_ok","challenge_before_admission_ok","unverified_publish_rejected","fallback_challenge_distinct_ok"):
            require(row[key]=="1","publication flag "+key)
        require(int(row["event_count"])==12,"publication event count")
        require(int(row["used_fallback"])==int(row["h"])%2,"publication admission path")
        require(int(row["initial_root"])==int(int(row["crash_cut"])<12),"publication root selection")

    exact=[r for r in data["soundness"] if r["kind"]=="exact_grid"]
    adaptive=[r for r in data["soundness"] if r["kind"]=="adaptive_collision"]
    require(len(exact)==3 and len(adaptive)==32,"soundness case partition")
    for row in exact:
        q=int(row["field"]); degree=int(row["degree"])
        require(q==17 and int(row["assignments"])==q**degree,"small-field assignment count")
        exact_zeros=q**degree-(q-1)**degree
        require(int(row["undetected"])==exact_zeros,"small-field zero count")
        require(exact_zeros<=degree*q**(degree-1),"Schwartz-Zippel control")
    require(all(r["residual_nonzero"]==r["fingerprint_zero"]==r["collision_constructed"]=="1" for r in adaptive),"adaptive collision control")

    actual={(r["write_order"],int(r["crash_cut"])) for r in data["receipts"]}
    require(actual=={(";".join(p),i) for p in itertools.permutations(("r","s","j","seen")) for i in range(5)},"receipt coverage")
    for row in data["receipts"]:
        order=row["write_order"].split(";"); cut=int(row["crash_cut"])
        delivered=set(order[:cut]); receipt="seen" in delivered
        vals={k:int(k in delivered)+int(not receipt) for k in ("r","s","j")}
        require(int(row["receipt_only_ok"])==int(all(v==1 for v in vals.values())),"receipt outcome")
        for k,v in vals.items(): require(int(row[k+"_after"])==v,"receipt state")

    tuples={(int(r["n"]),int(r["h"]),r["pattern"],int(r["repetition"])) for r in data["workloads"]}
    require(tuples=={(n,h,p,k) for n in (16,64,256) for h in (0,n//2,n) for p in ("aligned","ahead","holes","striped") for k in range(5)},"scale-check coverage")
    require(all(r["all_views_ok"]==r["structural_ok"]==r["factorized_ok"]=="1" for r in data["workloads"]),"scale-check failure")
    require(all(int(r["factorized_expected_join_pairs"])==0 for r in data["workloads"]),"workload checker enumerated expected joins")
    # Input shape and validity are checked independently of the random generator.
    input_bounds={}
    for n in (5,16,64,256):
        name="small.json" if n==5 else f"generated-{n}.json"
        records=json.loads((BASE/"inputs"/name).read_text()); log=trusted_log(records)
        require(set(log)==set(range(1,n+1)),"input ID coverage")
        maximum=0
        for h in range(n+1):
            r,s=(aggregate(log,list(range(1,h+1)),k) for k in ("r","s"))
            require(all(w>=0 for relation in (r,s) for w in relation.values()),"invalid canonical input prefix")
            maximum=max(maximum,sum(abs(w) for w in r.values())*sum(abs(w) for w in s.values()))
        input_bounds[str(n)]={"epochs":n,"max_prefix_join_absolute_envelope":maximum,"envelope_bits":maximum.bit_length()}

    cuts=data["cuts"]
    totals={k:sum(int(r[k]) for r in cuts) for k in cuts[0] if k.endswith(("_ok","_rejected")) or k in {"full_checker_accepts","residual_preserved"}}
    better=sum(int(r["target_only_aggregation_visits"])<int(r["checked_replay_aggregation_visits"]) for r in cuts)
    tie=sum(int(r["target_only_aggregation_visits"])==int(r["checked_replay_aggregation_visits"]) for r in cuts)
    result={"status":"reconciled finite evidence for the declared model; theorem and literature claims remain separately reviewed","counts":counts,"control_counts":control_counts,"cut_outcomes":totals,
            "target_only_aggregation_comparison":{"lower":better,"equal":tie,"higher":len(cuts)-better-tie},"input_bounds":input_bounds,
            "factorized_protocol":{"rounds":2,"field_bits":127,"expected_join_pairs_enumerated":0,"mutations_checked":5*len(cuts),"adaptive_controls":len(adaptive)},
            "unit_of_cost":"epoch-component payload visits and candidate rows; timings are diagnostic","deep_sql_controls_checked":args.deep}
    print(json.dumps(result,indent=2))
    if args.tex:
        unit_report=json.loads((args.results/"unit_tests.json").read_text())
        require(unit_report["success"] and unit_report["failures"]==unit_report["errors"]==unit_report["skipped"]==0,"unit report failure")
        macros={"UnitTests":unit_report["tests_run"],"AlgebraCases":625,"AlgebraOmissionFailures":400,"CutCases":len(cuts),"CutOmissionFailures":len(cuts)-totals["no_cross_ok"],
                "CheckpointFailures":len(cuts)-totals["checkpoint_only_ok"],"PublicationCases":counts["publication"],"ReceiptCases":120,"ReceiptFailures":72,
                "ScaleRows":180,"TargetLower":better,"TargetEqual":tie,"TargetHigher":len(cuts)-better-tie,
                "StructuralMutations":5*len(cuts),"FallbackSchedules":sum(int(r["used_fallback"]) for r in data["publication"]),"DirectSchedules":sum(not int(r["used_fallback"]) for r in data["publication"]),"FactorizedMutations":5*len(cuts),"FactorizedMutationMisses":5*len(cuts)-sum(totals[k] for k in ("factorized_r_rejected","factorized_s_rejected","factorized_selection_rejected","factorized_joined_rejected","factorized_grouped_rejected")),
                "AdaptiveCollisions":len(adaptive),"SoundnessGridAssignments":sum(int(r["assignments"]) for r in exact)}
        labels={16:"Sixteen",64:"SixtyFour",256:"TwoFiftySix"}
        for n in (16,64,256):
            rows=[r for r in data["workloads"] if int(r["n"])==n]
            suffix=labels[n]
            for key,prefix in (("replay_checker_ns","SQLMedian"),("structural_checker_ns","StructuralMedian"),("factorized_checker_ns","FactorizedMedian")):
                macros[f"{prefix}{suffix}"]=f"{statistics.median(int(r[key]) for r in rows)/1_000_000:.3f}"
            macros[f"AuthorityRows{suffix}"]=f"{statistics.median(int(r['factorized_authority_rows']) for r in rows):.0f}"
            macros[f"CandidateRows{suffix}"]=f"{statistics.median(int(r['factorized_candidate_rows']) for r in rows):.0f}"
        args.tex.parent.mkdir(parents=True,exist_ok=True)
        stage_cpu=sum(json.loads((args.results/(s+"_summary.json")).read_text())["cpu_seconds"] for s in STAGES)
        peak=max(json.loads((args.results/(s+"_summary.json")).read_text())["peak_rss_kib"] for s in STAGES)/1024
        extra="\\newcommand{\\StageCPUSeconds}{"+f"{stage_cpu:.2f}"+"}\n\\newcommand{\\PeakRSSMiB}{"+f"{peak:.1f}"+"}\n"
        def render(value):
            return f"{value:,}" if isinstance(value,int) else str(value)
        args.tex.write_text(extra+"% Derived from retained raw results; regenerate with verify_results.py.\n"+"".join("\\newcommand{\\"+k+"}{"+render(v)+"}\n" for k,v in macros.items()))

if __name__=="__main__": main()
