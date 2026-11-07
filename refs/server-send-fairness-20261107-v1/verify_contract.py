"""Bind archived bytes and run behavioral state/order/quota checks."""
import ast,hashlib,json,subprocess,sys,tomllib
from pathlib import Path
A=Path(__file__).resolve().parent;ROOT=A.parents[1]
def tree(path):return ast.parse(path.read_bytes())
def cls(t,name):return next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name==name)
def main():
 b=json.loads((A/'source-bindings.json').read_bytes());assert len(b['files'])==22
 for rows in(b['files'],b['runtime_parent_files']):
  for row in rows.values():
   p=ROOT/row['source'];assert p.resolve().is_relative_to(A)and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];tree(p)
 assert set(b['runtime_templates'])=={'config/friends-server.toml','config/server-settings.json'}
 for name,row in b['runtime_templates'].items():
  source=ROOT/row['source'];parent=ROOT/row['parent_source']
  assert source.resolve().is_relative_to(A)and parent.resolve().is_relative_to(A)
  assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']and hashlib.sha256(parent.read_bytes()).hexdigest()==row['parent_sha256']
  if name.endswith('.toml'):before=tomllib.loads(parent.read_text('utf8'))['server'];after=tomllib.loads(source.read_text('utf8'))['server']
  else:before=json.loads(parent.read_bytes());after=json.loads(source.read_bytes())
  assert after.pop('egress_mbps')==b['egress_mbps']and before==after,'Only the measured frame budget may change in public templates'
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
 for name,methods in [('application.py',{'FriendsSession':{'__init__'},'Application':{'_dispatch','_worker_call'}}),('dungeon_workers.py',{'DungeonWorkers':{'publish'}}),('realtime.py',{'RealtimeState':{'__init__','publish'}}),('periodic_scheduler.py',{'PeriodicScheduler':{'_notify'}}),('domain/friends_world.py',{'Mailbox':{'append'}})]:
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
   friends=cls(after,'FriendsSession')
   periodic=next(n for n in friends.body if isinstance(n,ast.FunctionDef)and n.name=='periodic_notifications')
   deadline=[n for n in periodic.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='deadline'for t in n.targets)]
   assert len(deadline)==1 and ast.unparse(deadline[0].value)=='time.monotonic() + 0.002'
   deadline[0].value=ast.parse('time.monotonic()+(.008 if town else .002)',mode='eval').body
   mailbox=next(n for n in friends.body if isinstance(n,ast.FunctionDef)and n.name=='_mailbox_messages')
   assert ast.unparse(mailbox.body[0])=='self._peer_drain_open = False';mailbox.body.pop(0)
   request=next(n for n in friends.body if isinstance(n,ast.FunctionDef)and n.name=='_dungeon_request')
   expected=ast.parse('''from els_server.dungeon_workers import KINDS
if event.kind in KINDS and self.application.world.dungeons.room(self)is None:return None''').body
   assert [ast.dump(n)for n in request.body[:2]]==[ast.dump(n)for n in expected];request.body=request.body[2:]
   preparation=next(n for n in cls(after,'Application').body if isinstance(n,ast.AsyncFunctionDef)and n.name=='_prepare_workers')
   modules=next(n for n in preparation.body if isinstance(n,ast.FunctionDef)and n.name=='prepare_modules')
   warm=ast.parse('''from els_server.domain import achievement_flow
from els_server.domain.achievement_catalog import catalog as achievement_catalog,rewards as achievement_rewards
from els_server.storage import achievement_history,achievement_profiles,erp_support_quest_scope
achievement_catalog();achievement_rewards()''').body
   assert [ast.dump(n)for n in modules.body[-len(warm):]]==[ast.dump(n)for n in warm];modules.body=modules.body[:-len(warm)]
   reads=[n for n in ast.walk(preparation)if isinstance(n,ast.Constant)and n.value=='SELECT id,name,enabled FROM accounts ORDER BY id'];assert len(reads)==1;reads[0].value='SELECT 1 FROM accounts LIMIT 0'
   after.body=[n for n in after.body if not(isinstance(n,ast.ImportFrom)and n.module=='contextvars')and not(isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='_town_move_wakes'for v in n.targets))]
  if name=='domain/friends_world.py':
   calls=[n for n in ast.walk(after)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='get_inventory_snapshot'and n.keywords]
   assert len(calls)==3
   for call in calls:
    assert len(call.keywords)==1 and call.keywords[0].arg=='equipped_only'and call.keywords[0].value.value is True
    call.keywords=[]
  if name=='realtime.py':
   row=next(n for n in cls(after,'RealtimeState').body if isinstance(n,ast.FunctionDef)and n.name=='transport_row').body[-1]
   extra=ast.parse("(s.shop_session_id,s.account.account_id,s.identity['id'],s in app.world.party_of)",mode='eval').body.elts
   assert isinstance(row,ast.Return)and isinstance(row.value,ast.Tuple)and [ast.dump(n)for n in row.value.elts[-4:]]==[ast.dump(n)for n in extra];row.value.elts=row.value.elts[:-4]
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
 before=tree(A/'runtime-parent/els_server/observability.py');after=tree(A/'source/els_server/observability.py')
 imports=[n for n in after.body if isinstance(n,ast.Import)and len(n.names)==1 and n.names[0].name=='time'];assert len(imports)==1;after.body.remove(imports[0])
 worker=next(n for n in cls(after,'EventLog').body if isinstance(n,ast.FunctionDef)and n.name=='_run')
 loop=worker.body[0];assert isinstance(loop,ast.While)
 window=loop.body[1];assert isinstance(window,ast.If)and ast.unparse(window.test)=='batch[0] is not None and batch[0][0] in self.LOW_VALUE'
 assert len(window.body)==1 and ast.unparse(window.body[0])=='time.sleep(0.01)';loop.body.remove(window)
 assert ast.dump(before)==ast.dump(after),'Only background diagnostic batching may change; freezing, bounds, critical fallback, ordering and close must stay exact'
 before=tree(A/'runtime-parent/els_server/domain/session_auxiliary.py');after=tree(A/'source/els_server/domain/session_auxiliary.py')
 helpers=[n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='town_peer_reply'];assert len(helpers)==1
 assert len(helpers[0].body)==1 and ast.dump(helpers[0].body[0].value)==ast.dump(ast.parse('all(e.event_id==0x201 and e.kind in(0x22a,0x22e,0x18e)for e in replies)',mode='eval').body)
 after.body.remove(helpers[0])
 for name,expression in [('maintenance_request',"session.phase=='dungeon_active'and session.dungeon_substage_synced and bool(session.reward_run_id)"),('maintenance_reply','all(e.event_id==0x201 and e.kind==0x9f for e in replies)')]:
  function=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name==name)
  extensions=[n for n in function.body if isinstance(n,ast.If)and ast.unparse(n.test)=='event.kind == 158'];assert len(extensions)==1
  extension=extensions[0];assert len(extension.body)==1 and isinstance(extension.body[0],ast.Return)and ast.dump(extension.body[0].value)==ast.dump(ast.parse(expression,mode='eval').body)
  function.body.remove(extension)
  if name=='maintenance_reply':
   town=next(n for n in function.body if isinstance(n,ast.If)and ast.unparse(n.test)=='event.kind == 555')
   assert len(town.body)==1 and ast.unparse(town.body[0])=='return town_peer_reply(replies)'
   town.body=ast.parse('return all(e.event_id==0x201 and e.kind==0x22e for e in replies)').body
 activity=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='activity_due')
 assert len(activity.args.kwonlyargs)==1 and activity.args.kwonlyargs[0].arg=='after'and activity.args.kw_defaults[0].value is False
 activity.args.kwonlyargs=[];activity.args.kw_defaults=[]
 original_activity=next(n for n in before.body if isinstance(n,ast.FunctionDef)and n.name=='activity_due')
 assignment=next(n for n in ast.walk(activity)if isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='unchanged'for v in n.targets))
 original_assignment=next(n for n in ast.walk(original_activity)if isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='unchanged'for v in n.targets))
 assert ast.dump(assignment.value)==ast.dump(ast.parse("args[0].kind==0xad or(run is not None and run.next is not None and run.next['kind']==0)or(after and args[0].kind==0xbb and run is not None)",mode='eval').body)
 assignment.value=original_assignment.value
 assert ast.dump(before)==ast.dump(after),'Only display9E, town peer replies and the completed capped-BB cursor may skip duplicate activity work; existing actor, scene, level and failure guards remain'
 before=tree(A/'runtime-parent/els_server/storage/achievement_profiles.py');after=tree(A/'source/els_server/storage/achievement_profiles.py')
 pending=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='pending_updates')
 reconcile=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='reconcile')
 original=next(n for n in before.body if isinstance(n,ast.FunctionDef)and n.name=='reconcile')
 assert ast.dump(pending.args)==ast.dump(original.args)==ast.dump(reconcile.args)
 assert ast.unparse(pending.body[-1])=='return updates'
 assert ast.unparse(reconcile.body[0])=='updates = pending_updates(db, account, owner, now, condition_types=condition_types)'
 reconcile.body=pending.body[:-1]+reconcile.body[1:];after.body.remove(pending)
 assert ast.dump(before)==ast.dump(after),'Every attained-level, collection and historical-condition decision and durable record remains the original implementation'
 before=tree(A/'runtime-parent/els_server/domain/achievement_flow.py');after=tree(A/'source/els_server/domain/achievement_flow.py')
 imported=next(n for n in after.body if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.achievement_profiles')
 assert [(n.name,n.asname)for n in imported.names]==[('reconcile','reconcile_profiles'),('pending_updates',None)];imported.names.pop()
 sync=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='synchronize')
 preflight=next(n for n in sync.body if isinstance(n,ast.If)and ast.unparse(n.test)=='not cold and (not arrival)')
 expected_preflight=ast.parse('''if not cold and not arrival:
    from els_server.storage.read_scope import snapshot_connection
    with snapshot_connection(s.account.store.path)as db:
        db.execute('BEGIN');guard(db)
        pending=pending_updates(db,s.account.account_id,s.account.uid,int(time.time()),condition_types=sources)
        guard(db)
    if not pending:return response''').body[0]
 assert ast.dump(preflight)==ast.dump(expected_preflight);sync.body.remove(preflight)
 imports=[n for n in sync.body if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.sqlite_timing'];assert len(imports)==1 and[(a.name,a.asname)for a in imports[0].names]==[('write_transaction',None)];sync.body.remove(imports[0])
 writer=next(n for n in sync.body if isinstance(n,ast.With));assert len(writer.items)==1 and len(writer.body)==2
 assert ast.unparse(writer.body[0])=="db.execute('PRAGMA foreign_keys=ON')"
 transaction=writer.body[1];assert isinstance(transaction,ast.With)and len(transaction.items)==1 and ast.unparse(transaction.items[0].context_expr)=='write_transaction(db)'and transaction.items[0].optional_vars is None
 writer.items.append(ast.withitem(context_expr=ast.Name(id='db',ctx=ast.Load())))
 writer.body=[writer.body[0],ast.parse("db.execute('BEGIN IMMEDIATE')").body[0],*transaction.body]
 assert ast.dump(before)==ast.dump(after),'Only the fresh no-change read and cooperative writer admission may differ; cold login, source kinds, owned guards, economic recording, encoding and appearance synchronization stay exact'
 bindings_only=sys.argv[1:]==['--bindings-only']
 selected=set()if bindings_only else set(sys.argv[1:]);assert not selected or selected<=set(b['test_files'])
 for name,expected in b['test_files'].items():
  p=A/'tests'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
  if not bindings_only and(not selected or name in selected):subprocess.run([sys.executable,'-B',str(p)],check=True)
 print(json.dumps(dict(ok=True,source_files=22,SQL_durability_changed=False,client_binary_changed=False,authority_receipt_contract_preserved=True,behavioral_tests=[]if bindings_only else sorted(selected or b['test_files']))))
if __name__=='__main__':main()
