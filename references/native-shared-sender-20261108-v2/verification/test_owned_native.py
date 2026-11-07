"""Launch only our own original game, with a temporary authenticated server."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,os,subprocess,sys,time,traceback
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate';W=H.parent
BASELINE='--baseline'in sys.argv
sys.dont_write_bytecode=True;os.environ['ELS_CRASH_TEST_RUNTIME']=str(C);sys.argv=[__file__]
spec=importlib.util.spec_from_file_location('owned_v9_native_fixture',W/'reproduce_tutorial_late_death.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sys.path[:0]=[str(C/'tools'),str(C/'tools/pylibs')]
import psutil
from launch_client import COMMON_FLAGS
CLIENT=Path('D:/艾尔之光/data/x2_dx11.exe')

async def main():
 assert not any((p.info['name']or'').lower()in('x2.exe','x2_dx11.exe')for p in psutil.process_iter(['name'])),'Existing game; never attach or stop it'
 assert hashlib.sha256(CLIENT.read_bytes()).hexdigest()=='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
 f=r.f.FriendsTests();await f.asyncSetUp();proc=None;run=None
 try:
  character=r.f.Characters(f.config.state_file,f.alice['id']).create('OwnedSend',1,'owned-native-v11-town',quick_start=True)
  from els_server.storage.quick_start import participant
  with r.closing(r.sqlite3.connect(f.config.state_file))as db:
   assert participant(db,character['uid'],f.alice['id'])
   location=db.execute('SELECT * FROM location WHERE uid=?',(character['uid'],)).fetchone();assert location[1]==20000
  (H/'town-fixture-prerequisites.json').write_bytes((json.dumps(dict(existing_quick_start_transaction=True,account_owned_temporary_identity=True,starting_town=20000,tutorial_skip_uses_existing_participant_rule=True,player_databases_modified=False,production_rules_changed=False),indent=2)+'\n').encode())
  bridge=f.bridge(f.alice);bridge.log=lambda event,**kw:f.events.append(dict(event='bridge:'+event,**kw));await bridge.start()
  before=set((C/'analysis/client-6c6b5180').iterdir())
  output=(H/'owned-native-console.private.txt').open('wb')
  command=[sys.executable,str(H/'owned_native_worker.py'),'--client',str(CLIENT),*COMMON_FLAGS,'--remote-bridge',*(['--baseline']if BASELINE else[])]
  proc=subprocess.Popen(command,cwd=C,stdout=output,stderr=subprocess.STDOUT,creationflags=0x08000000)
  started=time.monotonic();loaded=None;town=None;ready=None;seen=[]
  while time.monotonic()-started<100:
   await asyncio.sleep(.5)
   (H/'owned-native-live.private.json').write_bytes((json.dumps(dict(events=f.events,phases=[dict(role=s.role,phase=s.phase,build=s.client_build)for s in f.app.playing.values()]),indent=2)+'\n').encode())
   fresh=[p for p in(C/'analysis/client-6c6b5180').iterdir()if p.is_dir()and p not in before and(p/'client-process.json').is_file()]
   if fresh:assert len(fresh)==1;run=fresh[0]
   if run and(run/'trace.jsonl').exists():
    seen=[]
    for line in(run/'trace.jsonl').read_bytes().splitlines():
     try:v=json.loads(line)
     except ValueError:continue
     if v.get('type')=='error':raise AssertionError(v.get('description'))
     value=v.get('payload',{});seen.append(value)
    loaded=next((v for v in seen if v.get('event')=='owned_send_serialization_loaded'),None)
    ready=any(v.get('event')=='native_cache_sync_ready'for v in seen)
    town=any(getattr(s,'phase',None)in('town_ready',)for s in f.app.playing.values())
    if loaded and ready and town:break
   if proc.poll()is not None:raise AssertionError('Owned probe exited: '+str(proc.returncode))
  assert run and loaded and (BASELINE or loaded['active']and loaded['repeated_install_same'])and ready and town,dict(run=str(run),loaded=loaded,ready=ready,town=town)
  # Exercise the original periodic send naturally in town; no fabricated DTO.
  observed=time.monotonic()
  while time.monotonic()-observed<32:
   await asyncio.sleep(.5)
   assert proc.poll()is None,'Owned game/probe unexpectedly exited'
  errors=[v for v in f.events if v['event']in('protocol_error','worker_error','notification_error')]
  assert not errors,errors
  (run/'client.stop').write_text('owned send validation complete','utf8')
  await asyncio.wait_for(asyncio.to_thread(proc.wait),20);output.close()
  report=json.loads((run/'probe.json').read_bytes());identity=json.loads((run/'client-process.json').read_bytes())
  trace=[json.loads(v)for v in(run/'trace.jsonl').read_bytes().splitlines()]
  locks=[v['payload']['recursion']for v in trace if v.get('payload',{}).get('event')=='owned_send_lock_state']
  assert locks and max(locks)<=1 and locks[-1]==0,dict(lock_recursion_samples=locks)
  entries=[v['payload']for v in trace if v.get('payload',{}).get('event')=='owned_send_enter']
  assert entries,'Native sender observation must execute'
  leaves=[v for v in trace if v.get('payload',{}).get('event')=='owned_send_leave']
  if not BASELINE:assert len(leaves)>0 and abs(len(entries)-len(leaves))<=1,dict(entries=len(entries),leaves=len(leaves))
  states=[v['payload']for v in trace if v.get('payload',{}).get('event')=='owned_send_lock_state']
  assert states and any(v['opened']and v['closed']for v in states),'Normal owned ED shop open/close was not completed'
  assert all(v['stats']['failed']==0 for v in states),states[-1]
  final=states[-1];assert final['stats']['active']==0 and final['stats']['encryptions']==final['stats']['cleanups']>0,final
  assert abs(final['fieldEnter']-final['fieldLeave'])<=1 and final['fieldEnter']>0,final
  physical=[v['payload']['RVA']for v in trace if v.get('payload',{}).get('event')=='owned_physical_observer_attached']
  assert sorted(physical)==['0x30d0660','0x682d80'],physical
  events={v.get('payload',{}).get('event')for v in trace}
  assert {'local_artifact_restore_ready','local_ed_shop_bridge_ready','raid_native_power_ready','dungeon_result_stats_ready','owned_shop_closed_verified'}<=events,events
  assert max(v['logical_observers']for v in states)==7
  assert max(v['logical_field_observers']for v in states)>=4
  assert final['closed'] and final['logical_field_observers']==3,final
  assert proc.returncode==0 and report['file_sha256_after']==report['file_sha256']
  assert not psutil.pid_exists(identity['pid'])or psutil.Process(identity['pid']).create_time()!=identity['created']
  return dict(ok=True,baseline_no_gate=BASELINE,actual_original_game=True,temporary_authenticated_server=True,actual_owned_authenticated_scene=True,
      actual_composed_support_loaded=not BASELINE,repeated_same_script_install_same=not BASELINE,natural_owned_scene_observed_seconds=32,
      native_lock_returns_to_zero=True,maximum_idle_sample_recursion=max(locks),
      observed_send_entries=len(entries),
      observed_JS_return_callbacks=len(leaves),
      crypto_stats=final['stats'],sender_physical_JS_listeners=1,town_frame_physical_JS_listeners=1,native_fast_replacements=2,field_entries=final['fieldEnter'],field_returns=final['fieldLeave'],owned_shop_native_open_and_close=True,logical_sender_observers=7,maximum_logical_field_observers=max(v['logical_field_observers']for v in states),
      protocol_errors=0,owned_exit_and_detach_completed=True,original_EXE_unchanged=True,
      player_process_control=False,original_KOM_changed=False,production_modified=False,
      historical_duplicate_cause_proven=False,run_evidence=str(run))
 finally:
  (H/'owned-native-server.private.json').write_bytes((json.dumps(dict(events=f.events,phases=[dict(role=s.role,phase=s.phase,build=s.client_build)for s in f.app.playing.values()]),indent=2)+'\n').encode())
  if proc and proc.poll()is None:
   if run:(run/'client.stop').write_text('owned test finalizer','utf8')
   try:await asyncio.wait_for(asyncio.to_thread(proc.wait),20)
   except TimeoutError:proc.terminate();await asyncio.to_thread(proc.wait)
  await f.asyncTearDown()

if __name__=='__main__':
 result=dict(ok=False)
 try:result=asyncio.run(main())
 except BaseException:result.update(error=traceback.format_exc());raise
 finally:(H/('owned-native-baseline.json'if BASELINE else'owned-native.json')).write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
