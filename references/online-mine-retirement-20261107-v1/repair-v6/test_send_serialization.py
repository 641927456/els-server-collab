"""Own child host only: unchanged native counter bytes and Frida C callbacks.

The host exposes a synthetic encrypt/enqueue scheduling fixture, not the game.
No player process is enumerated or attached to.
"""
from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,traceback
R=Path('G:/els');H=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tools/pylibs'))
import frida
spec=importlib.util.spec_from_file_location('send_candidate',H/'candidate/tools/native_send_serialization.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
image=(R/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes();source=s.source(image,s.EXE_SHA)
for raw,sha in[(image,'0'*64),(b'wrong',s.EXE_SHA)]:
 try:s.source(raw,sha)
 except ValueError:pass
 else:raise AssertionError('Wrong client must refuse before attachment')

SETUP=r'''
const k=Process.getModuleByName('kernel32.dll'),exports={};
for(const n of ['Sleep','CreateThread','WaitForSingleObject','CloseHandle','InitializeCriticalSection','EnterCriticalSection','LeaveCriticalSection'])exports[n]=k.getExportByName(n);
const base=Memory.alloc(0x3c00000),lock=Memory.alloc(40),state=Memory.alloc(4),out=Memory.alloc(20000*4),count=Memory.alloc(4);
for(const [r,h]of Object.entries(PINS))base.add(+r).writeByteArray(h.match(/../g).map(v=>parseInt(v,16)));
const getter=Memory.alloc(Process.pageSize),increment=Memory.alloc(Process.pageSize);
getter.writeByteArray([0x8b,0x01,0xc3]);increment.writeByteArray([0xff,0x01,0xc3]);
// Copy the exact original instructions; provide the corresponding SAS+0x50.
getter.writeByteArray(GETTER);increment.writeByteArray(INCREMENT);
Memory.protect(getter,Process.pageSize,'r-x');Memory.protect(increment,Process.pageSize,'r-x');
const sas=Memory.alloc(0x60),stateCounter=sas.add(0x50);
const fixture=new CModule(`
 extern void Sleep(unsigned int);
 extern void *CreateThread(void *, unsigned long long, void *, void *, unsigned int, void *);
 extern unsigned int WaitForSingleObject(void *,unsigned int);
 extern int CloseHandle(void *);
 extern void InitializeCriticalSection(void *);
 extern void EnterCriticalSection(void *);
 extern void LeaveCriticalSection(void *);
 extern unsigned int native_get(void *);
 extern void native_inc(void *);
 extern unsigned char sas[], queue_lock[];
 extern unsigned int output[], used;
 extern void wrapped_send(void *,void *);
 void sender(void *owner,void *nested) {
   if(nested) wrapped_send(owner,0);
   unsigned int value=native_get(sas);
   Sleep(1);
   native_inc(sas);
   EnterCriticalSection(queue_lock);
   output[used++]=value;
   LeaveCriticalSection(queue_lock);
 }
 unsigned int worker(void *id) {
   for(unsigned int i=0;i<80;i++)wrapped_send(id,(i==0)?id:0);
   return 0;
 }
 int run(void) {
   void *threads[8];
   for(unsigned int i=0;i<8;i++)threads[i]=CreateThread(0,0,worker,(void *)(unsigned long long)(i+1),0,0);
   for(unsigned int i=0;i<8;i++) { if(!threads[i] || WaitForSingleObject(threads[i],15000)!=0)return 0; CloseHandle(threads[i]); }
   return 1;
 }
`,{...exports,native_get:getter,native_inc:increment,sas,queue_lock:lock,output:out,used:count,wrapped_send:base.add(0x682d80)});
new NativeFunction(exports.InitializeCriticalSection,'void',['pointer'])(lock);
const target=base.add(0x682d80);
target.writeByteArray([0x48,0xb8,...Array.from(new Uint8Array(Memory.alloc(8).writePointer(fixture.sender).readByteArray(8))),0xff,0xe0]);
Memory.protect(target.sub(target.toUInt32()%Process.pageSize),Process.pageSize,'r-x');
const hostProcess={getModuleByName(name){return name==='x2_dx11.exe'?{base}:Process.getModuleByName(name);}};
const run=new NativeFunction(fixture.run,'int',[],{exceptions:'propagate'});
function sample(){stateCounter.writeU32(1);count.writeU32(0);if(run()!==1)throw Error('Host worker failed');const n=count.readU32(),values=[];for(let i=0;i<n;i++)values.push(out.add(i*4).readU32());return {n,duplicates:n-new Set(values).size,ordered:values.every((v,i)=>v===i+1),final:stateCounter.readU32()};}
const baseline=sample();
'''
pins={r:image[r:r+n].hex()for r,n in {0x682da0:16,0x683104:5,0x68318c:5,0x3b7d860:16,0x1271e60:4,0x3b817b0:4,0x6875a0:16}.items()}
setup=SETUP.replace('PINS',json.dumps(pins)).replace('GETTER',json.dumps(list(image[0x1271e60:0x1271e64]))).replace('INCREMENT',json.dumps(list(image[0x3b817b0:0x3b817b4])))
TAIL=r'''
const install=prepareElsNativeSendSerialization(),controller=install();
if(controller!==install()||!controller.active())throw Error('Duplicate install');
// Same entry also has JS observers in the actual signed CP support.
let observed=0;const observer=Interceptor.attach(target,{onEnter(){observed++;},onLeave(){}});
Interceptor.flush();
const fixed=sample();observer.detach();
if(!baseline.duplicates||fixed.duplicates||!fixed.ordered||fixed.final!==fixed.n+1||observed!==fixed.n)throw Error(JSON.stringify({baseline,fixed,observed}));
rpc.exports={result(){return {ok:true,baseline,fixed,observed,repeated_install_same:true,nested_send:true,JS_observer_coexistence:true,host_only:true,natural_game:false,production_modified:false};}};
'''
process=None;session=None;script=None;result={'ok':False}
try:
 process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'],creationflags=0x08000000)
 session=frida.attach(process.pid);script=session.create_script(setup+'\n((Process)=>{\n'+source+'\n'+TAIL+'\n})(hostProcess);')
 errors=[];script.on('message',lambda message,data:errors.append(message)if message.get('type')=='error'else None)
 script.load();assert not errors,errors
 result=script.exports_sync.result();result.update(source_sha256=hashlib.sha256(source.encode()).hexdigest(),frida_version=frida.__version__)
except BaseException:
 result={'ok':False,'error':traceback.format_exc()};raise
finally:
 # Only our own child is stopped; no live game process or online connection.
 if process is not None:process.terminate();process.wait(timeout=5)
 if session is not None:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'send-serialization-host.json').write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
