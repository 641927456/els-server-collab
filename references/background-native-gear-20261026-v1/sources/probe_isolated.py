"""Run the formal native probe on a private desktop; never send OS input."""
from pathlib import Path
import ctypes,hashlib,json,os,subprocess,sys,time,traceback,uuid
N=Path(__file__).resolve().parent;settings=json.loads((N/'settings.json').read_bytes());R=Path('G:/els');runtime=Path(settings['runtime']);client=Path(settings['client']);out=N/'native-log';out.mkdir(exist_ok=True)
sys.dont_write_bytecode=True;sys.path[:0]=[str(runtime/'tools'),str(runtime),str(R/'tools/pylibs'),str(R/'analysis/local-activities-20261017-v95/research/job-background-v1')]
import psutil,frida
from job_api_capture import create_job,job_limits,job_pids,K,U,check,object_name,input_desktop,spawn,exit_code,close_process
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
receipt=dict(physical_input_actions=0,desktop_switched=False,new_SDK_overrides=0,client_copied=False,native_snapshot_copied=False,existing_processes_attached=False)
original_popen=subprocess.Popen;original_attach=frida.attach;owner=None;desktop=None;job=None;session=None;guard=None
def save():
 (N/'isolation-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,default=str),'utf8')
class OwnedProcess:
 def __init__(self,args,**kwargs):
  global owner
  assert owner is None and Path(args[0]).resolve()==client.resolve()and len(args)==2
  self.pi=spawn(args,'WinSta0\\'+receipt['desktop'],client.parent,suspended=True);self.pid=self.pi.pid
  check(K.AssignProcessToJobObject(job,self.pi.hProcess));assert job_pids(job)['pids']==[self.pid]
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
 raise RuntimeError('Unexpected child launch from the diagnostic probe')
def attach(pid,*a,**kw):
 global session,guard
 assert owner is not None and pid==owner.pid and pid in job_pids(job)['pids']
 session=original_attach(pid,*a,**kw)
 guard=session.create_script("\nconst u=Process.getModuleByName('user32.dll'),keep=[],counts={},deniedAddresses=new Set();\nfunction deny(name,ret,args,value){const p=u.findExportByName(name);if(!p||deniedAddresses.has(p.toString()))return;deniedAddresses.add(p.toString());const cb=new NativeCallback(function(){counts[name]=(counts[name]||0)+1;return value;},ret,args);keep.push(cb);Interceptor.replace(p,cb);}\ndeny('SendInput','uint',['uint','pointer','int'],0);deny('keybd_event','void',['uint8','uint8','uint32','pointer']);deny('mouse_event','void',['uint32','uint32','uint32','uint32','pointer']);\nfor(const n of ['SetCursorPos','SetPhysicalCursorPos'])deny(n,'int',['int','int'],0);\nfor(const n of ['SetForegroundWindow','BringWindowToTop','SwitchDesktop','SetThreadDesktop','ClipCursor','BlockInput'])deny(n,'int',['pointer'],0);\nfor(const n of ['SetFocus','SetActiveWindow','SetCapture'])deny(n,'pointer',['pointer'],ptr(0));\ndeny('SwitchToThisWindow','void',['pointer','int']);\nfor(const n of ['ChangeDisplaySettingsW','ChangeDisplaySettingsA'])deny(n,'long',['pointer','uint'],-1);\nfor(const n of ['ChangeDisplaySettingsExW','ChangeDisplaySettingsExA'])deny(n,'long',['pointer','pointer','pointer','uint','pointer'],-1);\nconst winpid=new NativeFunction(u.getExportByName('GetWindowThreadProcessId'),'uint',['pointer','pointer']),parent=new NativeFunction(u.getExportByName('GetParent'),'pointer',['pointer']);\nfunction owned(p){if(p.isNull())return false;const id=Memory.alloc(4);winpid(p,id);return id.readU32()===Process.id;}\nfor(const n of ['CreateWindowExW','CreateWindowExA'])Interceptor.attach(u.getExportByName(n),{onEnter(a){if(!(a[3].toUInt32()&0x40000000)){a[0]=ptr(a[0].toUInt32()|0x08000080);a[3]=ptr(a[3].toUInt32()&~0x21000000);a[4]=ptr(-30000);a[5]=ptr(-30000);}},onLeave(r){if(!r.isNull())send({event:'owned_window_created',hwnd:r.toString(),owned:owned(r)});}});\nfor(const n of ['ShowWindow','ShowWindowAsync'])Interceptor.attach(u.getExportByName(n),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}if(!parent(a[0]).isNull())return;if(a[1].toInt32()!==0)a[1]=ptr(4);}});\nInterceptor.attach(u.getExportByName('SetWindowPos'),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}a[6]=ptr(a[6].toUInt32()|0x10);if(parent(a[0]).isNull()){a[1]=ptr(1);a[2]=ptr(-30000);a[3]=ptr(-30000);}}});\nInterceptor.attach(u.getExportByName('MoveWindow'),{onEnter(a){if(!owned(a[0])){a[0]=ptr(0);return;}if(parent(a[0]).isNull()){a[1]=ptr(-30000);a[2]=ptr(-30000);}}});\nfor(const n of ['SetWindowPlacement','ShowOwnedPopups'])deny(n,'int',['pointer','pointer'],0);\n\nconst childDesktop=__CHILD_DESKTOP__,k=Process.getModuleByName('kernel32.dll');\nfor(const n of ['CreateProcessW','CreateProcessA'])Interceptor.attach(k.getExportByName(n),{onEnter(a){const si=a[8],size=si.readU32();if(size<104||size>512)throw Error('Owned child startup structure bound');this.copy=Memory.alloc(size);this.copy.writeByteArray(si.readByteArray(size));this.desktop=n.endsWith('W')?Memory.allocUtf16String(childDesktop):Memory.allocUtf8String(childDesktop);this.copy.add(16).writePointer(this.desktop);this.copy.add(60).writeU32(this.copy.add(60).readU32()|1);this.copy.add(64).writeU16(0);a[8]=this.copy;this.pi=a[9];try{this.app=a[0].isNull()?null:(n.endsWith('W')?a[0].readUtf16String():a[0].readUtf8String());}catch(e){this.app='unreadable';}},onLeave(r){send({event:'owned_child_native_creation',api:n,success:!!r.toInt32(),pid:r.toInt32()?this.pi.add(16).readU32():null,desktop:childDesktop,application:this.app,original_success_and_handles_retained:true});}});\nrpc.exports={status(){return {counts,physical_input_sent:0,focus_and_cursor_calls_blocked:true,offscreen_noactivate:true,installation_complete:true};}};\n".replace('__CHILD_DESKTOP__',json.dumps('WinSta0\\'+receipt['child_desktop'])));guard.on('message',lambda message,data: (N/'window-isolation-events.jsonl').open('a',encoding='utf8').write(json.dumps(message)+'\n'));guard.load();receipt['guard_startup_selftest']=guard.exports_sync.status();assert receipt['guard_startup_selftest']['installation_complete'] and receipt['guard_startup_selftest']['physical_input_sent']==0;receipt['offscreen_noactivate_isolation']=True;receipt['user32_API_replacement']='input/focus denial and window isolation only';save()
 image=(runtime/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes();prefix=image[0x780440:0x780450].hex()
 observer=session.create_script(r"""const m=Process.getModuleByName('x2_dx11.exe'),prefix=__PREFIX__;let tries=0;
const t=setInterval(()=>{if(++tries>6000){clearInterval(t);return;}const p=m.base.add(0x780440);if(Array.from(new Uint8Array(p.readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')!==prefix)return;clearInterval(t);Interceptor.attach(p,{onEnter(a){if(!this.returnAddress.equals(m.base.add(0x3f5467)))return;try{const bp=this.context.rbp,descriptor=bp.add(0x8c0),data=descriptor.add(0x30).readPointer(),compressed=descriptor.add(0x3c).readU32();send({event:'readonly_model_failure_detail',timestamp:Date.now(),name:this.context.rdi.readUtf16String(256).split('\0')[0],hresult:this.context.r14.toUInt32(),hresult_hex:'0x'+this.context.r14.toUInt32().toString(16),size:descriptor.add(0x28).readU32(),compressed_size:compressed,algorithm:descriptor.add(0x44).readU32(),key:descriptor.add(0x40).readU32(),post_transform_prefix:data.isNull()||compressed<32?null:Array.from(new Uint8Array(data.readByteArray(32)),x=>x.toString(16).padStart(2,'0')).join(''),read_only:true});}catch(e){send({event:'model_failure_probe_error',error:String(e)});}}});send({event:'model_failure_detail_observer_ready'});},25);""".replace('__PREFIX__',json.dumps(prefix)))
 def observed(message,data):
  if message.get('type')=='send':message['payload']['client_phase']='cold'if(N/'primary-acceptance.json').exists()else'primary'
  with (N/'model-failure-detail.jsonl').open('a',encoding='utf8')as stream:stream.write(json.dumps(message,ensure_ascii=False)+'\n')
 observer.on('message',observed);observer.load()

 render=session.create_script("\nconst done=new Set();function emit(x){send({event:'owned_d3d9_windowed',...x});}\nfunction factory(p,ex){if(p.isNull())return;for(const slot of ex?[16,20]:[16]){const f=p.readPointer().add(slot*8).readPointer(),key=f.toString();if(done.has(key))continue;done.add(key);Interceptor.attach(f,{onEnter(a){this.out=a[slot===20?7:6];const pp=a[5];this.before={windowed:pp.add(40).readU32(),width:pp.readU32(),height:pp.add(4).readU32(),window:pp.add(32).readPointer().toString(),adapter:a[1].toUInt32(),type:a[2].toUInt32(),flags:a[4].toUInt32(),slot};const u=Process.getModuleByName('user32.dll'),rect=Memory.alloc(16);new NativeFunction(u.getExportByName('GetClientRect'),'int',['pointer','pointer'])(pp.add(32).readPointer(),rect);emit({phase:'client_rect',rect:[0,4,8,12].map(o=>rect.add(o).readS32())});emit({phase:'create_enter',...this.before,changed:!this.before.windowed});},onLeave(r){emit({phase:'create_return',hresult:r.toString(),device:r.toInt32()<0?null:this.out.readPointer().toString(),slot});}});}}\nProcess.attachModuleObserver({onAdded(m){if(m.name.toLowerCase()!=='d3d9.dll')return;for(const name of ['Direct3DCreate9','Direct3DCreate9Ex']){const p=m.findExportByName(name);if(!p)continue;Interceptor.attach(p,{onEnter(a){this.out=name.endsWith('Ex')?a[1]:null;},onLeave(r){if(this.out){if(r.toInt32()>=0)factory(this.out.readPointer(),true);}else factory(r,false);}});}}});\n");render.on('message',observed);render.load()

 meshprefix=image[0x3fb407:0x3fb417].hex()
 meshjs=r"""const m=Process.getModuleByName('x2_dx11.exe'),prefix=__PREFIX__;let n=0;const timer=setInterval(()=>{const p=m.base.add(0x3fb407);if(Array.from(new Uint8Array(p.readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')!==prefix)return;clearInterval(timer);Interceptor.attach(p,{onEnter(){if(++n>20)return;try{const call=m.base.add(0x3eaa2b8).readPointer(),mod=Process.findModuleByAddress(call),app=m.base.add(0x4816400).readPointer();send({event:'native_mesh_create_return',hresult:this.context.rax.toUInt32(),hresult_hex:'0x'+this.context.rax.toUInt32().toString(16),device:app.add(0x10).readPointer().toString(),callee:call.toString(),module:mod?mod.path:null,symbol:DebugSymbol.fromAddress(call).toString(),read_only:true});}catch(e){send({event:'mesh_probe_error',error:String(e)});}}});},25);""".replace('__PREFIX__',json.dumps(meshprefix))
 mesh=session.create_script(meshjs);mesh.on('message',observed);mesh.load()

 logprefix=image[0x164b20:0x164b30].hex()
 logjs=r"""const m=Process.getModuleByName('x2_dx11.exe'),prefix=__PREFIX__;let attempts=0,n=0;const timer=setInterval(()=>{if(++attempts>6000){clearInterval(timer);return;}const p=m.base.add(0x164b20);if(Array.from(new Uint8Array(p.readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')!==prefix)return;clearInterval(timer);Interceptor.attach(p,{onEnter(a){const r=this.returnAddress.sub(m.base).toUInt32();if(r<0x3fb140||r>0x3fb95b||++n>160)return;send({event:'original_model_logger',caller:'0x'+r.toString(16),code:a[1].toUInt32(),read_only:true});}});},25);""".replace('__PREFIX__',json.dumps(logprefix))
 logger=session.create_script(logjs);logger.on('message',observed);logger.load()

 stages=[]
 for rva in (0x3f2cda,0x3f423e):
  prefix=image[rva:rva+16].hex()
  js=r"""const m=Process.getModuleByName('x2_dx11.exe'),rva=__RVA__,prefix=__PREFIX__;let n=0,attempts=0;
const timer=setInterval(()=>{if(++attempts>6000){clearInterval(timer);return;}const p=m.base.add(rva);if(Array.from(new Uint8Array(p.readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')!==prefix)return;clearInterval(timer);Interceptor.attach(p,{onEnter(){if(++n>24)return;try{const bp=this.context.rbp;send({event:'model_native_stage',rva:rva,result:this.context.rax.toUInt32(),result_hex:'0x'+this.context.rax.toUInt32().toString(16),name:bp.sub(0x80).readPointer().readUtf16String(),data_prefix:Array.from(new Uint8Array(this.context.rdi.readByteArray(32)),x=>x.toString(16).padStart(2,'0')).join(''),size:bp.add(0x8e8).readU32(),read_only:true});}catch(e){send({event:'model_stage_probe_error',rva:rva,error:String(e)});}}});},25);""".replace('__RVA__',str(rva)).replace('__PREFIX__',json.dumps(prefix))
  stage=session.create_script(js);stage.on('message',observed);stage.load();stages.append(stage)

 assert input_desktop()==receipt['input_desktop_before'];check(K.ResumeThread(owner.pi.hThread)!=0xffffffff)
 return session
try:
 assert not any((p.info['name']or'').lower()in('x2.exe','x2_dx11.exe')for p in psutil.process_iter(['name']))
 assert sha(client)==settings['client_sha256']
 receipt['input_desktop_before']=input_desktop();assert receipt['input_desktop_before'].lower()=='default'
 receipt['desktop']='Default';receipt['background_rendering_desktop']='Default';receipt['never_activate_or_send_input']=True
 receipt['child_desktop']='ELS_QA_CHILD_'+uuid.uuid4().hex[:16];desktop=check(U.CreateDesktopW(receipt['child_desktop'],None,None,0,0x1ff,None));assert object_name(desktop)==receipt['child_desktop']
 job=create_job('ELS-Gear-private-'+uuid.uuid4().hex);ui=ctypes.c_ulong(0xde);check(K.SetInformationJobObject(job,4,ctypes.byref(ui),4));receipt['job_limits']=job_limits(job);assert receipt['job_limits']['ui_flags']==0xde
 assert input_desktop()==receipt['input_desktop_before'];save()
 subprocess.Popen=popen;frida.attach=attach
 probe=runtime/'tools/probe_updated_client.py';source=probe.read_text('utf8');assert sha(probe)==settings['formal_probe_sha256']
 before="out=BASE/'analysis'/('client-'+digest[:8]);out.mkdir(exist_ok=True)";after="out=Path("+repr(str(out))+");out.mkdir(exist_ok=True)"
 assert source.count(before)==1;changed=source.replace(before,after)
 before_loop='while proc.poll() is None and (a.play or a.until_stopped or time.monotonic()-start<a.seconds)'
 after_loop='while proc.poll() is None and time.monotonic()-start<280 and (a.play or a.until_stopped or time.monotonic()-start<a.seconds)'
 assert changed.count(before_loop)==1;changed=changed.replace(before_loop,after_loop)
 assert changed.replace(after_loop,before_loop).replace(after,before)==source
 receipt.update(formal_probe_sha256=sha(probe),probe_changes=['diagnostic output directory','280 second bounded lifetime'],whole_source_inverse=True)
 save();sys.argv=[str(probe),*settings['probe_args']]
 exec(compile(changed,str(probe),'exec'),{'__name__':'__main__','__file__':str(probe)})
except BaseException:
 receipt['error']=traceback.format_exc();raise
finally:
 subprocess.Popen=original_popen;frida.attach=original_attach
 if guard:
  try:receipt['guard']=guard.exports_sync.status()
  except Exception as error:receipt['guard_closed']=type(error).__name__
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
