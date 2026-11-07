"""Own hidden host: release-only installation failure must not strand waiters."""
from pathlib import Path
import hashlib,json,subprocess,sys,threading
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H.parent/'repair-v9/candidate/tools/pylibs'));import frida
source=(H/'native_crypto_lock.js').read_text('utf-8')
setup="const cpp=Module.load("+json.dumps(str(H/'crypto_eh_fixture.dll'))+");const encrypt=cpp.getExportByName('fixture_encrypt'),destroy=cpp.getExportByName('fixture_destroy');const fakeModule={base:{add(rva){if(rva===0x3b7d860)return encrypt;if(rva===0x3b7d620)return destroy;throw Error('Unexpected model RVA');}}};"
shim="""
const kernel=Process.getModuleByName('kernel32.dll');
const workerCode=new CModule('extern void original_unmatched(void);unsigned int worker(void *unused){original_unmatched();return 0;}',{original_unmatched:cpp.getExportByName('fixture_unmatched_destroy')});
const createThread=new NativeFunction(kernel.getExportByName('CreateThread'),'pointer',['pointer','uint64','pointer','pointer','uint','pointer']);
const waitThread=new NativeFunction(kernel.getExportByName('WaitForSingleObject'),'uint',['pointer','uint']);
const pause=new NativeFunction(kernel.getExportByName('Sleep'),'void',['uint']);let waiter=ptr(0),blockedBeforeSignal=false;
const observedInterceptor={replaceFast(address,replacement){if(address.equals(encrypt)){
 Interceptor.flush();waiter=createThread(ptr(0),0,workerCode.worker,ptr(0),0,ptr(0));if(waiter.isNull())throw Error('Fixture worker creation');
 pause(40);blockedBeforeSignal=waitThread(waiter,0)===0x102;
 throw Error('expected second replacement rejection');
}return Interceptor.replaceFast(address,replacement);}};
"""
tail="""
let failure=null;try{installElsNativeCryptoLock(fakeModule);}catch(error){failure=String(error);}
if(!failure||!failure.includes('expected second replacement rejection'))throw Error('Wrong failure: '+failure);
const life=globalThis.elsNativeCryptoLockLifetime;new NativeFunction(cpp.getExportByName('fixture_unmatched_destroy'),'void',[],{exceptions:'propagate'})();
const waiterFinished=waitThread(waiter,1000)===0;new NativeFunction(kernel.getExportByName('CloseHandle'),'int',['pointer'])(waiter);
const wait=new NativeFunction(Process.getModuleByName('kernel32.dll').getExportByName('WaitForSingleObject'),'uint',['pointer','uint']);
rpc.exports={result(){return{failure,ready_event_signaled:wait(life.event,0)===0,original_cleanup_reference_set:!life.refs.add(8).readPointer().isNull(),original_crypto_reference_unset:life.refs.readPointer().isNull(),destructor_passthrough_completed:true,waiter_blocked_before_finally:blockedBeforeSignal,waiter_completed_after_signal:waiterFinished,lifetime_retained:life.callbacks!==null,installed:life.installed};}};
"""
proc=None;session=None;timer=None;result={};errors=[]
try:
 proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(50)'],creationflags=0x08000000);session=frida.attach(proc.pid)
 text=setup+shim+'\n((Interceptor)=>{'+source+tail+'})(observedInterceptor);';script=session.create_script(text);script.on('message',lambda m,d:errors.append(m)if m.get('type')=='error'else None)
 timer=threading.Timer(15,proc.terminate);timer.start();script.load();result=script.exports_sync.result();timer.cancel()
 assert not errors and all(result[k]for k in ['ready_event_signaled','original_cleanup_reference_set','original_crypto_reference_unset','destructor_passthrough_completed','waiter_blocked_before_finally','waiter_completed_after_signal','lifetime_retained'])and not result['installed'],(result,errors)
 result.update(ok=True,owned_host_only=True,production_modified=False,prototype_sha256=hashlib.sha256((H/'native_crypto_lock.js').read_bytes()).hexdigest())
except BaseException as error:result.update(ok=False,error=str(error),Frida_errors=errors);raise
finally:
 if timer:timer.cancel()
 if proc:proc.terminate();proc.wait(timeout=8)
 if session:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'fast-install-failure.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
