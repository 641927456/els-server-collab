"""Pinned view results plus actual owned elixir source, expiry and rollback."""
import runtime_fixture as h
import asyncio,contextlib,copy,importlib,json,sqlite3,struct,time
from unittest.mock import patch
from profile_town import seed
from els_server.storage.read_scope import committed_reads
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import world_elixirs as elixirs
from els_server.domain import elixir_flow
from els_server.protocol.protocol_codec import Event

names=('domain.assembly_flow','domain.random_mission_flow','domain.black_market_flow','domain.boosting_2026_join_flow','domain.boosting_2026_quests','storage.mailbox_extras','storage.world_elixirs')
current={name:importlib.import_module('els_server.'+name)for name in names}
original={name:h.load('pinned_new_ro_'+name.replace('.','_'),h.BASE/'els_server'/(name.replace('.','/')+'.py'))for name in names}
def contents(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();checks=[]
 try:
  uid=seed(c,c.alice,'OwnPureRO');peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid);await c.server.periodics.close()
  s=c.app.playing[c.alice['id']];path=c.config.state_file;aid=s.account.account_id;fixed=int(time.time())
  extension=s.activity2026_awards.previous
  join=extension.participation;quests=extension.growth
  before=contents(path)
  with patch('time.time',return_value=fixed):
   for name,function,args in (
    ('domain.assembly_flow','notices',(s,)),
    ('domain.random_mission_flow','periodic',(s,)),
    ('domain.black_market_flow','periodic',(s,)),
    ('storage.mailbox_extras','status',(path,aid,uid)),
    ('storage.world_elixirs','snapshot',(path,uid,aid)),
   ):
    saved=dict(vars(s));s._mission_poll_after=0
    expected=getattr(original[name],function)(*args)
    s.__dict__.clear();s.__dict__.update(saved);s._mission_poll_after=0
    with committed_reads(connections=c.app.read_connections):actual=getattr(current[name],function)(*args)
    assert actual==expected,(name,function);checks.append(name+'.'+function)
   for name,klass,flow in(('domain.boosting_2026_join_flow','BoostingJoinFlow',join),('domain.boosting_2026_quests','BoostingQuestBinding',quests)):
    a,b=copy.copy(flow),copy.copy(flow)
    expected=getattr(getattr(original[name],klass),'finalize')(a,s,[Event(0x201,kind=0x48f)])
    with committed_reads(connections=c.app.read_connections):actual=getattr(getattr(current[name],klass),'finalize')(b,s,[Event(0x201,kind=0x48f)])
    assert actual==expected,(name,'finalize');checks.append(name+'.finalize')
  assert contents(path)==before,'A pure view wrote player SQL'
  # Use the existing owned-item consumer to create a real validated buff
  # receipt. No invented elixir row or missing source is accepted by the test.
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');grant_items(db,[dict(template=710206,metadata=2,quantity=2,group=4)],uid)
   item=next(i for i in load_items(db,uid)if i['template']==710206)
  payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
  result=elixirs.use(path,uid,aid,payload,'owned-readonly-elixir',elixir_flow.prepare(s),now=fixed)
  assert result['result']==0 and result['state']['rows']
  before=contents(path)
  with committed_reads(connections=c.app.read_connections):
   active=elixirs.snapshot(path,uid,aid,now=fixed)
   assert active==original['storage.world_elixirs'].snapshot(path,uid,aid,now=fixed)
   assert elixirs.expire(path,uid,aid,lambda *_:[],now=fixed)is None
  assert contents(path)==before and active['rows']
  # A real other writer cannot block the negative view. It still sees only
  # committed rows, and the pooled transaction always ends before writing.
  with contextlib.closing(sqlite3.connect(path,timeout=0))as blocker:
   blocker.execute('BEGIN IMMEDIATE')
   with committed_reads(connections=c.app.read_connections):assert elixirs.snapshot(path,uid,aid,now=fixed)==active
   blocker.rollback()
  def clone(name):
   other=c.root/(name+'.sqlite3')
   with contextlib.closing(sqlite3.connect(path))as src,contextlib.closing(sqlite3.connect(other))as dst:src.backup(dst)
   return other
  old_path=clone('original-expiry');new_path=clone('candidate-expiry')
  expected=original['storage.world_elixirs'].expire(old_path,uid,aid,lambda *_:[],now=fixed+1801)
  with committed_reads(connections=c.app.read_connections):actual=elixirs.expire(new_path,uid,aid,lambda *_:[],now=fixed+1801)
  assert actual==expected and contents(old_path)==contents(new_path)and not actual['state']['rows']
  failed=clone('rejected-expiry');before=contents(failed)
  def reject(*_):raise ValueError('Owned expiry encoding failure')
  try:
   with committed_reads(connections=c.app.read_connections):elixirs.expire(failed,uid,aid,reject,now=fixed+1801)
  except ValueError as error:assert str(error)=='Owned expiry encoding failure'
  else:raise AssertionError('Failed positive expiry hidden')
  assert contents(failed)==before
  # Current SQL owner is read again even on an already prepared connection.
  with contextlib.closing(sqlite3.connect(failed))as db,db:db.execute('UPDATE character_owners SET account_id=account_id+100 WHERE uid=?',(uid,))
  for module in(original['storage.world_elixirs'],elixirs):
   try:
    with committed_reads(connections=c.app.read_connections):module.snapshot(failed,uid,aid,now=fixed)
   except ValueError as error:assert str(error)=='Profession character ownership'
   else:raise AssertionError('Stale owner accepted')
  assert all(not db.in_transaction for observers,files,readers in c.app.read_connections.workers.values()for db in readers.values())
  out=dict(passed=True,pinned_view_results=checks,no_pure_SQL_changes=True,real_owned_elixir_use_receipt=True,active_and_negative_expiry_equal=True,positive_expiry_full_SQL_equal=True,encoding_failure_rolls_back=True,external_commit_owner_change_seen=True,negative_read_under_actual_WAL_writer=True,no_retained_read_transactions=True)
 finally:await c.asyncTearDown()
 out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections));(h.H/'upkeep-readonly-tests.json').write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
asyncio.run(main())
