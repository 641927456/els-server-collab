"""Run only the contention regression against the accepted parent."""
import bootstrap
import importlib.util,json,unittest
from els_server.storage.sqlite_timing import _WriterTurn
def contended(turn):
    with turn.lock:return len(turn.waiters)>1
# Read-only test observation; admission and handoff remain the parent's code.
_WriterTurn.contended=contended
spec=importlib.util.spec_from_file_location('old_batch_regression',bootstrap.HERE/'test_writer_scheduling.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result=unittest.TestResult()
module.WriterSchedulingTests('test_contended_batch_yields_without_reordering_or_early_reply').run(result)
assert not result.errors and len(result.failures)==2,result.errors
assert all('Lists differ:'in failure for _,failure in result.failures)
out=dict(reproduced=True,parent=bootstrap.BASE.name,lanes=['death','coin'],
    observation='Both old writers execute the remaining eight ready jobs before the waiting writer can run',
    candidate_test_passed=False,expected_parent_regression_failures=len(result.failures))
(bootstrap.HERE/'old-batch-reproduction.json').write_text(json.dumps(out,indent=2),'utf8')
print(json.dumps(out))
