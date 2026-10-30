"""Owned background launch with API-only diagnostics and a separate memory image.
No old client RVAs, input events, focus changes or original-file modifications.
"""
import argparse,datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'tools/pylibs'))
import frida,psutil
from probe_commands import read_command


def _owned_remote_stop_path(value,remote,base):
 if value is None:return None
 if not remote:raise ValueError('Remote stop marker requires remote bridge mode')
 root=Path(base).resolve()/'state/friends-client';path=Path(value)
 if (not path.is_absolute() or '..' in path.parts or path.name!='bridge.stop'
     or path.parent.parent!=root):raise ValueError('Invalid owned bridge marker path')
 attempt=path.parent.name
 if len(attempt)!=22:raise ValueError('Invalid owned bridge attempt')
 try:datetime.datetime.strptime(attempt,'%Y%m%d-%H%M%S-%f')
 except ValueError:raise ValueError('Invalid owned bridge attempt') from None
 for part in (root.parent,root,path.parent,path):
  try:info=part.lstat()
  except FileNotFoundError:
   if part==path:continue
   raise ValueError('Owned bridge attempt does not exist') from None
  except OSError:raise ValueError('Cannot validate owned bridge marker') from None
  if getattr(info,'st_file_attributes',0)&0x400 or part.is_symlink():
   raise ValueError('Linked bridge marker paths are not allowed')
  if part==path:
   if not part.is_file() or info.st_nlink!=1:raise ValueError('Invalid owned bridge marker file')
  elif not part.is_dir():raise ValueError('Invalid owned bridge attempt directory')
 if path.resolve()!=path:raise ValueError('Owned bridge marker aliases another path')
 return path


def _owned_signal_bridge_stop(path,base,report):
 try:
  path=_owned_remote_stop_path(path,True,base)
  if path is None:return
  try:
   with path.open('x',encoding='utf8') as stream:stream.write('owned probe ended')
  except FileExistsError:pass # The paired wrapper has already signaled it.
 except (OSError,ValueError) as error:report['bridge_stop_error']=type(error).__name__

