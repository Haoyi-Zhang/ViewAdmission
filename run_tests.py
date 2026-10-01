#!/usr/bin/env python3
"""Run the retained unit tests and emit a machine-readable result to stdout."""
import json,os,resource,sys,time,unittest
from pathlib import Path
from resource_limits import constrain
constrain(cpu_seconds=120)
base=Path(__file__).resolve().parent
start=time.process_time()
suite=unittest.defaultTestLoader.discover(str(base/"tests"))
result=unittest.TextTestRunner(stream=sys.stderr,verbosity=1).run(suite)
print(json.dumps({"tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),"success":result.wasSuccessful(),"cpu_seconds":time.process_time()-start},indent=2))
sys.exit(0 if result.wasSuccessful() else 1)
