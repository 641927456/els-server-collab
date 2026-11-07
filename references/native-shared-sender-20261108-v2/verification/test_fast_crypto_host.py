"""Own hidden host only: real MSVC RAII exceptions across TinyCC wrappers."""
from pathlib import Path
import ast,hashlib,json,subprocess,sys,threading,time
H=Path(__file__).resolve().parent;W=H.parent;sys.dont_write_bytecode=True
sys.path.insert(0,str(W/'repair-v9/candidate/tools/pylibs'));import frida
b=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
t=ast.parse((W/'repair-v6/test_send_serialization.py').read_bytes())
old=next(ast.literal_eval(n.value)for n in t.body if isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id=='SETUP'for v in n.targets))
setup=old.split('const fixture=new CModule(')[0]
setup=setup.replace('PINS','{}').replace('GETTER',json.dumps(list(b[0x1271e60:0x1271e64]))).replace('INCREMENT',json.dumps(list(b[0x3b817b0:0x3b817b4])))
setup+='''
const cpp=Module.load(DLL),sender=cpp.getExportByName('fixture_sender'),encrypt=cpp.getExportByName('fixture_encrypt'),destroy=cpp.getExportByName('fixture_destroy'),field=cpp.getExportByName('fixture_field');
const fixture=new CModule(`
 extern void *CreateThread(void *,unsigned long long,void *,void *,unsigned int,void *);
 extern unsigned int WaitForSingleObject(void *,unsigned int);
 extern int CloseHandle(void *);
 extern void EnterCriticalSection(void *);
 extern void LeaveCriticalSection(void *);
 extern int actual_sender(void *,void *);
 extern void actual_field(void *,void *);
 extern unsigned char queue_lock[];
 extern unsigned int output[],used;
 void enqueue(unsigned int value){EnterCriticalSection(queue_lock);output[used++]=value;LeaveCriticalSection(queue_lock);}
 unsigned int worker(void *owner){for(unsigned int i=0;i<10;i++){actual_sender(owner,0);actual_field(owner,0);}return 0;}
 int run(void){void *threads[8];for(unsigned int i=0;i<8;i++)threads[i]=CreateThread(0,0,worker,(void *)(unsigned long long)(i+1),0,0);for(unsigned int i=0;i<8;i++){if(!threads[i]||WaitForSingleObject(threads[i],15000)!=0)return 0;CloseHandle(threads[i]);}return 1;}
`,{...exports,actual_sender:sender,actual_field:field,queue_lock:lock,output:out,used:count});
new NativeFunction(exports.InitializeCriticalSection,'void',['pointer'])(lock);
new NativeFunction(cpp.getExportByName('fixture_configure'),'void',['pointer','pointer','pointer','pointer','pointer','pointer','pointer'])(sas,getter,increment,exports.Sleep,fixture.enqueue,k.getExportByName('GetLastError'),k.getExportByName('SetLastError'));
const fakeModule={base:{add(rva){if(rva===0x3b7d860)return encrypt;if(rva===0x3b7d620)return destroy;throw Error('Unexpected model RVA');}}};
const run=new NativeFunction(fixture.run,'int',[],{exceptions:'propagate'}),nativeSend=new NativeFunction(sender,'int',['pointer','pointer'],{exceptions:'propagate'});
function reset(){stateCounter.writeU32(1);count.writeU32(0);}
function values(){return Array.from({length:count.readU32()},(_,i)=>out.add(i*4).readU32());}
'''.replace('DLL',json.dumps(str(H/'crypto_eh_fixture.dll')))
source=(H/'native_crypto_lock.js').read_text('utf-8')
tail='''
const ctl=installElsNativeCryptoLock(fakeModule);let enter=0,leave=0,fieldEnter=0,fieldLeave=0,observing=true;
Interceptor.attach(sender,{onEnter(a){this.observing=observing;if(!observing)return;enter++;nativeSend(a[0],ptr(0));},onLeave(){if(this.observing)leave++;}});
Interceptor.attach(field,{onEnter(a){this.observing=observing;if(!observing)return;this.owner=a[0];fieldEnter++;},onLeave(){if(!this.observing)return;nativeSend(this.owner,ptr(0));fieldLeave++;}});
Interceptor.flush();reset();if(run()!==1)throw Error('Native worker timeout');const normal=values(),normalCounter=stateCounter.readU32();observing=false;
const scenarios=[];for(const mode of[1,2,3,4,5]){reset();const result=nativeSend(ptr(1),ptr(mode));scenarios.push({mode,result,values:values(),counter:stateCounter.readU32(),stats:ctl.stats(),lock_recursion:ctl.lock.add(12).readU32()});}
const beforeUnmatched=ctl.stats();new NativeFunction(cpp.getExportByName('fixture_unmatched_destroy'),'void',[],{exceptions:'propagate'})();const afterUnmatched=ctl.stats();
const lastErrorPreserved=new NativeFunction(cpp.getExportByName('fixture_error_probe'),'int',[],{exceptions:'propagate'})()===1;
rpc.exports={result(){return{normal:{n:normal.length,duplicates:normal.length-new Set(normal).size,ordered:normal.every((v,i)=>v===i+1),counter:normalCounter},enter,leave,fieldEnter,fieldLeave,scenarios,beforeUnmatched,afterUnmatched,lastErrorPreserved,stats:ctl.stats(),lock_recursion:ctl.lock.add(12).readU32(),unwind_call_sites:ctl.unwind};}};
'''
proc=None;session=None;result={};errors=[];timer=None
try:
 proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(80)'],creationflags=0x08000000)
 text=setup+'\n'+source+'\n'+tail;(H/'fast-host-last-source.js').write_bytes(text.encode())
 session=frida.attach(proc.pid);script=session.create_script(text);script.on('message',lambda m,d:errors.append(m)if m.get('type')=='error'else None)
 timer=threading.Timer(30,proc.terminate);timer.start();script.load();result=script.exports_sync.result();timer.cancel()
 assert not errors,errors
 assert result['normal']==dict(n=240,duplicates=0,ordered=True,counter=241),result
 assert result['enter']==result['leave']==result['fieldEnter']==result['fieldLeave']==80,result
 assert [s['result']for s in result['scenarios']]==[-1,102,103,104,1],result
 assert all(s['stats']['active']==s['stats']['failed']==s['lock_recursion']==0 for s in result['scenarios']),result
 assert result['beforeUnmatched']==result['afterUnmatched'],result
 assert result['stats']['encryptions']==result['stats']['cleanups']==247 and result['lock_recursion']==0 and result['lastErrorPreserved'],result
 assert result['scenarios'][-1]['values']==[1,2],result
 result.update(ok=True,owned_host_only=True,production_modified=False,actual_game=False,prototype_sha256=hashlib.sha256((H/'native_crypto_lock.js').read_bytes()).hexdigest(),CPP_fixture_sha256=hashlib.sha256((H/'crypto_eh_fixture.dll').read_bytes()).hexdigest(),fixture_source_sha256=hashlib.sha256((H/'crypto_eh_fixture.cpp').read_bytes()).hexdigest(),frida_version=frida.__version__)
except BaseException as error:
 result.update(ok=False,error=str(error),Frida_errors=errors)
 raise
finally:
 if timer:timer.cancel()
 if proc is not None:proc.terminate();proc.wait(timeout=8)
 if session is not None:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'fast-crypto-host.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in result.items()if k!='unwind_call_sites'}))
