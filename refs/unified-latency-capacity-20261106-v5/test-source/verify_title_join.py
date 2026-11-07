"""Real accepted death atomicity plus original title ledger oracle."""
import runtime_fixture as h
import ast,asyncio,contextlib,json,sqlite3,uuid,hashlib
from unittest.mock import patch
from profile_town import seed
from els_server.domain import title_flow,legacy_pve_exp,title_kill_rules
from els_server.storage import title_kills
from els_server.protocol.protocol_codec import Event
probe=h.load('title_join_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')

def original_record():
 tree=ast.parse((h.BASE/'els_server/storage/title_kills.py').read_bytes())
 node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='record')
 scope=dict(vars(title_kills));exec(compile(ast.Module(body=[node],type_ignores=[]),'original-title-kill-record','exec'),scope)
 return scope['record']

def tables(path):
 with contextlib.closing(sqlite3.connect(path))as db:
  names=[r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'title_%' ORDER BY name")]
  return{n:sorted(db.execute('SELECT * FROM '+n).fetchall())for n in names}

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False)
 try:
  uid=seed(c,c.alice,'OwnTitle',False);p=await c.peer(c.alice);await p.roster();await c.server.periodics.close()
  await probe.solo_load(p,uid);s=c.app.playing[c.alice['id']]
  def graph_digest():return hashlib.sha256(json.dumps(s.dungeon_run.catalog._data,sort_keys=True).encode()).hexdigest()
  source_before=graph_digest()
  npc=next(n for n in s.dungeon_run.current['npcs']if legacy_pve_exp.eligible(n))
  event=Event(0x202,kind=0xad,payload=probe.accepted_combat(npc,uid),performers=(0,))
  writes=[];original=title_kills.record_in_transaction
  def joined(*a,**kw):writes.append(True);return original(*a,**kw)
  def fail(*a,**kw):raise ValueError('Owned title-join preencoding rollback')
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:before=tuple(db.iterdump())
  with patch.object(title_kills,'record_in_transaction',joined),patch('els_server.protocol.protocol_codec.encode_event',fail):
   try:await c.app.call(s.handle,event)
   except ValueError as e:assert str(e)=='Owned title-join preencoding rollback'
   else:raise AssertionError('Injected encoder failure did not propagate')
  assert writes and npc['key']not in s.dungeon_run.defeated
  assert npc['key']not in getattr(s,'_title_kill_seen',set())
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:assert tuple(db.iterdump())==before
  with patch.object(title_kills,'record_in_transaction',joined):
   await p.send(0xad,event.payload);assert(await p.until(0xae)).payload==bytes(4)
   await p.send(0x48d);await p.until(0x48f)
  assert npc['key']in s.dungeon_run.defeated and npc['key']in s._title_kill_seen
  with patch.object(title_kills,'record',side_effect=AssertionError('Repeated title writer')):
   await c.app.call(title_flow.observe_kills,s)
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:committed=tuple(db.iterdump())
  await p.send(0xad,event.payload);assert(await p.until(0xae)).payload==bytes(4)
  await p.send(0x48d);await p.until(0x48f)
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db:assert tuple(db.iterdump())==committed
  # A source-pinned matching objective exercises real counters and receipts,
  # independently of the benchmark map's available static monsters.
  rule=next(r for r in title_kill_rules.rules()if not r.prerequisites and any(o.kind==2 for o in r.objectives))
  objective=next(o for o in rule.objectives if o.kind==2)
  context=dict(run=str(uuid.uuid4()),dungeon=objective.maps[0]if objective.maps else 34710,
   stage=0,part=0,visits=1,key=1,npc=objective.npcs[0],graph='a'*64)
  outputs={}
  for name in('original','candidate'):
   path=c.root/(name+'-title.sqlite3')
   with contextlib.closing(sqlite3.connect(c.config.state_file))as source,contextlib.closing(sqlite3.connect(path))as db:source.backup(db)
   if name=='original':
    answer=original_record()(path,uid,context,b'accepted-proof',now=1800000000)
    replay=original_record()(path,uid,context,b'accepted-proof',now=1800000000)
   else:
    with contextlib.closing(sqlite3.connect(path))as db:
     try:title_kills.record_in_transaction(db,path,uid,context,b'accepted-proof')
     except ValueError:pass
     else:raise AssertionError('Unowned title transaction accepted')
     db.execute('BEGIN IMMEDIATE')
     try:title_kills.record_in_transaction(db,c.config.state_file,uid,context,b'accepted-proof')
     except ValueError:pass
     else:raise AssertionError('Foreign title database accepted')
     db.rollback();db.execute('BEGIN IMMEDIATE')
     answer=original(db,path,uid,context,b'accepted-proof',now=1800000000)
     replay=original(db,path,uid,context,b'accepted-proof',now=1800000000)
     assert db.in_transaction;db.commit()
   assert not answer['replayed']and replay['replayed'];outputs[name]=(answer,replay,tables(path))
  assert outputs['original']==outputs['candidate']
  assert graph_digest()==source_before,'Read-only kill source changed the pinned graph catalog'
  out.update(passed=True,shared_graph_catalog_unchanged_by_actual_native_death_and_failure=True,actual_native_death_marks_title_after_commit=True,
   actual_preencoding_failure_rolls_back_sql_and_actor=True,replay_has_no_increment=True,
   subsequent_observer_opens_no_writer=True,matching_original_title_counters_and_receipts_equal=True,
   caller_transaction_and_database_guards=True)
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  (h.H/'title-join-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out));assert out['passed']and not out['errors']
asyncio.run(main())