p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=75);p.add_argument('--argument',default='pxk19slammsu286nfha02kpqnf729ck');p.add_argument('--client',default='D:/\u827e\u5c14\u4e4b\u5149/data/x2_dx11.exe');p.add_argument('--login-probe',action='store_true');p.add_argument('--town-probe',action='store_true');p.add_argument('--dungeon-probe',action='store_true');p.add_argument('--auto-return',action='store_true');p.add_argument('--play',action='store_true',help='Run until client exits; use persistent local save; no automatic dungeon entry');p.add_argument('--state-file',type=Path)
p.add_argument('--no-auto-entry',action='store_true',help='Keep an isolated dungeon-capable test in town for re-login inspection')
p.add_argument('--startup-observer',type=Path,help='Optional early observer for an explicit isolated no-input probe')
p.add_argument('--item-test',action='store_true')
p.add_argument('--shop-test',action='store_true',help='Isolated native shop catalog protocol integration')
p.add_argument('--ice-test',action='store_true',help='Isolated native ice draw integration')
p.add_argument('--lightweight-play',action='store_true',help='Disable optional startup reader observers and timed screenshots for integrated play')
p.add_argument('--local-resource-index',action='store_true',help='Use native disk indexes for the two SHA256-pinned local resource archives')
p.add_argument('--server-config',type=Path,help='Run the structured server instead of the packet-capture experiment')
p.add_argument('--remote-bridge',action='store_true',help='Use the already authenticated loopback TLS bridge; never start a local server')
p.add_argument('--remote-stop-file',type=Path,help='Paired owned friends bridge marker')
p.add_argument('--allow-client-variants',action='store_true',help='Friends-only: no full-file EXE/KOM version lock; keep live native interface verification')
p.add_argument('--native-clear-replay',action='store_true',help='Opt-in isolated server/client result replay')
p.add_argument('--drop-probe',action='store_true')
p.add_argument('--boss-gauge-test',action='store_true')
p.add_argument('--drop-test',action='store_true')
p.add_argument('--until-stopped',action='store_true',help='Keep an isolated test alive until its owned stop file is written');p.add_argument('--npc-slot-test',action='store_true');p.add_argument('--gate-test',action='store_true');p.add_argument('--population-test',action='store_true');p.add_argument('--clear-test',action='store_true');p.add_argument('--reward-probe',action='store_true');p.add_argument('--reward-test',action='store_true');a=p.parse_args()
try:remote_stop_file=_owned_remote_stop_path(a.remote_stop_file,a.remote_bridge,BASE)
except ValueError as error:p.error(str(error))
if a.no_auto_entry and (a.play or not a.until_stopped or not a.dungeon_probe):p.error('No-auto-entry requires a persistent isolated dungeon probe')
if a.startup_observer and (a.play or not a.no_auto_entry or not a.startup_observer.is_file()):p.error('Startup observer requires an explicit isolated probe and existing script')
if a.item_test and not a.reward_test:p.error('Item test requires isolated persistent reward profile')
if a.remote_bridge and (a.server_config or a.state_file or a.native_clear_replay or not a.no_auto_entry or not a.local_resource_index):p.error('Remote bridge requires the pinned manual-entry client profile without a local save/server')
if a.allow_client_variants and not a.remote_bridge:p.error('Client variants are available only for the authenticated friends bridge')
if a.shop_test and (not a.item_test or not (a.state_file or a.remote_bridge) or a.play):p.error('Shop test requires an explicit isolated inventory save or authenticated remote bridge')
if a.ice_test and (not a.item_test or not (a.state_file or a.remote_bridge) or a.play):p.error('Ice test requires an explicit isolated inventory save or authenticated remote bridge')
if a.drop_probe and (not a.item_test or not (a.state_file or a.remote_bridge)):p.error('World drop probe requires an isolated inventory save or authenticated remote bridge')
if a.boss_gauge_test and not a.population_test:p.error('Boss gauge test requires isolated original population')
if a.drop_test and not a.drop_probe:p.error('Persistent pickup test requires isolated ground-spawn profile')
if a.reward_test and (not a.clear_test or a.reward_probe):p.error('Persistent reward test requires clear profile without diagnostic markers')
if a.reward_probe and not a.clear_test:p.error('Reward probe requires isolated clear profile')
if a.clear_test and not a.population_test:p.error('Clear test requires isolated population profile')
if a.population_test and not a.gate_test:p.error('Population test requires isolated gate profile')
if a.gate_test and not a.npc_slot_test:p.error('Gate test requires NPC slot experiment')
if a.until_stopped and not a.dungeon_probe:p.error('Persistent isolated testing requires dungeon probe')
if a.npc_slot_test and (a.play or not a.dungeon_probe):p.error('NPC slot test requires isolated dungeon probe')
if a.play:a.town_probe=True;a.auto_return=a.dungeon_probe
if a.dungeon_probe:a.town_probe=True
if a.town_probe:a.login_probe=True
client=Path(a.client)
from launch_friends_client import verify_client,prepare_native_sources,compatibility_preflight,running_clients
selection=compatibility_preflight(client,a.allow_client_variants) if a.login_probe else None
if a.remote_bridge and not a.login_probe:verify_client(client,a.allow_client_variants)
digest=hashlib.sha256(client.read_bytes()).hexdigest()
if selection and digest!=selection['executable']['sha256']:raise SystemExit('Client changed after compatibility preflight; no client launched.')
if running_clients(psutil):raise SystemExit('Existing client found; no launch or attach.')
prepared_sources={}
profile=Path(selection['native_directory']) if selection else BASE/'analysis'/('client-'+digest[:8])
if a.login_probe:
 # Complete disk verification BEFORE starting the client, so hashing cannot
 # delay installation while its native resource initialization is running.
 snapshot=(profile/'native-prefixes.bin').read_bytes()
 prepared_sources=prepare_native_sources(snapshot,client.parent,a.allow_client_variants,a.local_resource_index)
 if not a.remote_bridge:
  from local_stack_limits import source as local_stack_source
  prepared_sources['stack_limits']=local_stack_source(snapshot)
  from local_shortcut_totals import source as local_shortcut_source
  prepared_sources['shortcut_totals']=local_shortcut_source(snapshot)
if a.server_config:
 from els_server.config import ServerConfig
 server_config=ServerConfig.load(a.server_config)
 if (server_config.profile!='integrated_dx11' or server_config.port!=19400 or
     not a.state_file or server_config.state_file!=a.state_file.resolve() or
     not a.until_stopped or not a.no_auto_entry or not a.local_resource_index or
     not all(getattr(a,k) for k in ('dungeon_probe','npc_slot_test','gate_test','population_test',
                                  'clear_test','reward_test','item_test','shop_test','ice_test',
                                  'drop_probe','drop_test','boss_gauge_test'))):
  p.error('Structured server requires the matching integrated client/save profile')
