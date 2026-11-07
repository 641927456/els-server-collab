"""Reproduce premature fixture release against the exact historical CI queue."""
from pathlib import Path
import ast,asyncio,hashlib,json,threading,time,types,unittest,os,shutil,sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
W=Path(__file__).resolve().parent;G=W.parent/'repair-v10/git-delivery';O=W/'ci-queue-fixture-v1';O.mkdir(exist_ok=True)
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
inputs=read(G/'references/settlement-replay-fixture-20261030-v1/test-inputs.json');pin=inputs['files']['pinned-inputs/tests/test_peak_business_concurrency.py'];source=G/pin['source'];assert sha(source)==pin['sha256']
d=read(G/'references/server-structure-20261029-v1/delta.json');profile=read(G/d['candidate_profile']);queue=next(x for x in profile['channels']['local']['files']if x['path']=='els_server/business_queue.py');q=G/queue['source'];assert sha(q)==queue['sha256']
raw=source.read_text('utf8');tree=ast.parse(raw);cls=next(x for x in tree.body if isinstance(x,ast.ClassDef)and x.name=='QueueTests')
selected=[x.name for x in cls.body if isinstance(x,ast.AsyncFunctionDef)and 'self.gate.wait(3)'in ast.get_source_segment(raw,x)]
assert len(selected)==5,selected
fixed=raw.replace('self.gate.wait(3)','self.gate.wait()');assert fixed!=raw and fixed.count('self.gate.wait()')==5
(O/'test_peak_business_concurrency.py').write_text(fixed,'utf8')
base=Path(read(W/'delivery/delivery-plan.json')['full_source']);runtime=O/'runtime'
for row in profile['channels']['local']['files']:
 if not(row['path'].startswith('els_server/')or row['path']=='config/combat_rules.json'):continue
 source_path=G/row.get('source','_missing_')
 if not source_path.is_file():source_path=base/row['path']
 assert source_path.is_file()and sha(source_path)==row['sha256'],row['path']
 target=runtime/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():shutil.copyfile(source_path,target)
 else:assert sha(target)==row['sha256']
sys.path[:0]=[str(runtime),str(base/'tools/pylibs')]
(O/'work').mkdir(exist_ok=True);os.chdir(O/'work')
qscope={};exec(compile(q.read_bytes(),str(q),'exec'),qscope)
def run(text,names):
 tree=ast.parse(text);c=next(x for x in tree.body if isinstance(x,ast.ClassDef)and x.name=='QueueTests')
 env=dict(asyncio=asyncio,ThreadPoolExecutor=ThreadPoolExecutor,threading=threading,time=time,unittest=unittest,SimpleNamespace=SimpleNamespace,BoundedBusinessQueue=qscope['BoundedBusinessQueue'])
 exec(compile(ast.Module(body=[c],type_ignores=[]),'exact-CI-fixture','exec'),env)
 result=unittest.TestResult();start=time.monotonic();unittest.TestSuite(env['QueueTests'](n)for n in names).run(result)
 return dict(passed=result.wasSuccessful(),tests=result.testsRun,seconds=time.monotonic()-start,errors=[dict(test=str(t),error=e.splitlines()[-1])for t,e in result.errors],failures=[str(t)for t,_ in result.failures])
needle="        fresh = [self.submit(lambda: called.append('fresh')) for _ in range(64)]"
assert raw.count(needle)==fixed.count(needle)==1
delay='        await asyncio.sleep(3.15)\n'
old=run(raw.replace(needle,delay+needle),['test_cancellation_storm_does_not_return_capacity_early']);assert not old['passed']and any('TimeoutError'in x['error']for x in old['errors']),old
new=run(fixed.replace(needle,delay+needle),['test_cancellation_storm_does_not_return_capacity_early']);assert new['passed'],new
normal=run(fixed,selected);assert normal['passed'],normal
out=dict(passed=True,scope='Historical CI fixture only; no production queue or client payload change',
 cause='The blocking worker uses gate.wait(3) and can return before the cancellation/waiter assertions. A scheduling phase longer than 3 seconds makes waiters==64 unreachable even when capacity accounting is correct. The fixture should wait for its explicit gate; asyncTearDown already always releases it.',
 original_test_sha256=pin['sha256'],fixed_test_sha256=sha(O/'test_peak_business_concurrency.py'),pinned_queue=queue,
 controlled_delay_seconds=3.15,old_fixture=old,fixed_fixture=new,affected_tests=selected,affected_normal=normal,
 live_queue_modified=False,historical_manifests_modified=False,original_CI_elapsed_phase_not_logged=True)
(O/'verification.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out))
