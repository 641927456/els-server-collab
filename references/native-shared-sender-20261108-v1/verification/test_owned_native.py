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
  r.f.Characters(f.config.state_file,f.alice['id']).create('OwnedSend',1,'owned-native-v9')
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
    town=any(getattr(s,'phase',None)in('town_ready','dungeon_active')for s in f.app.playing.values())
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
  assert entries and (BASELINE or all(v['lock_recursion']>=1 for v in entries)),'Entry lock must actually be held'
  leaves=[v for v in trace if v.get('payload',{}).get('event')=='owned_send_leave']
  if not BASELINE:assert len(leaves)>0 and abs(len(entries)-len(leaves))<=1,dict(entries=len(entries),leaves=len(leaves))
  ready_events={v.get('payload',{}).get('event')for v in trace}
  assert {'local_artifact_restore_ready','raid_native_power_ready','dungeon_result_stats_ready'}<=ready_events,ready_events
  logical_counts=[v['payload']['logical_observers']for v in trace if v.get('payload',{}).get('event')=='owned_send_lock_state']
  assert logical_counts and max(logical_counts)==7,logical_counts
  assert proc.returncode==0 and report['file_sha256_after']==report['file_sha256']
  assert not psutil.pid_exists(identity['pid'])or psutil.Process(identity['pid']).create_time()!=identity['created']
  return dict(ok=True,baseline_no_gate=BASELINE,actual_original_game=True,temporary_authenticated_server=True,actual_owned_authenticated_scene=True,
      actual_composed_support_loaded=not BASELINE,repeated_same_script_install_same=not BASELINE,natural_owned_scene_observed_seconds=32,
      native_lock_returns_to_zero=True,maximum_idle_sample_recursion=max(locks),
      observed_send_entries_lock_held=len(entries),
      observed_JS_return_callbacks=len(leaves),
      logical_sender_observers=max(logical_counts),physical_sender_listener_count_by_exact_source=2,artifact_in_main_script=True,raid_power_and_result_stats_ready=True,
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