out=BASE/'analysis'/('client-'+digest[:8]);out.mkdir(exist_ok=True)
stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
run=out/stamp;run.mkdir();server=None;serverlog=None
if a.login_probe and not a.remote_bridge:
 if digest!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709' or client.name.lower()!='x2_dx11.exe':raise SystemExit('DX11 login probe build/name mismatch')
 serverlog=(run/'server-console.jsonl').open('w',encoding='utf8')
 command=[sys.executable,str(BASE/'capture_server.py'),'--seconds',str(a.seconds+15),'--generate-welcome','--local-identity','--client-build','dx11_260923','--stop-file',str(run/'server.stop'),'--output-dir',str(run)]
 if a.play or a.until_stopped:command+=['--until-stopped']
 if a.town_probe:command+=['--enter-town','--state-file',str(a.state_file or (BASE/'state/local.sqlite3' if a.play else run/'probe.sqlite3'))]
 if a.dungeon_probe:command+=['--enter-dungeon']
 if a.npc_slot_test:command+=['--npc-slot-test']
 if a.gate_test:command+=['--gate-test']
 if a.population_test:command+=['--population-test']
 if a.clear_test:command+=['--clear-test']
 if a.reward_probe:command+=['--reward-probe']
 if a.reward_test:command+=['--reward-test']
 if a.item_test:command+=['--item-test']
 if a.shop_test:command+=['--shop-test']
 if a.ice_test:command+=['--ice-test']
 if a.drop_probe:command+=['--drop-probe']
 if a.drop_test:command+=['--drop-test']
 if a.boss_gauge_test:command+=['--boss-gauge-test']
 if a.native_clear_replay:
  if a.server_config:raise SystemExit('Clear replay cannot use the integrated server')
  command+=['--native-clear-replay']
 if a.server_config:
  command=[sys.executable,'-m','els_server','--config',str(a.server_config.resolve()),
           '--stop-file',str(run/'server.stop'),'--log-dir',str(run/'server-logs')]
 server=subprocess.Popen(command,cwd=BASE,stdout=subprocess.DEVNULL if a.server_config else serverlog,
                         stderr=serverlog if a.server_config else subprocess.STDOUT)
 if a.server_config:
  deadline=time.monotonic()+90
  while server.poll() is None and time.monotonic()<deadline:
   status=run/'server-logs/server.jsonl'
   if status.exists() and '"event": "listening"' in status.read_text(encoding='utf8'):break
   time.sleep(.1)
  else:
   if server.poll() is None:
    (run/'server.stop').write_text('server readiness deadline');server.wait(timeout=25)
   serverlog.close();raise SystemExit('Structured server did not become ready; no client launched.')
 else:time.sleep(1)
 if server.poll() is not None:serverlog.close();raise SystemExit('Local server failed; no client launched.')
info=subprocess.STARTUPINFO();info.dwFlags|=subprocess.STARTF_USESHOWWINDOW;info.wShowWindow=4
try:
 if selection:
  from client_compatibility import ensure_unchanged
  ensure_unchanged(selection)
 proc=subprocess.Popen([str(client),a.argument],cwd=client.parent,startupinfo=info)
except Exception:
 if server:
  (run/'server.stop').write_text('client launch failed')
  server.wait(timeout=45 if a.server_config else 10);serverlog.close()
 raise
