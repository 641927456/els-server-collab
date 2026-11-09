"""Real actor/SQL marker consumer; producer qualification is retained separately."""
import bootstrap,runtime_fixture as h
import asyncio,contextlib,hashlib,json,psutil,sqlite3,struct,sys,threading,time,traceback
from unittest.mock import patch
from els_server.domain import achievement_flow as flow
from els_server.domain.achievement_catalog import catalog
from els_server.storage.achievement_history import record_notebook
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog as towns
from els_server.game_data import client_data
from els_server.storage import achievements as state
from els_server.protocol.protocol_codec import Event
from els_server.__main__ import _native_timing,_normal_scheduling
psutil.Process().cpu_affinity([20,22]);_normal_scheduling()
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(ok=False,checks={},source_preview=True,producer_and_natural_GUI_claim=False)
 try:
  account=c.alice['id'];path=c.config.state_file
  uid=Characters(path,account).create('OwnNote',14,'owned-notebook-role')['uid']
  LocalState(path,uid).save(20012,0,0,towns()['towns']['20012']['xyz'])
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98],uid))
  peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid,20012)
  actor=c.app.playing[account];assert actor.account.uid==uid and actor.account.character()['unit_type']==14 and actor.active_map==20012
  npc=next(condition['parameters']['m_iNpcId']for definition in catalog().values()for condition in definition['conditions']if condition['type']==66)
  def invoke(response=None):
   with c.app.dungeon_workers.scope(actor):return flow.synchronize(actor,Event(0x202,kind=0xfd),[Event(0x201,kind=0xfe,payload=bytes(4))]if response is None else response)
  def snapshot():
   with contextlib.closing(sqlite3.connect(path))as db:return state.snapshot(db,account,uid),db.execute("SELECT COUNT(*)FROM native_achievement_operations WHERE account_id=?AND kind='noah-note'",(account,)).fetchone()[0]
  with contextlib.closing(sqlite3.connect(path))as db,db:
   db.execute('BEGIN IMMEDIATE');record_notebook(db,account,uid,npc)
  actor._achievement_notebook_source=(account,uid,npc)
  with patch.object(flow,'encode_event',side_effect=ValueError('owned completion encoding failure')):
   before=snapshot()
   try:invoke()
   except ValueError as error:assert str(error)=='owned completion encoding failure'
   else:raise AssertionError('Completion encoding must fail')
  assert snapshot()==before and actor._achievement_notebook_source==(account,uid,npc)
  out['checks']['completion_failure_rolls_back_progress_and_preserves_marker']=True
  answer=invoke();assert any(row.kind==0x6c0 for row in answer)and actor._achievement_notebook_source is None
  completed=snapshot();assert completed!=before;out['checks']['original_reconcile_commits_completion_and_consumes_marker']=True
  actor._achievement_notebook_source=(account,uid,npc);plans=[];original=flow.pending_updates
  def tracked(*args,**kwargs):plans.append(kwargs['condition_types']);return original(*args,**kwargs)
  with patch.object(flow,'pending_updates',tracked):
   invoke();assert actor._achievement_notebook_source is None
   invoke()
  assert plans==[{66}]and snapshot()==completed,dict(planned_sources=[sorted(v)for v in plans],cold_state_unchanged=snapshot()==completed)
  out['checks']['already_completed_marker_queries_once_without_repeated_upkeep_reads']=True
  actor._achievement_notebook_source=(account,uid,npc)
  original_capture=flow.capture;calls=[]
  def capture(session):
   guard=original_capture(session)
   def check(db):
    guard(db);calls.append(True)
    if len(calls)==2:raise ValueError('owned last guard failure')
   return check
  with patch.object(flow,'capture',capture):
   try:invoke()
   except ValueError as error:assert str(error)=='owned last guard failure'
   else:raise AssertionError('Last guard must fail')
  assert actor._achievement_notebook_source==(account,uid,npc)and snapshot()==completed
  out['checks']['last_guard_failure_preserves_marker_and_cold_state']=True
  invoke();assert actor._achievement_notebook_source is None
  observed=[]
  def protocol_tracked(*args,**kwargs):
   if 66 in kwargs.get('condition_types',()):observed.append(True)
   return original(*args,**kwargs)
  with patch.object(flow,'pending_updates',protocol_tracked):
   await peer.send(0xfd,struct.pack('>i',npc));ack=await peer.until(0xfe)
   assert ack.payload[:4]==bytes(4)
   await asyncio.sleep(.25)
  assert len(observed)==1 and actor._achievement_notebook_source is None and snapshot()==completed
  out['checks']['real_Noah_FD_replay_does_not_leave_repeated_periodic_queries']=True
  out['ok']=True
 except BaseException as error:out.update(error=repr(error),traceback=traceback.format_exc())
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),
   errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')],source=bootstrap.SOURCE_BINDINGS,GIL_enabled=sys._is_gil_enabled())
  out['ok']=out['ok']and out['owned_runtime_removed']and out['connections']==0 and not out['errors']
  target=bootstrap.HERE/'notebook-evidence';target.mkdir(exist_ok=True);(target/'native-notebook-marker.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps({k:v for k,v in out.items()if k!='source'}));return out['ok']
if __name__=='__main__':
 with _native_timing():raise SystemExit(not asyncio.run(main()))
