"""Bind archived bytes and run behavioral state/order/quota checks."""
import ast,hashlib,json,subprocess,sys
from pathlib import Path
A=Path(__file__).resolve().parent;ROOT=A.parents[1]
def tree(path):return ast.parse(path.read_bytes())
def cls(t,name):return next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name==name)
def main():
 b=json.loads((A/'source-bindings.json').read_bytes());assert len(b['files'])==17
 for rows in(b['files'],b['runtime_parent_files']):
  for row in rows.values():
   p=ROOT/row['source'];assert p.resolve().is_relative_to(A)and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];tree(p)
 before=tree(A/'runtime-parent/els_server/domain/native_session_sources.py');after=tree(A/'source/els_server/domain/native_session_sources.py')
 c=cls(after,'SessionSources');method=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='release_transient');c.body.remove(method)
 assert ast.dump(before)==ast.dump(after),'Original capture, cursor, authority receipts and sent logic must be retained'
 before=tree(A/'runtime-parent/els_server/config.py');after=tree(A/'source/els_server/config.py');c=cls(after,'ServerConfig')
 field=next(n for n in c.body if isinstance(n,ast.AnnAssign)and n.target.id=='egress_mbps');assert field.value.value==0.0;c.body.remove(field)
 post=next(n for n in c.body if isinstance(n,ast.FunctionDef)and n.name=='__post_init__')
 guards=[n for n in post.body if isinstance(n,ast.If)and any(isinstance(v,ast.Attribute)and v.attr=='egress_mbps'for v in ast.walk(n.test))]
 assert len(guards)==1;post.body.remove(guards[0]);assert ast.dump(before)==ast.dump(after),'Every existing configuration rule must be retained'
 before=tree(A/'runtime-parent/els_server/transport.py');after=tree(A/'source/els_server/transport.py')
 socket_imports=[n for n in after.body if isinstance(n,ast.Import)and len(n.names)==1 and n.names[0].name=='socket']
 assert len(socket_imports)==1;after.body.remove(socket_imports[0])
 for t in(before,after):
  c=cls(t,'GameServer');c.body=[n for n in c.body if not(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in('__init__','handle','close'))]
 assert ast.dump(before)==ast.dump(after),'Transport changes are restricted to sender lifetime and delivery'
 # The current online parent's party, quest, guide, shutdown and GM actor
 # ownership fixes are retained. Only these scheduling entry points differ.
 for name,methods in [('application.py',{'FriendsSession':{'__init__'},'Application':{'_dispatch','_worker_call'}}),('dungeon_workers.py',{'DungeonWorkers':{'publish'}}),('periodic_scheduler.py',{'PeriodicScheduler':{'_notify'}}),('domain/friends_world.py',{'Mailbox':{'append'}})]:
  before=tree(A/'runtime-parent/els_server'/name);after=tree(A/'source/els_server'/name)
  for t in(before,after):
   for owner,names in methods.items():
    c=cls(t,owner);c.body=[n for n in c.body if not(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in names)]
  if name=='periodic_scheduler.py':
   helpers=[n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='_town_notice_pending'];assert len(helpers)==1;after.body.remove(helpers[0])
   deliver=next(n for n in cls(after,'PeriodicScheduler').body if isinstance(n,ast.AsyncFunctionDef)and n.name=='_deliver')
   guard=next(n for n in deliver.body if isinstance(n,ast.Try))
   assignments=[n for n in guard.finalbody if isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='queued_town_notice'for v in n.targets)]
   assert len(assignments)==1;guard.finalbody.remove(assignments[0])
   tests=[n for n in ast.walk(deliver)if isinstance(n,ast.IfExp)and ast.unparse(n.test)=='pending or queued_town_notice'];assert len(tests)==1;tests[0].test=ast.Name(id='pending',ctx=ast.Load())
  if name=='application.py':
   after.body=[n for n in after.body if not(isinstance(n,ast.ImportFrom)and n.module=='contextvars')and not(isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='_town_move_wakes'for v in n.targets))]
  if name=='domain/friends_world.py':
   calls=[n for n in ast.walk(after)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='get_inventory_snapshot'and n.keywords]
   assert len(calls)==3
   for call in calls:
    assert len(call.keywords)==1 and call.keywords[0].arg=='equipped_only'and call.keywords[0].value.value is True
    call.keywords=[]
  assert ast.dump(before)==ast.dump(after),name+' changed outside scheduling/public appearance scope'
 before=tree(A/'runtime-parent/els_server/protocol/dungeon_messages.py');after=tree(A/'source/els_server/protocol/dungeon_messages.py')
 # Normalize the original HP slice into the shared pure builder; all other
 # member fields, including the newly installed achievement tail, stay exact.
 class OriginalProfile(ast.NodeTransformer):
  def visit_If(self,node):
   if (any(isinstance(v,ast.ImportFrom)and v.module=='els_server.domain.character_stats'and any(a.name=='combat_values'for a in v.names)for v in node.body)
       and ast.unparse(node.test)=='capture is not None'):return None
   return self.generic_visit(node)
  def visit_Call(self,node):
   if isinstance(node.func,ast.Name)and node.func.id=='combat_attributes'and len(node.args)==2:
    node.func.id='member_profile';node.keywords=[ast.keyword(arg='absolute_hp',value=ast.parse('capture is not None',mode='eval').body)]
   return self.generic_visit(node)
 before=OriginalProfile().visit(before)
 after.body=[n for n in after.body if not(isinstance(n,ast.FunctionDef)and n.name=='member_profile')]
 assert ast.dump(before)==ast.dump(after),'Native member fields outside the shared profile must stay exact'
 for name,names in [('domain/elixir_flow.py',{'profiles'})]:
  before=tree(A/'runtime-parent/els_server'/name);after=tree(A/'source/els_server'/name)
  for t in(before,after):t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name in names)]
  assert ast.dump(before)==ast.dump(after),name+' changed outside native profile construction'
 before=tree(A/'runtime-parent/els_server/storage/inventory_state.py');after=tree(A/'source/els_server/storage/inventory_state.py')
 after.body=[n for n in after.body if not(isinstance(n,ast.FunctionDef)and n.name in('load_equipped_items','_load_equipped_items'))]
 load=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='_load_items')
 assert load.args.kwonlyargs[-1].arg=='bag_group'and load.args.kw_defaults[-1].value is None
 load.args.kwonlyargs.pop();load.args.kw_defaults.pop()
 filters=[n for n in load.body if isinstance(n,ast.If)and ast.unparse(n.test)=='bag_group is not None'];assert len(filters)==1;load.body.remove(filters[0])
 snapshot=next(n for n in cls(after,'InventoryState').body if isinstance(n,ast.FunctionDef)and n.name=='snapshot')
 assert snapshot.args.kwonlyargs[0].arg=='equipped_only'and snapshot.args.kw_defaults[0].value is False
 snapshot.args.kwonlyargs=[];snapshot.args.kw_defaults=[]
 choices=[n for n in ast.walk(snapshot)if isinstance(n,ast.Call)and isinstance(n.func,ast.IfExp)];assert len(choices)==1
 assert ast.unparse(choices[0].func)=='load_equipped_items if equipped_only else load_items';choices[0].func=ast.Name(id='load_items',ctx=ast.Load())
 assert ast.dump(before)==ast.dump(after),'Full inventory validation/default loading must stay exact'
 before=tree(A/'runtime-parent/els_server/storage/read_scope.py');after=tree(A/'source/els_server/storage/read_scope.py')
 projection=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='inventory_projection')
 assert projection.args.kwonlyargs[0].arg=='projection'and projection.args.kw_defaults[0].value=='inventory'
 projection.args.kwonlyargs=[];projection.args.kw_defaults=[]
 tuples=[n for n in ast.walk(projection)if isinstance(n,ast.Tuple)and n.elts and isinstance(n.elts[0],ast.Name)and n.elts[0].id=='projection'];assert len(tuples)==1
 tuples[0].elts[0]=ast.Constant('inventory')
 assert ast.dump(before)==ast.dump(after),'File, committed-generation, ownership and receipt guards must stay exact'
 before=tree(A/'runtime-parent/els_server/domain/local_session.py');after=tree(A/'source/els_server/domain/local_session.py')
 original=next(n for n in cls(before,'LocalAccount').body if isinstance(n,ast.FunctionDef)and n.name=='get_inventory_snapshot')
 updated=next(n for n in cls(after,'LocalAccount').body if isinstance(n,ast.FunctionDef)and n.name=='get_inventory_snapshot')
 assert ast.dump(ast.Module(body=original.body[:-1],type_ignores=[]))==ast.dump(ast.Module(body=updated.body[:-2],type_ignores=[])),'Inventory enable/repair must remain before both projections'
 updated.args=original.args;updated.body=original.body
 assert ast.dump(before)==ast.dump(after),'Local session behavior outside the opt-in inventory projection must stay exact'
 for name,count in [('position_writer.py',3),('death_writer.py',1),('clock_writer.py',1)]:
  before=tree(A/'runtime-parent/els_server/storage'/name);after=tree(A/'source/els_server/storage'/name)
  class WriterBindings(ast.NodeTransformer):
   assignments=0;guards=0
   def visit_Assign(self,node):
    if len(node.targets)==1 and isinstance(node.targets[0],ast.Name)and node.targets[0].id=='path'and ast.unparse(node.value)=='Path(path)':
     self.assignments+=1;return None
    return self.generic_visit(node)
   def visit_If(self,node):
    if ast.unparse(node.test)=='path != self.path and path.resolve() != self.path.resolve()':
     self.guards+=1;node.test=ast.parse('Path(path).resolve()!=self.path.resolve()',mode='eval').body
    return self.generic_visit(node)
  normalized=WriterBindings();after=normalized.visit(after)
  assert normalized.assignments==normalized.guards==count
  assert ast.dump(before)==ast.dump(after),name+' changed outside same-path submit guards; fresh files, transactions and advance order must stay exact'
 selected=set(sys.argv[1:]);assert not selected or selected<=set(b['test_files'])
 for name,expected in b['test_files'].items():
  p=A/'tests'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
  if not selected or name in selected:subprocess.run([sys.executable,'-B',str(p)],check=True)
 print(json.dumps(dict(ok=True,source_files=17,SQL_durability_changed=False,client_binary_changed=False,authority_receipt_contract_preserved=True,behavioral_tests=sorted(selected or b['test_files']))))
if __name__=='__main__':main()
