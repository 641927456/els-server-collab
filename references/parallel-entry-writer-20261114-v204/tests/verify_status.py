from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,asyncio,ctypes,json,sys,threading,time
H=Path(__file__).resolve().parent;ROOT=H.parents[1]
a=argparse.ArgumentParser();a.add_argument('--parent',action='store_true');a.add_argument('--online',action='store_true');args=a.parse_args()
R=(H/'runtime/online-parent-combined'if args.parent else H/'runtime/online-combined')if args.online else(ROOT/'analysis/publisher-auth-scope-20261114-v203/runtime/combined'if args.parent else H/'runtime/combined');W=H/(('status-online-'if args.online else'status-')+('parent'if args.parent else'candidate'));W.mkdir()
sys.path[:0]=[str(ROOT/'analysis/publisher-auth-scope-20261114-v203/publication/qa'),str(R),str(R/'tools')]
engine=ctypes.WinDLL(str(R/'python/sqlite3.dll'));import sqlite3
assert sqlite3.sqlite_version=='3.54.1'and not sys._is_gil_enabled()
import protocol_harness as h;h.bind_runtime(R)
from els_server.gm_runtime import Runtime
from els_server.protocol.protocol_codec import Event
async def main():
 f=h.Fixture(W);release=threading.Event();acquired=threading.Event();holder=None;status=None;foreground=None
 try:
  await f.start();one=await f.actor(1);two=await f.actor(2);gm=Runtime(f.app,f.server,W/'gm-audit.json')
  expected=await f.app.call(gm.players);initial_status=await f.app.call(gm.execute,dict(action='status'))
  def hold():
   with f.app.dungeon_workers.scope(two.session,mailboxes=False):acquired.set();assert release.wait(10)
  holder=asyncio.create_task(asyncio.to_thread(hold));assert await asyncio.to_thread(acquired.wait,2)
  status=asyncio.create_task(f.app.call(gm.execute,dict(action='status')));await asyncio.sleep(.15)
  start=time.perf_counter();foreground=asyncio.create_task(f.app.call(one.session.periodic_notifications))
  done,_=await asyncio.wait((foreground,),timeout=.35);unblocked=bool(done);elapsed=(time.perf_counter()-start)*1000
  release.set();await holder;await foreground;actual_status=await status;actual=actual_status['players'];assert actual_status==initial_status
  assert {r['uid']for r in actual}=={one.uid,two.uid}and actual==expected
  assert unblocked is (not args.parent),(unblocked,args.parent)
  checks={}
  if not args.parent:
   d=f.app.dungeon_workers
   class Fake:
    def __init__(self):self.app=f.app
    def players(self):pass
   class Sub(Runtime):pass
   checks=dict(real_status=d.gm_player_read(gm.execute,(dict(action='status'),)),real_players=d.gm_player_read(gm.players,()),give_stays_bulk=not d.gm_player_read(gm.execute,(dict(action='give'),)),batch_online_stays_bulk=not d.gm_player_read(gm.execute,(dict(action='batch-give',value=dict(mode='online')),)),subclass_stays_bulk=not d.gm_player_read(Sub(f.app,f.server,W/'sub.json').players,()),lookalike_rejected=not d.gm_player_read(Fake().players,()),other_app_rejected=not d.gm_player_read(Runtime(object(),None,W/'x.json').players,()))
   assert all(checks.values())
   # A read that captured a source before that source released must skip it.
   old=two.session;before=f.app.registry.total if hasattr(f.app.registry,'total')else None
   await two.peer.close();f.actors.remove(two)
   for _ in range(100):
    if old.released:break
    await asyncio.sleep(.02)
   assert old.released
   rows=await f.app.call(gm.players);assert [r['uid']for r in rows]==[one.uid]
   # Real GM economy still executes under its unchanged all-actor scope.
   result=await f.give(one,77000,1);assert result
   checks.update(released_source_omitted=True,real_GM_give_succeeded=True)
  assert not[r for r in f.logs if r['event']in('worker_error','notification_error','connection_task_error','protocol_error')]
  out=dict(ok=True,parent=args.parent,online=args.online,actual_TLS=True,foreground_completed_while_other_actor_held=unblocked,foreground_window_ms=elapsed,status_shape_and_values_equal=True,status_fields=sorted(initial_status),checks=checks,source_runtime=str(R),artificial_hold_only_on_owned_second_actor=True)
  (W/'result.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out))
 finally:
  release.set()
  for task in(holder,status,foreground):
   if task:await asyncio.gather(task,return_exceptions=True)
  await f.close()
if __name__=='__main__':asyncio.run(main())
