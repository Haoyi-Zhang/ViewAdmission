#!/usr/bin/env python3
"""One-worker complete finite reproduction; refuses to overwrite existing output."""
from __future__ import annotations
import argparse,json,os,resource,subprocess,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True,type=Path)
    ap.add_argument("--compare",type=Path)
    args=ap.parse_args();out=args.out.resolve()
    if out.exists():ap.error("output path already exists; choose a fresh directory")
    reference = args.compare.resolve() if args.compare is not None else None
    if reference is not None and not reference.is_dir():
        ap.error("comparison directory does not exist; paths are relative to the current directory")
    from resource_limits import constrain
    constrain(cpu_seconds=900)
    records=[];wall=time.perf_counter()
    def execute(label,arguments,save=None):
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        start=time.perf_counter()
        result=subprocess.run([sys.executable,*arguments],cwd=BASE,text=True,capture_output=True,timeout=950)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        records.append({"step":label,"returncode":result.returncode,"cpu_seconds":after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,"wall_seconds":time.perf_counter()-start})
        if result.returncode:
            sys.stderr.write(result.stdout+result.stderr)
            raise RuntimeError(label+" failed; partial outputs remain for inspection")
        if save:(out/save).write_text(result.stdout)
        print(label,"completed",flush=True)
    execute("finite-sweep",["reproduce.py","--mode","full","--out",str(out)])
    execute("boundary-controls",["protocol_controls.py","--out",str(out)])
    execute("unit-tests",["run_tests.py"],"unit_tests.json")
    execute("stored-cases",["check_cases.py"],"case_checks.json")
    execute("end-to-end-demo",["demo.py","--poison","--admission","factorized"],"demo.json")
    command=["verify_results.py",str(out),"--deep"]
    if reference is not None:command += ["--compare",str(reference)]
    execute("reconciliation",command,"reconciliation.json")
    usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    result={"steps":records,"child_cpu_seconds":sum(r["cpu_seconds"] for r in records),"wall_seconds":time.perf_counter()-wall,"peak_child_rss_kib":usage.ru_maxrss,"concurrent_workers":1,"comparison":"all deterministic raw columns; timings excluded" if args.compare else "coverage and SQL controls"}
    (out/"execution.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
