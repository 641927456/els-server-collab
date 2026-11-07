"""Own host: retain the exact original cleanup prefix and empty-buffer path."""
from pathlib import Path
import hashlib,json,subprocess,sys,threading
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H.parent/'repair-v9/candidate/tools/pylibs'));import frida
image=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
ranges=[(0x3b7d570,0x3b7d5a8),(0x3b7d620,0x3b7d633),(0x16fa20,0x16fa33),(0x1527c0,0x15281f)]
data={str(lo):list(image[lo:hi])for lo,hi in ranges};source=(H/'native_crypto_lock.js').read_text('utf-8')
setup='const bytes='+json.dumps(data)+';const base=Memory.alloc(0x4000000);const pages=new Set();for(const[r,chunk]of Object.entries(bytes)){const p=base.add(+r);p.writeByteArray(chunk);pages.add(p.sub(p.toUInt32()%Process.pageSize).toString());}for(const p of pages)Memory.protect(ptr(p),Process.pageSize,"r-x");const cpp=Module.load('+json.dumps(str(H/'crypto_eh_fixture.dll'))+');const fakeModule={base:{add(r){return r===0x3b7d860?cpp.getExportByName("fixture_encrypt"):base.add(r);}}};'
tail='''
const ctl=installElsNativeCryptoLock(fakeModule),ctx=Memory.alloc(64);
new NativeFunction(base.add(0x3b7d570),'pointer',['pointer','uint16'],{exceptions:'propagate'})(ctx,0x1234);
if(ctx.add(0x28).readU64().toString()!=='15')throw Error('Fixture must keep the original empty-inline-buffer path');
new NativeFunction(base.add(0x3b7d620),'void',['pointer'],{exceptions:'propagate'})(ctx);
rpc.exports={result(){return{cleanup_prefix_relocated:true,original_tail_chain_returned:true,string_length:ctx.add(0x20).readU64().toString(),string_capacity:ctx.add(0x28).readU64().toString(),lock_recursion:ctl.lock.add(12).readU32(),stats:ctl.stats(),cleanup_function_bytes:19};}};
'''
proc=None;session=None;timer=None;result={};errors=[]
try:
 proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(50)'],creationflags=0x08000000);session=frida.attach(proc.pid)
 script=session.create_script(setup+'\n'+source+'\n'+tail);script.on('message',lambda m,d:errors.append(m)if m.get('type')=='error'else None)
 timer=threading.Timer(15,proc.terminate);timer.start();script.load();result=script.exports_sync.result();timer.cancel()
 assert not errors and result['string_length']=='0'and result['string_capacity']=='15'and result['lock_recursion']==0 and not any(result['stats'].values()),(result,errors)
 result.update(ok=True,owned_host_only=True,actual_game=False,production_modified=False,image_sha256=hashlib.sha256(image).hexdigest(),prototype_sha256=hashlib.sha256(source.encode()).hexdigest(),original_entry_sha256=hashlib.sha256(image[0x3b7d620:0x3b7d633]).hexdigest(),scope='Original empty-string path; allocator/free branches are not executed')
except BaseException as error:result.update(ok=False,error=str(error),Frida_errors=errors);raise
finally:
 if timer:timer.cancel()
 if proc:proc.terminate();proc.wait(timeout=8)
 if session:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'original-cleanup-entry-host.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
