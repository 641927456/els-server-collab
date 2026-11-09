"""Bind the four-file delta and exercise real SQLite pending/failure/flush order."""
import ast,contextlib,copy,functools,hashlib,importlib.util,json,runpy,sqlite3,sys,tempfile,threading,time,types,unittest,weakref
from pathlib import Path
from types import SimpleNamespace
from contextvars import ContextVar
from unittest.mock import patch
A=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_bytes())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def tree(path):return ast.parse(path.read_bytes())
def owner(t,name):return next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name==name)
binding=read(A/'source-bindings.json');base=(A/binding['base_ref']).resolve();effective=dict(binding['base_source_files'])
assert len(effective)==28 and len(binding['changed_files'])==4
for name,sha in effective.items():assert digest(base/name)==sha
for name,row in binding['changed_files'].items():
 assert digest(A/'source'/name)==row['sha256']and digest(A/'parent'/name)==row['parent_sha256']
 tree(A/'source'/name);tree(A/'parent'/name);effective[name]=row['sha256']
assert effective==binding['effective_source_files']and len(effective)==30
for name,sha in binding['support_files'].items():assert digest(A/'support'/name)==sha
for name in ['native-clock-order.json','native-clock-failures.json','native-scene-clocks.json']:
 evidence=read(A/name);assert evidence['ok']
 assert {key.split('/',1)[1]:sha for key,sha in evidence['source'].items()}==effective
native=read(A/'native-clock-order.json');assert native['native']['real_TLS_move_delivered_before_held_clock_commit_completed']and native['native']['final_online_progress_cold_read_nonempty']
assert native['native']['owned_runtime_removed']and native['native']['connections']==0 and not native['native']['errors']
report=read(A/'twenty-town-five-minute.json');assert report['seconds']==300 and report['movement_requests']==35000 and report['peer_coordinate_deliveries']==665000
assert report['largest_clock_commit_ms']>100 and report['movement_handler_roundtrip']['max_ms']<30
assert not report['all_tail_latency_eliminated']and not report['production_installed']and not report['public_network_qualified']

# Only the periodic observation entry changes in Application; its original
# account/domain scopes, reward handlers and world ownership remain exact.
before=tree(A/'parent/els_server/application.py');after=tree(A/'source/els_server/application.py')
class ObserveEntry(ast.NodeTransformer):
 assignments=0;calls=0
 def visit_Assign(self,node):
  if any(isinstance(v,ast.Name)and v.id=='observe_clock'for v in node.targets):
   expected=ast.parse("observe_clock=(getattr(timer,'observe_background',timer.observe)if function.__name__=='periodic_notifications'else timer.observe)if activity else None").body[0]
   assert ast.dump(node)==ast.dump(expected);self.assignments+=1;return None
  return self.generic_visit(node)
 def visit_Call(self,node):
  if isinstance(node.func,ast.Name)and node.func.id=='observe_clock':
   assert len(node.args)==1 and ast.unparse(node.args[0])=='session'and not node.keywords
   self.calls+=1;node.func=ast.Attribute(value=ast.Name(id='timer',ctx=ast.Load()),attr='observe',ctx=ast.Load())
  return self.generic_visit(node)
normal=ObserveEntry();normal.visit(after);assert normal.assignments==1 and normal.calls==3 and ast.dump(before)==ast.dump(after)

# Reconstruct the original synchronous admission from submit. All physical
# SQL, FULL commit, savepoints, file binding and FIFO retirement stay exact.
before=tree(A/'parent/els_server/storage/clock_writer.py');after=tree(A/'source/els_server/storage/clock_writer.py')
imports=next(n for n in after.body if isinstance(n,ast.ImportFrom)and n.module=='contextvars');assert [n.name for n in imports.names]==['Context','copy_context'];imports.names=imports.names[1:]
c=owner(after,'ClockWriter');wrapper=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='commit')
assert ast.dump(wrapper)==ast.dump(ast.parse('def commit(self,plans,*,stop):\n return writer_result(self.submit(plans,stop=stop))').body[0]);c.body.remove(wrapper)
submit=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='submit');submit.name='commit'
assert [v.arg for v in submit.args.kwonlyargs]==['stop','background']and submit.args.kw_defaults[-1].value is False
submit.args.kwonlyargs.pop();submit.args.kw_defaults.pop()
class SubmitAdmission(ast.NodeTransformer):
 busy=0;contexts=0
 def visit_If(self,node):
  expected=ast.parse('future.set_result(self._busy_report(plans));return future').body
  if [ast.dump(n)for n in node.body]==[ast.dump(n)for n in expected]:
   self.busy+=1;node.body=ast.parse('return self._busy_report(plans)').body
  return self.generic_visit(node)
 def visit_IfExp(self,node):
  assert ast.unparse(node)=='Context() if background else copy_context()';self.contexts+=1
  return ast.parse('copy_context()',mode='eval').body
normal=SubmitAdmission();normal.visit(submit);assert normal.busy==2 and normal.contexts==1
assert ast.dump(submit.body[-1])==ast.dump(ast.parse('return future').body[0]);submit.body[-1]=ast.parse('return writer_result(future)').body[0]
assert ast.dump(before)==ast.dump(after)

for name,cls in [('domain/attendance_online_2026.py','PairClocks'),('domain/online_clock_transaction.py','_ClockCommit')]:
 before=tree(A/'parent/els_server'/name);after=tree(A/'source/els_server'/name)
 if cls=='PairClocks':
  before.body.remove(owner(before,cls));after.body.remove(owner(after,cls));assert ast.dump(before)==ast.dump(after)
 else:
  for method in ['persist','writer','_restore_one']:
   pick=lambda t:next(n for n in owner(t,cls).body if isinstance(n,ast.FunctionDef)and n.name==method)
   assert ast.dump(pick(before))==ast.dump(pick(after))

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
for name in ['els_server','els_server.domain','els_server.storage']:
 package=types.ModuleType(name);package.__path__=[];sys.modules[name]=package
performance=types.ModuleType('els_server.performance');performance.clock_stage=lambda *a,**k:contextlib.nullcontext();performance.sqlite_observed=lambda **values:None;sys.modules[performance.__name__]=performance
load('els_server.cleanup',A/'support/els_server/cleanup.py')
load('els_server.storage.sqlite_timing',A/'support/els_server/storage/sqlite_timing.py')
load('els_server.storage.writer_errors',A/'support/els_server/storage/writer_errors.py')
writer_module=load('els_server.storage.clock_writer',A/'source/els_server/storage/clock_writer.py');ClockWriter=writer_module.ClockWriter
clock=load('els_server.domain.online_clock_transaction',A/'source/els_server/domain/online_clock_transaction.py');current_commit=clock.current_commit;finish_observation=clock.finish_observation
pair=types.ModuleType('els_server.domain.attendance_online_2026');pair.__dict__['weakref']=weakref;sys.modules[pair.__name__]=pair
node=owner(tree(A/'source/els_server/domain/attendance_online_2026.py'),'PairClocks');exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-PairClocks','exec'),pair.__dict__);PairClocks=pair.PairClocks
namespace=dict(globals(),bootstrap=SimpleNamespace(HERE=A),module=writer_module)
exec(compile((A/'portable_checks.py').read_bytes(),str(A/'portable_checks.py'),'exec'),namespace)
checks=namespace['transaction_checks']();assert len(checks)==4 and all(checks.values())
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(namespace['Cases']))
assert result.wasSuccessful()and result.testsRun==4
print(json.dumps(dict(ok=True,effective_source_files=30,changed_files=4,transaction_and_order_checks=8,original_SQL_and_FULL_commit_preserved=True)))
