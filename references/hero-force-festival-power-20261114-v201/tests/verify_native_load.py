"""One fresh, owned original-client cold login using the actual signed install."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,os,sqlite3,subprocess,sys,time,traceback,uuid
H=Path(__file__).resolve().parent;ROOT=H.parents[1];N=H/'native';run=N/'cold-6'
cfg=json.loads((run/'probe-input.json').read_bytes());RUNTIME=Path(cfg['runtime']);WORK=N/'fixture-6';WORK.mkdir(exist_ok=True);assert not(WORK/'game.sqlite3').exists(),'Never overwrite a previous owned experiment'
sys.dont_write_bytecode=True
sys.path[:0]=[str(RUNTIME),str(RUNTIME/'tools')]
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.storage.lifecycle import SaveLease,prepare_database,checkpoint_database
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.reward_state import RewardState
from els_server.storage.festival_origins import saved
from els_server.storage.seal_quests import QuestState
from els_server.game_data import client_data
PY=Path('C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe')
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def state():
 code='import sys,json,os;sys.path[:0]='+repr([str(RUNTIME/'tools'),str(RUNTIME/'tools/pylibs')])+';import psutil;from client_process_guard import has_running_client;print(json.dumps(dict(running=has_running_client(),created=psutil.Process(os.getppid()).create_time())))'
 return json.loads(subprocess.check_output([str(PY),'-B','-c',code],creationflags=0x08000000))
def events():
 out=[]
 for p in run.glob('20*/trace.jsonl'):
  for line in p.read_text('utf8').splitlines():
   d=json.loads(line);out.append(d.get('payload',d))
 return out
async def main():
 assert sys.version_info[:2]==(3,14)and not sys._is_gil_enabled()and sqlite3.sqlite_version=='3.54.1'
 assert all(Path(m.__file__).resolve().is_relative_to(RUNTIME)for n,m in sys.modules.items()if n.startswith('els_server')and getattr(m,'__file__',None))
 cert=subprocess.run([str(RUNTIME/'server-python/python.exe'),'-B',str(RUNTIME/'tools/create_friends_certificate.py'),'--output-dir',str(WORK/'tls'),'--host','127.0.0.1'],capture_output=True,text=True,check=True,timeout=60,creationflags=0x08000000)
 pin=cert.stdout.strip();assert len(pin)==64
 config=ServerConfig(host='127.0.0.1',port=0,client_probe_port=19533,state_file=WORK/'game.sqlite3',accounts_file=WORK/'accounts.sqlite3',tls_cert=WORK/'tls/server-cert.pem',tls_key=WORK/'tls/server-key.pem',log_dir=WORK/'logs',shutdown_timeout=10)
 prepare_database(config.state_file)
 lockpath=ROOT/'analysis/coordination-20261015/isolated-game-test.lock';token=uuid.uuid4().hex
 lease=dict(owner='publisher-v201-four-repairs-native',pid=os.getpid(),owner_created=state()['created'],token=token,directory=str(N),purpose='Owned original-client cold notification and actual signed support load')
 app=server=bridge=proc=console=None;claimed=False;result=dict(ok=False,actual_TLS=False,original_client=False,natural_GUI=False,physical_input=False,production_database_used=False);logs=[]
 def log(event,**kw):
  row=dict(event=event,**kw);logs.append(row)
  with(WORK/'events-private.jsonl').open('a',encoding='utf8')as stream:stream.write(json.dumps(row,default=str)+'\n')
 try:
  with SaveLease(config.state_file):
   app=Application(config);await app.start();identity=await app.call(app.registry.create,'publisherfes'+token[:8])
   role=await app.call(Characters(config.state_file,identity['id']).create,'FesNative',1,'festival-native-'+token);assert role['uid']==1001
   RewardState(config.state_file,1001,account_id=identity['id']);QuestState(config.state_file,1001,account_id=identity['id']).snapshot()
   with closing(sqlite3.connect(config.state_file))as db,db:
    db.execute('UPDATE characters SET level=99 WHERE uid=1001')
    db.execute('UPDATE reward_balances SET experience=?,ed=1000 WHERE uid=1001',(client_data().thresholds[98],))
   from els_server.domain.town_travel import catalog
   location=LocalState(config.state_file,1001);location.save(20010,0,0,catalog()['towns']['20010']['xyz']);location.save(1503,0,0,catalog()['towns']['1503']['xyz'])
   with closing(sqlite3.connect(config.state_file))as db:assert saved(db,1001,identity['id'])==20010
   server=GameServer(config,app,log);_,port=await server.start()
   bridge=Bridge(BridgeConfig('127.0.0.1',port,identity['name'],identity['token'],pin,local_port=19534,probe_port=19533),log);await bridge.start()
   # Prepare our own TLS/save first, then compete only for a genuinely free
   # window. Waiting does not acquire, remove or repair a foreign lease.
   waiting=time.monotonic()
   while time.monotonic()-waiting<600:
    if not lockpath.exists()and not(await asyncio.to_thread(state))['running']:
     try:
      with lockpath.open('x',encoding='utf8')as stream:json.dump(lease,stream)
     except FileExistsError:
      await asyncio.sleep(1);continue
     claimed=True;break
    await asyncio.sleep(1)
   assert claimed,'No free native window within the bounded wait; leave the foreign process untouched'
   result['native_window_wait_seconds']=round(time.monotonic()-waiting,2)
   assert not state()['running']
   console=(run/'console-private.txt').open('wb')
   proc=await asyncio.create_subprocess_exec(str(PY),'-B',str(N/'native_runner.py'),str(run),stdout=console,stderr=subprocess.STDOUT,creationflags=0x08000000)
   result['original_client']=True
   deadline=time.monotonic()+220
   while time.monotonic()<deadline:
    e=events();applied=[r for r in e if r.get('event')=='festival_return_origin_applied'];observed=[r for r in e if r.get('event')=='festival_native_inspect']
    errors=[r for r in e if r.get('type')=='error'or r.get('event')in('native_script_error','festival_native_error')]
    assert not errors,'Owned native support reported an error'
    if applied and observed:break
    if proc.returncode is not None:raise AssertionError('Owned original-client runner exited '+str(proc.returncode))
    await asyncio.sleep(.5)
   else:raise TimeoutError('Actual festival input was not applied/read in the original client')
   assert any(row.get('event')=='my_buff_cleanup_ready'for row in e),'Final MyBuff repair did not activate'
   assert any(row.get('event')=='raid_native_power_ready'for row in e),'Final client-power support did not activate'
   assert len(applied)==1 and applied[0]['uid']=='1001'and applied[0]['town']==20010
   assert observed[0]['map']==1503 and observed[0]['origin']==20010
   with closing(sqlite3.connect(config.state_file))as db:
    assert saved(db,1001,identity['id'])==20010 and location.load()['map']==1503
    assert db.execute('SELECT ed FROM reward_balances WHERE uid=1001').fetchone()[0]==1000
   result.update(ok=True,mybuff_ready=True,raid_native_power_ready=True,actual_TLS=True,actual_signed_install=str(RUNTIME),native_notification=applied[0],native_readback=observed[0],native_default_handlers_passed=True,source_origin_persisted=True,ED_unchanged=True,client_signature_definition=hashlib.sha256((H/'packages/client.payload.json').read_bytes()).hexdigest(),server_signature_definition=hashlib.sha256((H/'packages/server-addon.payload.json').read_bytes()).hexdigest(),port_only_harness_override=19534,return_button_natural_click=False)
 except BaseException as exc:
  write(N/'failure-private.json',dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc()));raise
 finally:
  if proc:
   for path in run.glob('20*/client-process.json'):(path.parent/'client.stop').touch()
   try:await asyncio.wait_for(proc.wait(),25)
   except TimeoutError:proc.terminate();await proc.wait();result['runner_forced_stop']=True
   if console:console.close()
   if(run/'closed.json').exists():result['cleanup']=json.loads((run/'closed.json').read_bytes())
  if bridge:await bridge.close()
  if server:await server.close()
  if app:app.close()
  checkpoint_database(config.state_file)
  released=not claimed
  if claimed:
   assert lockpath.exists()and json.loads(lockpath.read_bytes()).get('token')==token
   lockpath.unlink();released=True
  result.update(owned_connections_closed=not server or not server.connections,lease_released=released,GIL_enabled=sys._is_gil_enabled())
  write(N/'result.json',result)
  print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':asyncio.run(main())
