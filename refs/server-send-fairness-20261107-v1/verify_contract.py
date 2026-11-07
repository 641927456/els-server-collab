"""Bind archived bytes and run behavioral state/order/quota checks."""
import ast,copy,hashlib,json,subprocess,sys,tomllib
from pathlib import Path
A=Path(__file__).resolve().parent;ROOT=A.parents[1]
def tree(path):return ast.parse(path.read_bytes())
def cls(t,name):return next(n for n in t.body if isinstance(n,ast.ClassDef)and n.name==name)
def main():
 b=json.loads((A/'source-bindings.json').read_bytes());assert len(b['files'])==28
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
 before=tree(A/'runtime-parent/els_server/__main__.py');after=tree(A/'source/els_server/__main__.py')
 for t in(before,after):t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name=='_normal_scheduling')]
 assert ast.dump(before)==ast.dump(after),'Only the existing startup scheduling normalization changes'
 # The current online parent's party, quest, guide, shutdown and GM actor
 # ownership fixes are retained. Only these scheduling entry points differ.
 dispatch=next(n for n in cls(tree(A/'source/els_server/application.py'),'Application').body if isinstance(n,ast.AsyncFunctionDef)and n.name=='_dispatch')
 roster_admission=next(n for n in ast.walk(dispatch)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='preparation'for t in n.targets))
 assert ast.dump(roster_admission)==ast.dump(ast.parse('preparation=own_preparation and(transition or args[0].kind in(0x28,0x227,0x485))').body[0]),'Heavy native roster queries must use the existing preparation admission'
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
   original_call=next(n for n in cls(before,'Application').body if isinstance(n,ast.AsyncFunctionDef)and n.name=='call')
   updated_call=next(n for n in cls(after,'Application').body if isinstance(n,ast.AsyncFunctionDef)and n.name=='call')
   assert [ast.dump(n)for n in updated_call.body[:2]]==[ast.dump(n)for n in original_call.body[:2]]
   expected_window=ast.parse('''peer_window=self.dungeon_workers.ordinary_town_move(function,args)
if peer_window:session._peer_drain_open=True''').body
   assert [ast.dump(n)for n in updated_call.body[2:4]]==[ast.dump(n)for n in expected_window]
   scope=updated_call.body[4];assert len(updated_call.body)==5 and isinstance(scope,ast.Try)and not scope.handlers and not scope.orelse
   assert [ast.dump(n)for n in scope.body]==[ast.dump(n)for n in original_call.body[2:]]
   assert [ast.dump(n)for n in scope.finalbody]==[ast.dump(n)for n in ast.parse('if peer_window:session._peer_drain_open=False').body]
   updated_call.body=original_call.body
   handle=next(n for n in cls(after,'FriendsSession').body if isinstance(n,ast.FunctionDef)and n.name=='handle')
   preparation=next(n for n in handle.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='own_town_input'for t in n.targets))
   assert ast.dump(preparation)==ast.dump(ast.parse('own_town_input=entering_town and self.application.dungeon_workers.town_preparation(self.handle,(event,))').body[0]);handle.body.remove(preparation)
   empty=next(n for n in handle.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='town_member'for t in n.targets));assert empty.value.value is None;handle.body.remove(empty)
   prepared=next(n for n in handle.body if isinstance(n,ast.If)and ast.unparse(n.test)=="own_town_input and self.phase == 'town_ready'")
   expected=ast.parse("if own_town_input and self.phase=='town_ready':\n town_member=(self.account.character(),self.account.get_location(),self.account.get_inventory_snapshot(equipped_only=True)['items'])").body[0]
   assert ast.dump(prepared)==ast.dump(expected);handle.body.remove(prepared)
   calls=[n for n in ast.walk(handle)if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)and n.func.attr=='_after_local'and n.keywords]
   assert len(calls)==1 and ast.unparse(calls[0].keywords[0].value)=='town_member'and calls[0].keywords[0].arg=='town_member';calls[0].keywords=[]
   after_local=next(n for n in cls(after,'FriendsSession').body if isinstance(n,ast.FunctionDef)and n.name=='_after_local')
   assert len(after_local.args.kwonlyargs)==1 and after_local.args.kwonlyargs[0].arg=='town_member'and after_local.args.kw_defaults[0].value is None;after_local.args.kwonlyargs=[];after_local.args.kw_defaults=[]
   sync=[n for n in ast.walk(after_local)if isinstance(n,ast.Call)and ast.unparse(n.func)=='self.application.world.synchronize'];assert len(sync)==1 and len(sync[0].keywords)==1 and sync[0].keywords[0].arg=='own'and ast.unparse(sync[0].keywords[0].value)=='town_member';sync[0].keywords=[]
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
  if name=='dungeon_workers.py':
   prep=next(n for n in cls(after,'DungeonWorkers').body if isinstance(n,ast.FunctionDef)and n.name=='town_preparation')
   guard=next(n for n in prep.body if isinstance(n,ast.If));alternatives=guard.test.operand.values[-1].values
   expected=ast.parse("session.application.playing.get(session.identity['id'])is None and(args[0].kind,session.phase)in((0x1e,'game_connected'),(0x35,'game_authenticated'),(0x1ef,'port_ready'),(0x39,'session_ready'),(0x485,'terms_ready'),(0x485,'session_ready'),(0x485,'channels_ready'),(0x490,'characters_ready'))",mode='eval').body
   assert len(alternatives)==4 and ast.dump(alternatives[-1])==ast.dump(expected),'Preselection isolation must retain exact phases and exclude an active same-account actor'
   alternatives.pop()
   constructor=next(n for n in cls(after,'DungeonWorkers').body if isinstance(n,ast.FunctionDef)and n.name=='__init__')
   for field in('town_workers','death_workers'):
    values=[n for n in constructor.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Attribute)and ast.unparse(t)=='self.'+field for t in n.targets)]
    assert len(values)==1 and values[0].value.value==8;values[0].value=ast.Constant(16)
  if name=='domain/friends_world.py':
   synchronize=next(n for n in cls(after,'FriendsWorld').body if isinstance(n,ast.FunctionDef)and n.name=='synchronize')
   assert len(synchronize.args.kwonlyargs)==1 and synchronize.args.kwonlyargs[0].arg=='own'and synchronize.args.kw_defaults[0].value is None;synchronize.args.kwonlyargs=[];synchronize.args.kw_defaults=[]
   fallback=next(n for n in synchronize.body if isinstance(n,ast.If)and ast.unparse(n.test)=='own is None');assert len(fallback.body)==1 and not fallback.orelse
   synchronize.body[synchronize.body.index(fallback)]=fallback.body[0]
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
 profile_tree=tree(A/'source/els_server/domain/elixir_flow.py')
 profile=next(n for n in profile_tree.body if isinstance(n,ast.FunctionDef)and n.name=='profiles')
 lu=next(n for n in profile.body if isinstance(n,ast.If))
 statements=[ast.unparse(n)for n in lu.body]
 for expected in("from els_server.storage.luciel_state import state, active_state","character['luciel_style'] = state(db, s.account.uid)['style']","character['luciel_active_unit'] = active_state(db, s.account.uid)['active_unit']"):
  assert expected in statements,'Authoritative saved LuCiel state must remain fresh'
 for name,names in [('domain/elixir_flow.py',{'profiles'})]:
  before=tree(A/'runtime-parent/els_server'/name);after=tree(A/'source/els_server'/name)
  for t in(before,after):t.body=[n for n in t.body if not(isinstance(n,ast.FunctionDef)and n.name in names)]
  assert ast.dump(before)==ast.dump(after),name+' changed outside native profile construction'
 before=tree(A/'runtime-parent/els_server/storage/inventory_state.py');after=tree(A/'source/els_server/storage/inventory_state.py')
 public=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='load_items')
 equipped=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='load_equipped_items')
 assert len(public.body)==1 and ast.unparse(public.body[0])=='return _load_items(db, owner, item_uid=item_uid)'
 assert len(equipped.body)==1 and ast.unparse(equipped.body[0])=='return _load_items(db, owner, bag_group=9)'
 after.body.remove(public);after.body.remove(equipped)
 load=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='_load_items')
 load.name='load_items'
 assert load.args.kwonlyargs[-1].arg=='bag_group'and load.args.kw_defaults[-1].value is None
 load.args.kwonlyargs.pop();load.args.kw_defaults.pop()
 filters=[n for n in load.body if isinstance(n,ast.If)and ast.unparse(n.test)=='bag_group is not None'];assert len(filters)==1
 assert ast.dump(filters[0])==ast.dump(ast.parse("if bag_group is not None:\n query+=' AND bag_group=?';parameters+=(bag_group,)").body[0]);load.body.remove(filters[0])
 snapshot=next(n for n in cls(after,'InventoryState').body if isinstance(n,ast.FunctionDef)and n.name=='snapshot')
 assert snapshot.args.kwonlyargs[0].arg=='equipped_only'and snapshot.args.kw_defaults[0].value is False
 snapshot.args.kwonlyargs=[];snapshot.args.kw_defaults=[]
 choices=[n for n in ast.walk(snapshot)if isinstance(n,ast.Call)and isinstance(n.func,ast.IfExp)];assert len(choices)==1
 assert ast.unparse(choices[0].func)=='load_equipped_items if equipped_only else load_items';choices[0].func=ast.Name(id='load_items',ctx=ast.Load())
 assert ast.dump(before)==ast.dump(after),'Full inventory validation/default loading and accepted row-cache removal must stay exact'
 before=tree(A/'runtime-parent/els_server/storage/read_scope.py');after=tree(A/'source/els_server/storage/read_scope.py')
 projection=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='inventory_projection')
 assert projection.args.kwonlyargs[0].arg=='projection'and projection.args.kw_defaults[0].value=='inventory'
 projection.args.kwonlyargs=[];projection.args.kw_defaults=[]
 tuples=[n for n in ast.walk(projection)if isinstance(n,ast.Tuple)and n.elts and isinstance(n.elts[0],ast.Name)and n.elts[0].id=='projection'];assert len(tuples)==1
 tuples[0].elts[0]=ast.Constant('inventory')
 original_test="canonical_path(store.path) != canonical_path(inventory.path)"
 optimized_test="store.path != inventory.path and canonical_path(store.path) != canonical_path(inventory.path)"
 found=[n for n in ast.walk(projection)if isinstance(n,ast.BoolOp)and ast.unparse(n)==optimized_test];assert len(found)==1
 parent=next(n for n in ast.walk(projection)if isinstance(n,ast.BoolOp)and found[0]in n.values)
 parent.values[parent.values.index(found[0])]=ast.parse(original_test,mode='eval').body
 extra_names={'_ITEM_SCALARS','_flat_item','item_validation_projection'}
 extras=[n for n in after.body if isinstance(n,ast.FunctionDef)and n.name in extra_names or isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id in extra_names for t in n.targets)]
 assert len(extras)==3
 helper=next(n for n in extras if isinstance(n,ast.FunctionDef)and n.name=='item_validation_projection')
 text=ast.unparse(helper)
 assert 'pickle.loads'not in text and 'scope.thread != threading.get_ident()'in text and 'not _flat_item(item)'in text and 'return saved.copy()'in text
 for n in extras:after.body.remove(n)
 imports=[n for n in after.body if isinstance(n,ast.Import)and len(n.names)==1 and n.names[0].name=='pickle'];assert len(imports)==1;after.body.remove(imports[0])
 for method in cls(after,'_ReadScope').body:
  if not isinstance(method,ast.FunctionDef):continue
  if method.name=='__init__':
   selected=[n for n in method.body if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='self.item_validations'];assert len(selected)==1 and ast.unparse(selected[0].value)=='{}';method.body.remove(selected[0])
  elif method.name=='close':
   group=next(n for n in method.body if isinstance(n,ast.Try));selected=[n for n in group.finalbody if ast.unparse(n)=='self.item_validations.clear()'];assert len(selected)==1;group.finalbody.remove(selected[0])
 assert ast.dump(before)==ast.dump(after),'Fresh files, committed generation, owner and receipt guards remain exact; only flat codec reuse and identical-path equality differ'
 assert not any(isinstance(n,ast.FunctionDef)and n.name in('validated_item_projection','_tracked_snapshot')for n in after.body),'Accepted snapshot-tracker and row-cache removals must remain'
 for name in('friend_flow','mentor_flow'):
  before=tree(A/('runtime-parent/els_server/domain/'+name+'.py'));after=tree(A/('source/els_server/domain/'+name+'.py'))
  additions=[n for n in after.body if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.read_scope'and[(v.name,v.asname)for v in n.names]==[('snapshot_connection',None)]]
  assert len(additions)==1;after.body.remove(additions[0])
  def sync_node(t):
   body=t.body if name=='friend_flow'else cls(t,'Mentors').body
   return next(n for n in body if isinstance(n,ast.FunctionDef)and n.name=='synchronize')
  original=[n for n in ast.walk(sync_node(before))if isinstance(n,ast.withitem)and isinstance(n.context_expr,ast.Call)and isinstance(n.context_expr.func,ast.Name)and n.context_expr.func.id=='closing']
  replacement=[n for n in ast.walk(sync_node(after))if isinstance(n,ast.withitem)and isinstance(n.context_expr,ast.Call)and isinstance(n.context_expr.func,ast.Name)and n.context_expr.func.id=='snapshot_connection']
  assert len(original)==len(replacement)==1
  expression='snapshot_connection(s.account.store.path'+(',timeout=5'if name=='mentor_flow'else'')+')'
  assert ast.dump(replacement[0].context_expr)==ast.dump(ast.parse(expression,mode='eval').body)
  replacement[0].context_expr=copy.deepcopy(original[0].context_expr)
  assert ast.dump(before)==ast.dump(after),'Social SQL, BEGIN, timeout, authority, mailbox and encoding logic must stay exact'
 before=tree(A/'runtime-parent/els_server/domain/inventory_items.py');after=tree(A/'source/els_server/domain/inventory_items.py')
 checked=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='_checked_items')
 assert ast.unparse(checked.body[1])=='from els_server.storage.read_scope import item_validation_projection'
 assert ast.unparse(checked.body[2])=='checked = [item_validation_projection(i, validate_item) for i in items]'
 checked.body[1:3]=ast.parse('checked=[validate_item(i)for i in items]').body
 assert ast.dump(before)==ast.dump(after),'All actual validation rules, list bounds, duplicate checks and native wire encoders remain exact'
 before=tree(A/'runtime-parent/els_server/domain/local_session.py');after=tree(A/'source/els_server/domain/local_session.py')
 original=next(n for n in cls(before,'LocalAccount').body if isinstance(n,ast.FunctionDef)and n.name=='get_inventory_snapshot')
 updated=next(n for n in cls(after,'LocalAccount').body if isinstance(n,ast.FunctionDef)and n.name=='get_inventory_snapshot')
 assert ast.dump(ast.Module(body=original.body[:-1],type_ignores=[]))==ast.dump(ast.Module(body=updated.body[:-2],type_ignores=[])),'Inventory enable/repair must remain before both projections'
 updated.args=original.args;updated.body=original.body
 original_capture=next(n for n in cls(before,'LocalSession').body if isinstance(n,ast.FunctionDef)and n.name=='_capture_luciel_dungeon_hp')
 updated_capture=next(n for n in cls(after,'LocalSession').body if isinstance(n,ast.FunctionDef)and n.name=='_capture_luciel_dungeon_hp')
 assert ast.dump(original_capture)==ast.dump(updated_capture),'Retain the accepted complete four-span LuCiel source'
 updated_capture.body=original_capture.body
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
 before=tree(A/'runtime-parent/els_server/storage/achievement_collections.py');after=tree(A/'source/els_server/storage/achievement_collections.py')
 class OriginalCollectionReader(ast.NodeTransformer):
  imports=0;calls=0
  def visit_ImportFrom(self,node):
   if node.module=='els_server.storage.inventory_state':
    for value in node.names:
     if value.name=='load_equipped_items':assert value.asname is None;value.name='load_items';self.imports+=1
   return node
  def visit_Call(self,node):
   if isinstance(node.func,ast.Name)and node.func.id=='load_equipped_items':
    assert ast.unparse(node)=='load_equipped_items(db, character)';node.func.id='load_items';self.calls+=1
   return self.generic_visit(node)
 restore=OriginalCollectionReader();after=restore.visit(after)
 assert restore.imports==restore.calls==1 and ast.dump(before)==ast.dump(after),'Only equipped-set SQL selection changes; owner/account SQL, each-role maximum, original expiry and all other collection sources stay exact'
 before=tree(A/'runtime-parent/els_server/storage/title_drop_rewards.py');after=tree(A/'source/els_server/storage/title_drop_rewards.py')
 bonus=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='bonus')
 own=next(n for n in bonus.body if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='owned')
 assert ast.unparse(own.value)=='titles.owned(db, character, when)';bonus.body.remove(own)
 active=next(n for n in bonus.body if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='active')
 assert ast.unparse(active.value)=='titles._equipped(db, character, owned)'
 active.value=ast.parse('titles.equipped(db, owner, when)',mode='eval').body
 expiry=next(n for n in bonus.body if isinstance(n,ast.Assign)and ast.unparse(n.targets[0])=='end')
 generator=expiry.value.args[0];assert isinstance(generator,ast.GeneratorExp)and len(generator.generators)==1 and ast.unparse(generator.generators[0].iter)=='owned'
 generator.generators[0].iter=ast.parse('titles.owned(db, character, when)',mode='eval').body
 assert ast.dump(before)==ast.dump(after),'Only repeated title reads in the existing writer may differ; all reward facts, eligibility, replay, validation and transaction guards remain exact'
 title_module=tree(A/'runtime-parent/els_server/storage/titles.py')
 equipped=next(n for n in title_module.body if isinstance(n,ast.FunctionDef)and n.name=='equipped')
 expected=ast.parse('now=int(time.time())if now is None else now\nc=character(db,uid)\nreturn _equipped(db,c,owned(db,c,now))').body
 assert ast.dump(ast.Module(body=equipped.body[1:],type_ignores=[]))==ast.dump(ast.Module(body=expected,type_ignores=[]))
 before=tree(A/'runtime-parent/els_server/storage/achievement_profiles.py');after=tree(A/'source/els_server/storage/achievement_profiles.py')
 pending=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='pending_updates')
 reconcile=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='reconcile')
 original=next(n for n in before.body if isinstance(n,ast.FunctionDef)and n.name=='reconcile')
 assert ast.dump(pending.args)==ast.dump(original.args)==ast.dump(reconcile.args)
 expected_plan=ast.parse("plan=dict(updates=updates)\nif duration is not None:plan['couple_due']=couple_due\nreturn plan").body
 assert ast.dump(ast.Module(body=pending.body[-3:],type_ignores=[]))==ast.dump(ast.Module(body=expected_plan,type_ignores=[]))
 assert ast.unparse(reconcile.body[0])=='plan = pending_updates(db, account, owner, now, condition_types=condition_types)'
 assert ast.unparse(reconcile.body[1])=="updates = plan['updates']"
 tail=reconcile.body[2:]
 assert ast.unparse(tail[-2])=="if 'couple_due' in plan:\n    result['couple_due'] = plan['couple_due']"
 tail[-2]=original.body[-2]
 reconcile.body=pending.body[:-3]+tail;after.body.remove(pending)
 assert ast.dump(before)==ast.dump(after),'Every source rule, result digest and couple deadline remains the original implementation'
 before=tree(A/'runtime-parent/els_server/domain/achievement_flow.py');after=tree(A/'source/els_server/domain/achievement_flow.py')
 imported=next(n for n in after.body if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.achievement_profiles')
 assert [(n.name,n.asname)for n in imported.names]==[('reconcile','reconcile_profiles'),('pending_updates',None)];imported.names.pop()
 sync=next(n for n in after.body if isinstance(n,ast.FunctionDef)and n.name=='synchronize')
 start=next(i for i,n in enumerate(sync.body)if isinstance(n,ast.If)and ast.unparse(n.test)=='10 not in sources')
 assert not sync.body[start].orelse
 preflight=sync.body[start].body
 expected=ast.parse("from els_server.storage.read_scope import snapshot_connection\noptions={}if cold or arrival else dict(condition_types=sources)\nwith snapshot_connection(s.account.store.path)as db:\n    db.execute('BEGIN');guard(db)\n    plan=pending_updates(db,s.account.account_id,s.account.uid,now,**options)\n    if not plan['updates']:\n        answer=response\n        if cold or arrival:\n            current=state.snapshot(db,s.account.account_id,s.account.uid)\n            message=wire.summary(points(current['completed']),current['watched'],False)\n            encode_event(message);answer=[*response,message]\n    guard(db)\nif not plan['updates']:\n    if 'couple_due'in plan:\n        s._achievement_couple_due=(s.account.account_id,s.account.uid,plan['couple_due'])if plan['couple_due']is not None else None\n    if spa is not None and 7 in sources:s._achievement_spa_source=None\n    return answer").body
 assert ast.dump(ast.Module(body=preflight,type_ignores=[]))==ast.dump(ast.Module(body=expected,type_ignores=[]))
 del sync.body[start]
 imports=[n for n in sync.body if isinstance(n,ast.ImportFrom)and n.module=='els_server.storage.sqlite_timing'];assert len(imports)==1 and[(v.name,v.asname)for v in imports[0].names]==[('write_transaction',None)];sync.body.remove(imports[0])
 writer=next(n for n in sync.body if isinstance(n,ast.With));assert len(writer.items)==1 and len(writer.body)==2
 assert ast.unparse(writer.body[0])=="db.execute('PRAGMA foreign_keys=ON')"
 transaction=writer.body[1];assert isinstance(transaction,ast.With)and len(transaction.items)==1 and ast.unparse(transaction.items[0].context_expr)=='write_transaction(db)'and transaction.items[0].optional_vars is None
 writer.items.append(ast.withitem(context_expr=ast.Name(id='db',ctx=ast.Load())))
 writer.body=[writer.body[0],ast.parse("db.execute('BEGIN IMMEDIATE')").body[0],*transaction.body]
 assert ast.dump(before)==ast.dump(after),'Only fresh no-change planning and cooperative admission differ; original scheduled observations, guards, transactions and replies remain exact'
 bindings_only=sys.argv[1:]==['--bindings-only']
 selected=set()if bindings_only else set(sys.argv[1:]);assert not selected or selected<=set(b['test_files'])
 for name,expected in b['test_files'].items():
  p=A/'tests'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
  if not bindings_only and(not selected or name in selected):subprocess.run([sys.executable,'-B',str(p)],check=True)
 print(json.dumps(dict(ok=True,source_files=len(b['files']),SQL_durability_changed=False,client_binary_changed=False,authority_receipt_contract_preserved=True,behavioral_tests=[]if bindings_only else sorted(selected or b['test_files']))))
if __name__=='__main__':main()
