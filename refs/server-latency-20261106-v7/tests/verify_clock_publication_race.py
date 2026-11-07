"""Real native B3/BB with one genuinely lock-skipped publication, then recovery."""
import runtime_fixture as h
import asyncio,json,sys,threading,time
from unittest.mock import patch
from profile_town import seed
from els_server.domain.dungeon_time_sync import context
probe=h.load('owned_clock_race_probe',h.ROOT/'analysis/glass-door-20261104-v1/repair-v3/gate_probe.py')
async def main():
 fixed='--expect-fixed'in sys.argv;c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False,expected_fixed=fixed,cases=[],publication_skips=[])
 try:
  uid=seed(c,c.alice,'OwnClockRace',False);p=await c.peer(c.alice);await p.roster()
  await c.server.periodics.close();original=c.app.dungeon_workers.publish
  def publish(function,args,**kwargs):
   if getattr(function,'__name__','')=='handle'and args and args[0].kind in(0xb3,0xbb):
    held=threading.Event();release=threading.Event()
    def holder():
     with c.app.world_lock:
      held.set();assert release.wait(3),'Owned lock holder deadline'
    thread=threading.Thread(target=holder,name='owned-world-publication-race');thread.start()
    try:
     assert held.wait(2);before=c.app.realtime.view
     result=original(function,args,**kwargs)
     assert c.app.realtime.view is before,'Expected actual nonblocking world-lock skip'
     out['publication_skips'].append(args[0].kind);return result
    finally:release.set();thread.join(3);assert not thread.is_alive()
   return original(function,args,**kwargs)
  async def recover_and_observe(label):
   s=c.app.playing[c.alice['id']];key=context(s)
   assert key is not None and c.server.realtime.clock(s)!=key
   await c.app.call(lambda:None)
   assert c.server.realtime.clock(s)==key
   got=False
   try:
    async with asyncio.timeout(1.6):
     event=await p.until(0x9c);assert event.payload==bytes(4);got=True
   except TimeoutError:pass
   out['cases'].append(dict(case=label,actual_world_lock_skipped_publication=True,view_recovered=True,native_clock_resumed=got))
   assert got==fixed,(label,got,fixed)
  with patch.object(c.app.dungeon_workers,'publish',publish):
   await probe.solo_load(p,uid);await recover_and_observe('initial_B3_missing_view')
   s=c.app.playing[c.alice['id']]
   await probe.clear_first(p,uid,s.dungeon_run)
   await probe.finish_solo(p);await recover_and_observe('BB_stale_prior_part_view')
  out.update(passed=True,behavior_correct=fixed,bug_reproduced=not fixed,physical_player_input=False,source=h.bootstrap.SOURCE_BINDINGS)
 finally:
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),errors=[r['event']for r in c.events if r['event']in('worker_error','notification_error','connection_task_error')])
  (h.H/('clock-race-fixed.json'if fixed else'clock-race-before.json')).write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out));assert out['passed']and not out['errors']
asyncio.run(main())
