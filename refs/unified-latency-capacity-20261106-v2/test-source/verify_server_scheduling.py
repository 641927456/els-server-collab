"""Actual shared startup policy from an inherited BelowNormal/Low process."""
import bootstrap,hashlib,json,psutil,sys
from pathlib import Path
from els_server import __main__ as server
p=psutil.Process();p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS);p.ionice(psutil.IOPRIO_LOW)
before=dict(priority_class=int(p.nice()),IO_priority=int(p.ionice()));assert before==dict(priority_class=16384,IO_priority=1)
actual=server._normal_scheduling();assert actual==dict(priority_class=32,IO_priority=2)
source=Path(server.__spec__.origin);assert source==bootstrap.HERE/'experiments/combined-latency-v3/source/els_server/__main__.py'
assert not sys._is_gil_enabled()
out=dict(passed=True,own_process_only=True,inherited=before,actual=actual,actual_shared_source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),GIL_enabled=False,production_installed=False)
(bootstrap.HERE/'server-scheduling-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
