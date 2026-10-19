"""Compare independent compression against captured native reads and digest."""
import json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from resource_integrity import client_digest,validate_archive,ARCHIVE,LOCAL_DIGEST,ORIGINAL_DIGEST,encode_manifest,PINNED
from verify_experiment import evaluate

folder=BASE/'analysis/runs/20261012-170315-857104'
trace=[json.loads(l) for l in (folder/'launch-loopback-trace.jsonl').read_text(encoding='utf8').splitlines()]
events=[r.get('payload',{}) for r in trace]
data=b''.join(bytes.fromhex(e['hex']) for e in events if e.get('event')=='archive_integrity_read')
assert len(data)==10492
assert client_digest(data)==LOCAL_DIGEST
assert [e['hex'] for e in events if e.get('event')=='archive_integrity_actual']==[LOCAL_DIGEST]
assert encode_manifest(ORIGINAL_DIGEST)==next(e['expected_encoded'] for e in events if e.get('event')=='archive_integrity_input')
audit=json.loads((BASE/'analysis/archive-integrity-audit.json').read_text(encoding='utf-8-sig'))
assert len(audit)==36 and len(PINNED)==23
assert {p[0] for p in PINNED}=={r['file'] for r in audit if not r['matches']}
validate_archive(ARCHIVE,data)
try:validate_archive(ARCHIVE,data[:-1]+bytes([data[-1]^1]))
except RuntimeError:pass
else:raise AssertionError('Modified archive was accepted')
probe=json.loads((folder/'launch-loopback.json').read_text())
capture=json.loads((folder/'local-bootstrap.json').read_text())
assert not evaluate(trace,probe,capture)['startup_verified']
assert not evaluate(trace,probe,capture)['resource_integrity_verified']
print('PASS: independent digest equals native witness; altered archive refused; known popup fails startup acceptance.')
