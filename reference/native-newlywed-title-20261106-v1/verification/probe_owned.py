"""Run the formal native probe on a private desktop; never send OS input."""
from pathlib import Path
import ctypes,hashlib,json,os,subprocess,sys,time,traceback,uuid
N=Path(__file__).resolve().parent;settings=json.loads((N/'settings.json').read_bytes());R=Path('G:/els');runtime=Path(settings['runtime']);client=Path(settings['client']);out=N/'native-log';out.mkdir(exist_ok=True)
sys.dont_write_bytecode=True;sys.path[:0]=[str(runtime/'tools'),str(runtime),str(R/'tools/pylibs'),str(R/'analysis/local-activities-20261017-v95/research/job-background-v1')]
import psutil,frida
from job_api_capture import create_job,job_limits,job_pids,K,U,check,object_name,input_desktop,spawn,exit_code,close_process
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=dict(physical_input_actions=0,desktop_switched=False,new_SDK_overrides=0,client_copied=False,native_snapshot_copied=False,existing_processes_attached=False)
original_popen=subprocess.Popen;original_attach=frida.attach;owner=None;desktop=None;job=None;session=None;guard=None;server_pids=[]
def save():
 (N/'isolation-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str),'utf8')
class OwnedProcess:
 def __init__(self,args,**kwargs):
  global owner
  assert owner is None and Path(args[0]).resolve()==client.resolve()and len(args)==2
  self.pi=spawn(args,'WinSta0\\'+receipt['desktop'],client.parent,suspended=True);self.pid=self.pi.pid
  check(K.AssignProcessToJobObject(job,self.pi.hProcess));owner=self
  members=job_pids(job);helpers=[]
  assert self.pid in members['pids']and all(pid in members['pids']for pid in server_pids)
  for pid in members['pids']:
   if pid==self.pid or pid in server_pids:continue
   helper=psutil.Process(pid);parents={p.pid for p in helper.parents()}
   receipt['own_server_child_check']=dict(pid=pid,parents=sorted(parents),expected_parent_pids=list(server_pids),exe=helper.exe());save()
   assert parents.intersection(server_pids),'Unexpected own Job child ancestry'
   helpers.append(dict(pid=pid,parent=helper.ppid(),created=helper.create_time(),exe=helper.exe()))
  receipt['job_membership_at_game_birth']=dict(server_pids=list(server_pids),server_helpers=helpers,client_pid=self.pid,actual=members,client_exit_code=exit_code(self.pi));save()
  # The native GUI thread attaches its explicit desktop during initialization.
  owner=self;receipt.update(client_pid=self.pid,client_created=psutil.Process(self.pid).create_time(),client_exe=str(client),created_suspended=True,client_desktop_explicit_in_CreateProcess=True)
  save()
 def poll(self):
  return None if exit_code(self.pi)==259 else exit_code(self.pi)
 def wait(self,timeout=None):
  end=time.monotonic()+(timeout if timeout is not None else 300)
  while self.poll()is None:
   if time.monotonic()>end:raise subprocess.TimeoutExpired('owned isolated client',timeout)
   time.sleep(.1)
  return self.poll()
 def terminate(self):
  assert Path(psutil.Process(self.pid).exe()).resolve()==client.resolve()
  assert abs(psutil.Process(self.pid).create_time()-receipt['client_created'])<.001
  check(K.TerminateProcess(self.pi.hProcess,0))
def popen(args,*a,**kw):
 if args and Path(str(args[0])).resolve()==client.resolve():return OwnedProcess(args,**kw)
 if args[:3]==[sys.executable,'-m','els_server']:
  assert '--config'in args and Path(args[args.index('--config')+1]).resolve()==N/'server.toml'
  kw['creationflags']=subprocess.CREATE_NO_WINDOW|0x00000004
  p=original_popen(args,*a,**kw);check(K.AssignProcessToJobObject(job,ctypes.c_void_p(int(p._handle))));server_pids.append(p.pid)
  nt=ctypes.WinDLL('ntdll');nt.NtResumeProcess.argtypes=[ctypes.c_void_p];nt.NtResumeProcess.restype=ctypes.c_long
  assert nt.NtResumeProcess(ctypes.c_void_p(int(p._handle)))==0
  return p
 raise RuntimeError('Unexpected child launch from the diagnostic probe')
def attach(pid,*a,**kw):
 global session,guard
 assert owner is not None and pid==owner.pid and pid in job_pids(job)['pids']
 session=original_attach(pid,*a,**kw)
 guard=session.create_script("\nconst u=Process.getModuleByName('user32.dll'),keep=[],counts={},deniedAddresses=new Set();\nfunction deny(name,ret,args,value){const p=u.findExportByName(name);if(!p||deniedAddresses.has(p.toString()))return;deniedAddresses.add(p.toString());const cb=new NativeCallback(function(){counts[name]=(counts[name]||0)+1;return value;},ret,args);keep.push(cb);Interceptor.replace(p,cb);}\ndeny('SendInput','uint',['uint','pointer','int'],0);deny('keybd_event','void',['uint8','uint8','uint32','pointer']);deny('mouse_event','void',['uint32','uint32','uint32','uint32','pointer']);\nfor(const n of ['SetCursorPos','SetPhysicalCursorPos'])deny(n,'int',['int','int'],0);\nfor(const n of ['SetForegroundWindow','BringWindowToTop','SwitchDesktop','SetThreadDesktop','ClipCursor','BlockInput'])deny(n,'int',['pointer'],0);\nfor(const n of ['SetFocus','SetActiveWindow','SetCapture'])deny(n,'pointer',['pointer'],ptr(0));\ndeny('SwitchToThisWindow','void',['pointer','int']);\nfor(const n of ['ChangeDisplaySettingsW','ChangeDisplaySettingsA'])deny(n,'long',['pointer','uint'],-1);\nfor(const n of ['ChangeDisplaySettingsExW','ChangeDisplaySettingsExA'])deny(n,'long',['pointer','pointer','pointer','uint','pointer'],-1);\nconst winpid=new NativeFunction(u.getExportByName('GetWindowThreadProcessId'),'uint',['pointer','pointer']),parent=new NativeFunction(u.getExportByName('GetParent'),'pointer',['pointer']);\nfunction owned(p){if(p.isNull())return false;const id=Memory.alloc(4);winpid(p,id);return id.readU32()===Process.id;}\nfor(const n of ['CreateWindowExW','CreateWindowExA'])Interceptor.attach(u.getExportByName(n),{onEnter(a){if(!(a[3].toUInt32()&0x40000000)){a[0]=ptr(a[0].toUInt32()|0x08000080);a[3]=ptr(a[3].toUInt32()&~0x21000000);a[4]=ptr(-30000);a[5]=ptr(-30000);}},onLeave(r){if(!r.isNull())send({event:'owned_window_created',hwnd:r.toString(),owned:owned(r)});}});\nfor(const n of ['ShowWindow','ShowWindowAsync'])Interceptor.attach(u.getExportByName(n),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}if(!parent(a[0]).isNull())return;if(a[1].toInt32()!==0)a[1]=ptr(4);}});\nInterceptor.attach(u.getExportByName('SetWindowPos'),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}a[6]=ptr(a[6].toUInt32()|0x10);if(parent(a[0]).isNull()){a[1]=ptr(1);a[2]=ptr(-30000);a[3]=ptr(-30000);}}});\nInterceptor.attach(u.getExportByName('MoveWindow'),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}if(parent(a[0]).isNull()){a[1]=ptr(-30000);a[2]=ptr(-30000);}}});\nfor(const n of ['SetWindowPlacement','ShowOwnedPopups'])deny(n,'int',['pointer','pointer'],0);\n\nconst childDesktop=__CHILD_DESKTOP__,k=Process.getModuleByName('kernel32.dll');\nfor(const n of ['CreateProcessW','CreateProcessA'])Interceptor.attach(k.getExportByName(n),{onEnter(a){const si=a[8],size=si.readU32();if(size<104||size>512)throw Error('Owned child startup structure bound');this.copy=Memory.alloc(size);this.copy.writeByteArray(si.readByteArray(size));this.desktop=n.endsWith('W')?Memory.allocUtf16String(childDesktop):Memory.allocUtf8String(childDesktop);this.copy.add(16).writePointer(this.desktop);this.copy.add(60).writeU32(this.copy.add(60).readU32()|1);this.copy.add(64).writeU16(0);a[8]=this.copy;this.pi=a[9];try{this.app=a[0].isNull()?null:(n.endsWith('W')?a[0].readUtf16String():a[0].readUtf8String());}catch(e){this.app='unreadable';}},onLeave(r){send({event:'owned_child_native_creation',api:n,success:!!r.toInt32(),pid:r.toInt32()?this.pi.add(16).readU32():null,desktop:childDesktop,application:this.app,original_success_and_handles_retained:true});}});\nrpc.exports={status(){return {counts,physical_input_sent:0,focus_and_cursor_calls_blocked:true,offscreen_noactivate:true,installation_complete:true};}};\n".replace('__CHILD_DESKTOP__',json.dumps('WinSta0\\'+receipt['child_desktop'])));guard.on('message',lambda message,data: (N/'window-isolation-events.jsonl').open('a',encoding='utf8').write(json.dumps(message)+'\n'));guard.load();receipt['guard_startup_selftest']=guard.exports_sync.status();assert receipt['guard_startup_selftest']['installation_complete'] and receipt['guard_startup_selftest']['physical_input_sent']==0;receipt['offscreen_noactivate_isolation']=True;receipt['user32_API_replacement']='input/focus denial and window isolation only';save()
 assert input_desktop()==receipt['input_desktop_before'];check(K.ResumeThread(owner.pi.hThread)!=0xffffffff)
 return session
lock=R/'analysis/coordination-20261015/isolated-game-test.lock';lockfd=None;lockino=None;lockdoc=None
try:
 lockdoc=dict(owner=os.environ.get('CODEX_THREAD_ID','feature-closure-20261105-v1'),pid=os.getpid(),purpose='Owned native periodic item formatter qualification',directory=str(N),token=uuid.uuid4().hex)
 lockfd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(lockfd,json.dumps(lockdoc).encode());os.fsync(lockfd);lockino=lock.stat().st_ino
 assert not any((p.info['name']or'').lower()in('x2.exe','x2_dx11.exe')for p in psutil.process_iter(['name']))
 assert sha(client)==settings['client_sha256']
 import socket
 with socket.socket()as portcheck:portcheck.bind(('127.0.0.1',19400))
 import importlib.util
 spec=importlib.util.spec_from_file_location('native_title_options',N.parents[1]/'test-tools-v1/native_title_options.py');m=importlib.util.module_from_spec(spec);sys.modules['native_title_options']=m;spec.loader.exec_module(m)
 delta=json.loads((N.parents[1]/'composition-check-v1.json').read_bytes())['candidate_pins']
 assert all(sha(N.parents[1]/'test-tools-v1'/Path(rel).name)==value for rel,value in delta.items())
 receipt['candidate_delta_pins']=delta
 for name in ('native_wear_sync','world_event_iteration','guild_native_power','native_cache_sync'):
  spec=importlib.util.spec_from_file_location(name,(N.parents[1]/'test-tools-v1' if name=='native_cache_sync' else runtime/'tools')/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m)
 receipt['actual_runtime_imports']={name:str(sys.modules[name].__file__)for name in ('native_wear_sync','world_event_iteration','guild_native_power','native_cache_sync')};receipt['formal_source_files_changed']=False;receipt['parent_signed_payload']='a33de4e7abdc18f8e35bd2a64e7dba92b76036d710f06354c615778df9c5eb0e';receipt['selected_runtime']='G:/els/analysis/feature-closure-20261105-v1/housing-pets-v1/native-game-v1/runtime';receipt['candidate_signed']=False;receipt['candidate_published']=False;receipt['server_candidate_installed']=False
 receipt['input_desktop_before']=input_desktop();assert receipt['input_desktop_before'].lower()=='default'
 receipt['desktop']='Default';receipt['background_rendering_desktop']='Default';receipt['never_activate_or_send_input']=True
 receipt['child_desktop']='ELS_QA_CHILD_'+uuid.uuid4().hex[:16];desktop=check(U.CreateDesktopW(receipt['child_desktop'],None,None,0,0x1ff,None));assert object_name(desktop)==receipt['child_desktop']
 job=create_job('ELS-Gear-private-'+uuid.uuid4().hex);ui=ctypes.c_ulong(0xde);check(K.SetInformationJobObject(job,4,ctypes.byref(ui),4));receipt['job_limits']=job_limits(job);assert receipt['job_limits']['ui_flags']==0xde
 assert input_desktop()==receipt['input_desktop_before'];save()
 owned_helpers=[]
 def start_owned_helper(args,logname):
  stream=(N/logname).open('w',encoding='utf8')
  p=original_popen(args,cwd=runtime,stdout=stream,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|0x00000004)
  check(K.AssignProcessToJobObject(job,ctypes.c_void_p(int(p._handle))));server_pids.append(p.pid)
  nt=ctypes.WinDLL('ntdll');nt.NtResumeProcess.argtypes=[ctypes.c_void_p];nt.NtResumeProcess.restype=ctypes.c_long
  assert nt.NtResumeProcess(ctypes.c_void_p(int(p._handle)))==0
  owned_helpers.append((p,stream));return p
 backend=start_owned_helper([sys.executable,'-X','utf8','-B',str(N/'server_input.py'),str(N),str(settings['family'])],'server-console.txt')
 deadline=time.monotonic()+40
 while not(N/'server-ready.json').exists():
  assert backend.poll()is None,'Owned fixture server failed; see private local diagnostic'
  assert time.monotonic()<deadline,'Owned fixture server readiness deadline'
  time.sleep(.1)
 launch_owner=psutil.Process(os.getppid())
 bridge=start_owned_helper([sys.executable,'-X','utf8','-B','-m','els_server.friends_bridge','--config',str(N/'private/bridge.json'),'--stop-file',str(Path(settings['remote_stop_file'])),'--owner-pid',str(launch_owner.pid),'--owner-created',repr(launch_owner.create_time())],'bridge-console.txt')
 deadline=time.monotonic()+25
 while 'ELS_BRIDGE_READY'not in(N/'bridge-console.txt').read_text('utf8'):
  assert bridge.poll()is None,'Owned fixture bridge failed; see private local diagnostic'
  assert time.monotonic()<deadline,'Owned fixture bridge readiness deadline'
  time.sleep(.1)
 subprocess.Popen=popen;frida.attach=attach
 probe=runtime/'tools/probe_updated_client.py';source=probe.read_text('utf8');assert sha(probe)==settings['formal_probe_sha256']
 before="out=BASE/'analysis'/('client-'+digest[:8]);out.mkdir(exist_ok=True)";after="out=Path("+repr(str(out))+");out.mkdir(exist_ok=True)"
 assert source.count(before)==1;changed=source.replace(before,after)
 observer='const originalOwnedTitleInstall=installElsGuildNativePower;let ownedTitleInstalled=false;\ninstallElsGuildNativePower=function(){const result=originalOwnedTitleInstall();if(ownedTitleInstalled)return result;ownedTitleInstalled=true;\n(()=>{const m=Process.getModuleByName(\'x2_dx11.exe\'),dir="G:\\\\els\\\\analysis\\\\feature-closure-20261105-v1\\\\wedding-v1\\\\title-display-v6\\\\native-game-v1\\\\candidate-data-v4",scenario=JSON.parse(File.readAllText(dir+\'/server-ready.json\')),pins={"35135184": "48895c2408488974241848897c242055", "11606672": "488bc455535657415441554156415748", "1386256": "40534883ec20488b5118488bd94883fa"},hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,\'0\')).join(\'\');for(const[r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error(\'Owned title formatter guard \'+r);const fn=(r,t,a)=>new NativeFunction(m.base.add(r),t,a),formatTitle=fn(0x2181ed0,\'void\',[\'pointer\',\'pointer\',\'int\']),formatOption=fn(0xb11a90,\'pointer\',[\'pointer\',\'pointer\',\'uint32\',\'uint8\']),destroyString=fn(0x152710,\'void\',[\'pointer\']),alloc=n=>{const p=Memory.alloc(n);p.writeByteArray(new Array(n).fill(0));return p;},text=p=>{const n=p.add(16).readU64().toNumber(),cap=p.add(24).readU64().toNumber();if(n>16000||cap<n)throw Error(\'Title string bound\');return(cap>7?p.readPointer():p).readUtf16String(n);},write=(name,v)=>{const f=new File(dir+\'/\'+name,\'w\');f.write(JSON.stringify(v));f.flush();f.close();};const keep=[];\nfunction find(manager,key){const head=manager.readPointer();let node=head.add(8).readPointer(),best=head,steps=0;while(node.add(25).readU8()===0){if(++steps>64)throw Error(\'Original title/option tree bound\');if(node.add(32).readS32()<key)node=node.add(16).readPointer();else{best=node;node=node.readPointer();}}if(best.equals(head)||best.add(32).readS32()!==key)throw Error(\'Native title/option identity missing \'+key);return best;}\nfunction options(node){const p=node.add(0xe0).readPointer(),end=node.add(0xe8).readPointer(),n=end.sub(p).toInt32()/4;if(!Number.isInteger(n)||n<1||n>30)throw Error(\'Native title option vector bound\');return Array.from({length:n},(_,i)=>p.add(i*4).readS32());}\nfunction label(manager,id){const out=alloc(32);keep.push(out);formatTitle(manager,out,id);const result=text(out);destroyString(out);return result;}\nfunction option(manager,id){const row=find(manager,id).add(40),out=alloc(32);keep.push(out);formatOption(row,out,1,0);const result=text(out);destroyString(out);return result;}\nconst reference=JSON.parse(File.readAllText("G:\\\\els\\\\analysis\\\\feature-closure-20261105-v1\\\\wedding-v1\\\\title-display-v6\\\\native-game-v1\\\\private-vector-v1\\\\native-original-title-text.json"));\nfunction evaluate(engine){const manager=engine.add(0x4d8).readPointer(),optionManager=engine.add(0x4c0).readPointer();if(manager.isNull()||optionManager.isNull()||manager.add(0x30).readPointer().isNull())throw Error(\'Native title manager/UI normal precondition\');const ids=reference.ids,nodes=ids.map(id=>find(manager,id)),before=nodes.map(options),expected=reference.vectors.map((v,i)=>ids[i]===12360?reference.private_newlywed_options:v);if(JSON.stringify(before)!==JSON.stringify(expected))throw Error(\'Candidate live title vector differs from exact approved replacement\');const texts=Object.fromEntries(ids.map(id=>[id,label(manager,id)]));if(JSON.stringify(texts)!==JSON.stringify(reference.after))throw Error(\'Candidate original title formatter output differs\');if(option(optionManager,87018)!==reference.old_drop_option_text||option(optionManager,100003019)!==reference.new_drop_option_text)throw Error(\'Shared native options were modified\');installElsTitleOptionData();installElsTitleOptionData();if(JSON.stringify(nodes.map(options))!==JSON.stringify(before))throw Error(\'Repeated adapter application changed the catalog\');return{ids,vectors:before,native_text:texts,old_shared_option_text:reference.old_drop_option_text,native20_option_text:reference.new_drop_option_text,exactly_one_live_title_reference_changed:true,other_shared10_titles_unchanged:true,duplicate_adapter_calls_no_change:true,original_UI_presence_reused:true};}\nlet first=0,frames=0,done=false,rows=null,last=0;Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(done)return;try{const e=m.base.add(0x4817e70).readPointer();if(e.isNull())return;const cache=e.add(0xc8).readPointer();if(cache.isNull())return;const u=cache.add(0xa0).readPointer();if(u.isNull()||u.add(0x48).readU64().toString()!==String(scenario.uid))return;const state=m.base.add(0x4817e80).readPointer();if(state.isNull()||state.add(0x160).readS32()!==14)return;frames++;if(!first)first=Date.now();if(!rows){rows=evaluate(e);write(\'native-original-title-text.json\',rows);send({event:\'owned_original_title_text\',rows});}if(Date.now()-last>=1000){last=Date.now();send({event:\'owned_title_probe_progress\',frames,seconds:(Date.now()-first)/1000});}if(Date.now()-first>=120000){done=true;const final_rows=evaluate(e);const v={ok:true,frames,seconds:(Date.now()-first)/1000,rows,final_rows,native_Game:true,natural_GUI:false,physical_input_actions:0,production_Hook:false,live_catalog_reference_changes:1,shared_option_writes:0,candidate_signed:false};write(\'native-observer-complete.json\',v);send({event:\'owned_original_title_complete\',frames,seconds:v.seconds});}}catch(error){done=true;write(\'native-observer-failure.json\',{ok:false,error:String(error),stack:String(error.stack)});send({event:\'owned_original_title_failure\',error:String(error)});}}});})();return result;};'
 marker="native_login_template=compose_native_cache(snapshot,digest,(BASE/'tools/trace_dx11_login.js').read_text(encoding='utf8'))"
 assert changed.count(marker)==1
 changed=changed.replace(marker,marker+"\n native_login_template+="+repr(observer))
 before_loop='while proc.poll() is None and (a.play or a.until_stopped or time.monotonic()-start<a.seconds)'
 after_loop='while proc.poll() is None and time.monotonic()-start<300 and (a.play or a.until_stopped or time.monotonic()-start<a.seconds)'
 assert changed.count(before_loop)==1;changed=changed.replace(before_loop,after_loop)
 inventory_before='  if a.item_test and not a.lightweight_play and login_hooks_ready and startup_inventory is None:'
 inventory_after='  if False: # Owned probe omits legacy observers that hook current CP producer entries.'
 assert changed.count(inventory_before)==1
 changed=changed.replace(inventory_before,inventory_after)
 capture_before='   for t in (() if a.lightweight_play else (60,90,120,160,220)):'
 capture_after='   for t in ():'
 assert changed.count(capture_before)==1
 changed=changed.replace(capture_before,capture_after)
 assert changed.replace(capture_after,capture_before).replace(inventory_after,inventory_before).replace(after_loop,before_loop).replace(after,before).replace(marker+"\n native_login_template+="+repr(observer),marker)==source
 receipt.update(formal_probe_sha256=sha(probe),probe_changes=['diagnostic output directory','240 second bounded lifetime','legacy inventory observers and screenshots omitted in owned probe','controlled original native guild requests appended without changing candidate component body'],whole_source_inverse=True)
 save();sys.argv=[str(probe),*settings['probe_args']]
 exec(compile(changed,str(probe),'exec'),{'__name__':'__main__','__file__':str(probe)})
except BaseException:
 receipt['error']=traceback.format_exc();raise
finally:
 subprocess.Popen=original_popen;frida.attach=original_attach
 if guard:
  try:receipt['guard']=guard.exports_sync.status()
  except Exception as error:receipt['guard_closed']=type(error).__name__
 if 'owned_helpers'in globals():
  (N/'server.stop').write_bytes(b'owned qualification ended')
  Path(settings['remote_stop_file']).write_bytes(b'owned qualification ended')
  for helper,stream in owned_helpers:
   try:helper.wait(timeout=20)
   except subprocess.TimeoutExpired:receipt.setdefault('owned_helper_stop_timeout',[]).append(helper.pid)
   stream.close()
 if job:
  receipt['own_job_pids_before_close']=job_pids(job)['pids'];K.CloseHandle(job)
 if owner:
  try:owner.wait(timeout=10)
  except Exception as error:
   receipt['own_wait_error']=type(error).__name__
   if owner.poll()is None:owner.terminate();owner.wait(timeout=10)
  close_process(owner.pi)
 if desktop:check(U.CloseDesktop(desktop));receipt['private_desktop_handle_closed']=True
 receipt['input_desktop_after']=input_desktop();receipt['input_desktop_unchanged']=receipt['input_desktop_after']==receipt.get('input_desktop_before')
 receipt['client_sha256_after']=sha(client);receipt['client_executable_unchanged']=receipt['client_sha256_after']==settings['client_sha256'];save()
 if lockfd is not None:
  assert lock.stat().st_ino==lockino and json.loads(lock.read_bytes())==lockdoc
  os.close(lockfd);lock.unlink()