report={'pid':proc.pid,'created':psutil.Process(proc.pid).create_time(),'exe':str(client),'file_sha256':digest,'argument':a.argument,'no_old_rvas':True,'no_os_input':True,'play':a.play,'npc_slot_test':a.npc_slot_test,'gate_test':a.gate_test,'population_test':a.population_test,'clear_test':a.clear_test,'reward_probe':a.reward_probe,'reward_test':a.reward_test,'auto_dungeon_entry':a.dungeon_probe and not a.play,'auto_training_return':a.auto_return,'consistency':'Sequential live module image, not an atomic snapshot.'}
report['item_test']=a.item_test
report['shop_test']=a.shop_test
report['ice_test']=a.ice_test
report['drop_probe']=a.drop_probe
report['drop_test']=a.drop_test
report['boss_gauge_test']=a.boss_gauge_test
report['lightweight_play']=a.lightweight_play
report['server_config']=str(a.server_config.resolve()) if a.server_config else None
report['local_resource_index_compat']=a.local_resource_index
report['compatibility_preflight_before_launch']=a.login_probe
report['full_file_version_lock']=not a.allow_client_variants
report['native_reference_profile']=str(profile) if a.login_probe else None
report['client_compatibility']=selection['report'] if selection else None
if a.no_auto_entry:report['auto_dungeon_entry']=False
(run/'client-process.json').write_text(json.dumps(report),encoding='utf8')
dump_path=(profile if a.login_probe else out)/'native-prefixes.bin'
log=(run/'trace.jsonl').open('w',encoding='utf8');dump=dump_path.open('rb' if a.login_probe else 'w+b');session=None
try:
 session=frida.attach(proc.pid);clear_received_at=None;clear_sequence=0;login_hooks_ready=False;startup_inventory=None;startup_shop=None;startup_artifact=None
 def receive(m,data):
  global clear_received_at,clear_sequence,login_hooks_ready
  log.write(json.dumps(m,ensure_ascii=True)+'\n');log.flush()
  v=m.get('payload',{})
  if v.get('event')=='updated_login_hooks_ready':login_hooks_ready=True
  if v.get('event')=='native_lifecycle_packet' and v.get('kind')==0xc1 and v.get('result')==1:
   clear_received_at=time.monotonic();clear_sequence+=1
  if v.get('event')=='snapshot_chunk':dump.seek(v['offset']);dump.write(data)
  if v.get('event')=='snapshot_begin':dump.truncate(v['size']);report['base']=v['base'];report['size']=v['size']
 script=session.create_script("""
const image=Process.getModuleByName(__MODULE_NAME__);
function emit(v){send({timestamp:Date.now(),...v});}
for(const api of ['MessageBoxW','MessageBoxA'])Interceptor.attach(Process.getModuleByName('user32.dll').getExportByName(api),{onEnter(a){emit({event:'dialog',api,text:api.endsWith('W')?a[1].readUtf16String():a[1].readCString(),title:api.endsWith('W')?a[2].readUtf16String():a[2].readCString(),caller:this.returnAddress.sub(image.base).toString()});}});
for(const api of ['ExitProcess','TerminateProcess']){const f=Process.getModuleByName('kernel32.dll').findExportByName(api);if(f)Interceptor.attach(f,{onEnter(a){emit({event:'process_exit_requested',api,code:(api==='ExitProcess'?a[0]:a[1]).toUInt32(),caller:this.returnAddress.toString()});}});}
Process.attachModuleObserver({onAdded(m){
 if(/d3d|dxgi/i.test(m.name))emit({event:'graphics_module',name:m.name,path:m.path});
 for(const name of ['D3D11CreateDevice','D3D11CreateDeviceAndSwapChain','Direct3DCreate9','Direct3DCreate9Ex']){
  const f=m.findExportByName(name);if(!f)continue;
  try{Interceptor.attach(f,{onEnter(a){this.name=name;emit({event:'graphics_create_enter',api:name,caller:this.returnAddress.toString()});},onLeave(r){emit({event:'graphics_create_return',api:this.name,result:r.toString()});}});}catch(e){emit({event:'api_hook_error',api:name,error:String(e)});}
 }
}});
rpc.exports={snapshot(){
 emit({event:'snapshot_begin',base:image.base.toString(),size:image.size});
 for(let o=0;o<image.size;o+=1048576){const n=Math.min(1048576,image.size-o);
  try{send({event:'snapshot_chunk',offset:o},image.base.add(o).readByteArray(n));}
  catch(e){for(let j=o;j<o+n;j+=4096){try{send({event:'snapshot_chunk',offset:j},image.base.add(j).readByteArray(Math.min(4096,image.size-j)));}catch(x){emit({event:'snapshot_hole',offset:j});}}}
 }
 emit({event:'snapshot_done'});return true;
}};
emit({event:'attached',base:image.base.toString(),size:image.size});
""".replace('__MODULE_NAME__',json.dumps(client.name)))
 script.on('message',receive);script.load()
 fatal_observer=session.create_script((BASE/'tools/observe_native_fatal.js').read_text(encoding='utf8'));fatal_observer.on('message',receive);fatal_observer.load()
 initial_resources=session.create_script((BASE/'tools/observe_initial_resources.js').read_text(encoding='utf8'));initial_resources.on('message',receive);initial_resources.load()
 resource_dialogs=session.create_script((BASE/'tools/observe_resource_dialog.js').read_text(encoding='utf8'));resource_dialogs.on('message',receive);resource_dialogs.load()
 if a.login_probe:
  # Resource compatibility gets installed before login hooks and optional observers.
  compatibility_scripts=[]
  for name in ('index','digest','config','stack_limits','shortcut_totals'):
   if name in prepared_sources:
    compatibility=session.create_script(prepared_sources[name]);compatibility.on('message',receive);compatibility.load();compatibility_scripts.append(compatibility)
  rvas=(0x6845e0,0x682d80,0x30f6730,0x30f8e00,0x2b4eaa0,0xd9b170)
  if a.town_probe:rvas+=(0x137ad80,0x13a0f90,0x13aeb90,0x13a11f0,0x13835c0)
  if a.dungeon_probe:rvas+=(0x30d0660,0x2cc06d0,0x2b4d0d0,0x2b4cef0,0x2bdcf00,0xc231c0,0x2b42890,0x3b6d140,0x3b6d1c0,0x107f480,0x15684e0,0x7ada60,0x8571d0,0x1aa5b80,0x18c7160,0x184afa0,0x7d8b00,0x15ae30,0x19ec9b0,0x1562bc0,0x1ab2b10,0x3144ca0,0x1b5aa10)
  if a.dungeon_probe:rvas+=(0xc25b90,)
  if a.gate_test:rvas+=(0x16d2090,0x1aa4a40)
  candidate=json.loads((profile/'npc-wire-candidate.json').read_text(encoding='utf8')) if a.dungeon_probe and not a.play else None
  code=(BASE/'tools/trace_dx11_login.js').read_text(encoding='utf8').replace('__VERIFIED_PREFIXES__',json.dumps({r:snapshot[r:r+8].hex() for r in rvas})).replace('__ENTER_TOWN__','true' if a.town_probe else 'false').replace('__ENTER_DUNGEON__','true' if a.dungeon_probe else 'false').replace('__NPC_CANDIDATE__',json.dumps(candidate)).replace('__AUTO_RETURN__','true' if a.auto_return else 'false').replace('__GATE_IDENTITY_TEST__','true' if a.gate_test else 'false').replace('__POPULATION_TEST__','true' if a.population_test else 'false').replace('__LIGHTWEIGHT_PLAY__','true' if a.lightweight_play else 'false')
  login_script=session.create_script(code);login_script.on('message',receive);login_script.load()
  startup_observer=None
 print(str(run),flush=True);start=time.monotonic();captured=False;captures=set();town_ready_time=None;dungeon_queued=False;last_command=None;extension=None;extension_stamp=None
 while proc.poll() is None and (a.play or a.until_stopped or time.monotonic()-start<a.seconds) and not (run/'client.stop').exists():
  if a.allow_client_variants and not login_hooks_ready and time.monotonic()-start>35:
   print('ELS_LAUNCH_ERROR: 当前客户端的运行接口与朋友服适配器不兼容，请将 game-launch.log 发给房主。',flush=True)
   raise RuntimeError('Native interface verification timed out; no game interface hooks installed')
  if a.startup_observer and login_hooks_ready and startup_observer is None:
   startup_observer=session.create_script(a.startup_observer.read_text(encoding='utf8'));startup_observer.on('message',receive);startup_observer.load()
  if a.item_test and login_hooks_ready and startup_artifact is None:
   from artifact_restore_source import bridge_source as artifact_source
   startup_artifact=session.create_script(artifact_source(snapshot));startup_artifact.on('message',receive);startup_artifact.load()
   report['local_artifact_scene_restore']=True
   (run/'client-process.json').write_text(json.dumps(report),encoding='utf8')
  if a.shop_test and login_hooks_ready and startup_shop is None:
   from install_ed_shop_bridge import bridge_source
   startup_shop=session.create_script(bridge_source(snapshot));startup_shop.on('message',receive);startup_shop.load()
   report['local_ed_shop_bridge']=True
   report['deferred_shop_entry']=True
   (run/'client-process.json').write_text(json.dumps(report),encoding='utf8')
  if a.item_test and not a.lightweight_play and login_hooks_ready and startup_inventory is None:
   # Install essential read-only hooks before the first saved-unit response.
   # Extensions can be installed later without missing login insertion evidence.
   src=(BASE/'tools/trace_inventory_readers.js').read_text(encoding='utf8')
   src=src[:src.index("Interceptor.attach(irModule.base.add(0x223b480)")]
   prefixes={r:snapshot[r:r+8].hex() for r in (0x197dad0,0x197e5f0)}
   src=src.replace('__PREFIXES__',json.dumps(prefixes))+'\n'+(BASE/'tools/trace_owned_economy_sync.js').read_text(encoding='utf8').replace('__SYNC_PREFIX__',snapshot[0xc4ddf0:0xc4ddf8].hex())
   src+='\n'+(BASE/'tools/trace_fashion_ack.js').read_text(encoding='utf8').replace('__FASHION_PREFIX__',snapshot[0x234b280:0x234b288].hex())
   src+="\nsend({event:'startup_inventory_observers_ready',timestamp:Date.now(),read_only:true});\n"
   startup_inventory=session.create_script(src);startup_inventory.on('message',receive);startup_inventory.load()
   report['startup_inventory_observers']=True
   report['startup_fashion_ack_observer']=True
   (run/'client-process.json').write_text(json.dumps(report),encoding='utf8')
  if clear_received_at is not None and not a.lightweight_play:
   for delay in (2,5,8,15):
    name=('clear-ui-' if clear_sequence==1 else 'clear-'+str(clear_sequence)+'-ui-')+str(delay)+'.png'
    if time.monotonic()-clear_received_at>=delay and name not in captures:
     captures.add(name)
     try:
      from capture_probe_window import capture
      capture(run,name)
     except Exception as e:report.setdefault('capture_errors',[]).append(str(e))
  if not a.login_probe and not captured and time.monotonic()-start>=45:script.exports_sync.snapshot();dump.flush();captured=True;print('Module snapshot saved.',flush=True)
  if a.login_probe:
   if a.dungeon_probe:
    last_command,command=read_command(run/'skill-command.json',last_command)
    if command is not None:login_script.post({'type':'updated_probe_command','payload':command})
    # Same owned early-attached session: diagnostic extension without another
    # attach or restarting a long resource load. Only our run-local file is read.
    path=run/'probe-extension.js'
    if path.exists() and path.stat().st_mtime_ns!=extension_stamp:
     extension_stamp=path.stat().st_mtime_ns
     try:
      if extension is None:
       from owned_extension import OwnedExtension
       def extension_report(kind,error):
        log.write(json.dumps({'type':kind,'error':error})+'\n');log.flush()
       extension=OwnedExtension(session,receive,extension_report)
      extension.load(path.read_text(encoding='utf8'))
      log.write(json.dumps({'type':'extension_loaded','stamp':extension_stamp})+'\n');log.flush()
     except Exception as e:log.write(json.dumps({'type':'extension_error','error':str(e)})+'\n');log.flush()
   if a.dungeon_probe and not a.play and not a.no_auto_entry and not dungeon_queued:
    text=(run/'server-console.jsonl').read_text(encoding='utf8')
    if '"after": "town_ready"' in text:
     town_ready_time=town_ready_time or time.monotonic()
     if time.monotonic()-town_ready_time>=12:
      login_script.post({'type':'updated_probe_command','payload':{'op':'dungeon_enter'}});dungeon_queued=True
   for t in (() if a.lightweight_play else (60,90,120,160,220)):
    if time.monotonic()-start>=t and t not in captures:
     captures.add(t)
     try:
      from capture_probe_window import capture
      capture(run,f'client-window-{t}.png')
     except Exception as e:report.setdefault('capture_errors',[]).append(str(e))
  time.sleep(.25)
 if a.allow_client_variants and not login_hooks_ready:
  print('ELS_LAUNCH_ERROR: 游戏在联机接口准备完成前退出，请将 game-launch.log 发给房主。',flush=True)
  raise RuntimeError('Client exited before native interface verification completed')
 report['snapshot_captured']=captured;report['exit_before_cleanup']=proc.poll();report['elapsed_seconds']=round(time.monotonic()-start,3)
finally:
 if remote_stop_file is not None:
  if 'exit_before_cleanup' not in report:report['exit_before_cleanup']=proc.poll()
  _owned_signal_bridge_stop(remote_stop_file,BASE,report)
 if proc.poll() is None:proc.terminate()
 proc.wait(timeout=10)
 if session:
  try:session.detach()
  except Exception:pass
 if server:
  (run/'server.stop').write_text('owned probe ended')
  try:server.wait(timeout=45 if a.server_config else 10)
  except subprocess.TimeoutExpired:server.terminate();server.wait(timeout=5)
  serverlog.close()
 log.close();dump.close();report['snapshot_sha256']=hashlib.sha256(dump_path.read_bytes()).hexdigest();report['file_sha256_after']=hashlib.sha256(client.read_bytes()).hexdigest()
 (run/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 if not a.login_probe:(out/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 print(json.dumps(report),flush=True)
