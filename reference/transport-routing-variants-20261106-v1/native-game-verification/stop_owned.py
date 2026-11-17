"""Request this owned probe's original stop-file cleanup, with PID/time checks."""
from pathlib import Path
import json,re,sys
sys.path.insert(0,'G:/els/tools/pylibs');import psutil
root=Path(__file__).resolve().parent
assert re.fullmatch(r'family1(?:-v[0-9]+)?',sys.argv[1])
n=(root/sys.argv[1]).resolve();assert n.parent==root
r=json.loads((n/'isolation-receipt.json').read_bytes())
assert not r.get('client_executable_unchanged'),'Already completed'
p=psutil.Process(r['client_pid'])
assert p.create_time()==r['client_created']and Path(p.exe()).resolve()==Path(r['client_exe']).resolve()
assert p.pid in r['job_membership_at_game_birth']['actual']['pids']
runs=list((n/'native-log').iterdir());assert len(runs)==1
run=runs[0];meta=json.loads((run/'client-process.json').read_bytes())
assert meta['pid']==p.pid and not run.is_symlink()and run.resolve().parent==n/'native-log'
(run/'client.stop').write_bytes(b'owned fixture ended; request original probe cleanup')
print(json.dumps(dict(own_stop_requested=True,pid=p.pid)))
