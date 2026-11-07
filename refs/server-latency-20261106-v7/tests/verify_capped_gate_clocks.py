"""Actual capped/level-up AD and real independent clock ledgers/final flush."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,time
from unittest.mock import patch
from profile_town import seed
from els_server.game_data import client_data
from els_server.domain.attendance_2026_online import AttendanceOnlineClock
from els_server.domain.online_2026_clock import OnlineTitleClock
probe=h.load('capped_death_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False)
 try:
  ids=[c.alice,c.bob];uids=[seed(c,v,'OwnCD'+str(i),i==0)for i,v in enumerate(ids)]
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   db.execute('UPDATE characters SET level=98,revision=revision+1 WHERE uid=?',(uids[1],))
   db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[98]-1,uids[1]))
  peers=[await c.peer(v)for v in ids]
  for p in peers:await p.roster()
  await c.server.periodics.close()
  await probe.solo_load(peers[0],uids[0])
  #34710 requires level99. The original El Tree route admits the actual
  #level98 actor; keep its normal admission and original population source.
  original_identity=probe.IDENTITY;probe.IDENTITY=30000
  try:await probe.solo_load(peers[1],uids[1])
  finally:probe.IDENTITY=original_identity
  s=c.app.playing[ids[0]['id']];pair=s.activity2026_awards.online;a=pair.attendance;t=pair.title.clock
  # The real display/mail consumer requires the selected save path. Isolate
  # new observations by their clock operation tokens in this owned database.
  path=c.config.state_file
  current=[10.,float(int(time.time()))];base=current[1]
  ae=a.eligibility;te=t.eligibility
  def identity(resolve):
   def selected(session):
    value=resolve(session)
    return None if value is None else(str(path),*value[1:])
   return selected
  a=AttendanceOnlineClock(a.definition,campaign=a.campaign,definition_sha256=a.digest,schedule=a.schedule,eligibility=identity(ae),monotonic=lambda:current[0],epoch=lambda:current[1])
  t=OnlineTitleClock(t.selection_bytes,campaign=t.campaign,eligibility=identity(te),monotonic=lambda:current[0],epoch=lambda:current[1])
  pair.attendance=a;pair.title.clock=t
  for clock in(a,t):clock.observe(s)
  current[:]=[12.,base+2];calls=[];observe=pair.observe
  def counted(*args,**kwargs):calls.append(True);return observe(*args,**kwargs)
  npc=s.dungeon_run.current['npcs'][0]
  with patch.object(pair,'observe',counted):
   await peers[0].send(0xad,probe.accepted_combat(npc,uids[0]));assert(await peers[0].until(0xae)).payload==bytes(4);await peers[0].until(0xcf)
  assert not calls,'Capped AD repeated online clock persistence'
  with contextlib.closing(sqlite3.connect(path))as db:
   assert db.execute('SELECT 1 FROM activity518_facts WHERE operation LIKE ?',('online:'+a.token+':%',)).fetchone()is None
  calls=[]
  with patch.object(pair,'observe',counted):
   await probe.clear_first(peers[0],uids[0],s.dungeon_run)
   assert s.dungeon_run.next['kind']==0
   await peers[0].send(0xb8,b'\1');assert(await peers[0].until(0xb9)).payload==bytes(4)
   assert(await peers[0].until(0xba)).payload==b'\1'
   await peers[0].send(0xbb,b'\1');assert(await peers[0].until(0xbc)).payload==bytes(4)
   assert(await peers[0].until(0xbd)).payload[:1]==b'\1'
  assert not calls,'Same-stage capped curtain repeated foreground clocks'
  # Predicate-only boundary checks: no fabricated settlement is dispatched.
  from els_server.domain.session_auxiliary import activity_due
  for kind in(1,4):
   with patch.object(s.dungeon_run,'next',dict(kind=kind)):
    assert activity_due(s.handle,(h.Event(0x202,kind=0xbb,payload=b'\1'),))
  # Existing independent upkeep, then final disconnect/stop-style flush,
  # records every whole second which the foreground did not write.
  current[:]=[13.,base+3];s._clear_periodic_steps();s.next_periodic=0
  await c.app.call(s.periodic_notifications)
  current[:]=[14.,base+4]
  for clock in(a,t):clock.observe(s,stop=True)
  with contextlib.closing(sqlite3.connect(path))as db:
   spans=[(v['starts'],v['ends'])for(raw,)in db.execute('SELECT payload FROM activity518_facts WHERE operation LIKE ?',('online:'+a.token+':%',))for v in[json.loads(raw)]]
   title=db.execute('SELECT starts,ends FROM online2026_spans WHERE operation LIKE ?',('%'+t.token+'%',)).fetchall()
  def seconds(spans):
   return len({n for start,end in spans for n in range(start,end)})
  assert seconds(spans)==4 and seconds(title)==4,(spans,title)
  lower=c.app.playing[ids[1]['id']];assert lower.account.character_identity()['level']==98
  lower_pair=lower.activity2026_awards.online;observe=lower_pair.observe;calls=[]
  def counted_lower(*args,**kwargs):calls.append(True);return observe(*args,**kwargs)
  from els_server.domain.dungeon_population import population
  npc=population(lower.gate_stage,hp_context=getattr(lower,'_c1_hp_context',None))['npcs'][0]
  with patch.object(lower_pair,'observe',counted_lower):
   await peers[1].send(0xad,probe.accepted_combat(npc,uids[1]));assert(await peers[1].until(0xae)).payload==bytes(4);await peers[1].until(0xcf)
  assert len(calls)==2 and lower.account.character_identity()['level']==99,(len(calls),lower.account.character_identity())
  out.update(passed=True,capped_actual_native_death_has_no_clock_write=True,actual_same_stage_B8_and_BB_skip_only_foreground_clocks=True,cross_stage_and_final_predicate_keep_observations=True,independent_upkeep_and_final_stop_preserve_all_four_seconds=True,actual_level98_to99_death_keeps_both_observations=True,clock_injection_only_in_owned_fixture=True)
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  (h.H/'capped-gate-clocks-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out));assert out['passed']and not out['errors']
asyncio.run(main())
