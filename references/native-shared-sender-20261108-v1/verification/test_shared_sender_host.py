"""Own hidden host: two Gum listeners, multiple isolated logical observers."""
from pathlib import Path
import ast,importlib.util,json,subprocess,sys,time
H=Path(__file__).resolve().parent;W=H.parent;C=W/'repair-v9/candidate'
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'tools/pylibs'),str(C/'tools')]
import frida
from native_send_serialization import source,EXE_SHA
b=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
tree=ast.parse((W/'repair-v6/test_send_serialization.py').read_bytes())
setup=next(ast.literal_eval(n.value)for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='SETUP'for t in n.targets))
sizes={0x682da0:16,0x683104:5,0x68318c:5,0x3b7d860:16,0x1271e60:4,0x3b817b0:4,0x6875a0:16}
setup=setup.replace('PINS',json.dumps({r:b[r:r+n].hex()for r,n in sizes.items()})).replace('GETTER',json.dumps(list(b[0x1271e60:0x1271e64]))).replace('INCREMENT',json.dumps(list(b[0x3b817b0:0x3b817b4]))).replace('const baseline=sample();','').replace('i<80','i<10')
old="target.writeByteArray([0x48,0xb8,...Array.from(new Uint8Array(Memory.alloc(8).writePointer(fixture.sender).readByteArray(8))),0xff,0xe0]);"
new="target.writeByteArray([0x48,0x83,0xec,0x28,0x48,0xb8,...Array.from(new Uint8Array(Memory.alloc(8).writePointer(fixture.sender).readByteArray(8))),0xff,0xd0,0x48,0x83,0xc4,0x28,0xc3]);"
assert setup.count(old)==1;setup=setup.replace(old,new)
tail=r'''
const ctl=prepareElsNativeSendSerialization()(),counts={},errors=[],states=new Map();
function add(name){
 counts[name]={enter:0,leave:0,native_contexts:0};
 return elsObserveNativeSend({onEnter(args){
  this.thread=this.threadId;this.previous=states.get(name+this.thread);this.bound=name;
  states.set(name+this.thread,name);counts[name].enter++;
  if(this.returnAddress.isNull()||this.context.rsp.isNull())throw Error('Opaque native context forwarding');
  counts[name].native_contexts++;
 },onLeave(){
  if(this.bound!==name||states.get(name+this.thread)!==name)throw Error('Observer state collision '+name);
  if(this.returnAddress.isNull()||this.context.rsp.isNull())throw Error('Return context forwarding');
  if(this.previous===undefined)states.delete(name+this.thread);else states.set(name+this.thread,this.previous);
  counts[name].leave++;
 }});
}
add('raid');const removable=add('artifact');add('result');
const nestedSend=new NativeFunction(target,'void',['pointer','pointer'],{exceptions:'propagate'}),depths=new Set();let nested=0;
elsObserveNativeSend({onEnter(args){const tid=this.threadId;if(depths.has(tid))return;depths.add(tid);try{nestedSend(args[0],ptr(0));nested++;}finally{depths.delete(tid);}}});
Interceptor.flush();const first=sample();
add('late');const second=sample();removable.detach();const artifactBefore=counts.artifact.enter;
let threw=false;elsObserveNativeSend({onEnter(){if(!threw){threw=true;throw Error('expected logical observer error');}}});
const third=sample();
let canceledEnter=0,canceledLeave=0,canceled;
elsObserveNativeSend({onEnter(){canceled.detach();}});
canceled=elsObserveNativeSend({onEnter(){canceledEnter++;},onLeave(){canceledLeave++;}});
const fourth=sample();
rpc.exports={result(){return{physical,first,second,third,fourth,counts,nested,lock_recursion:ctl.lock.add(12).readU32(),remaining_states:states.size,artifact_detach_worked:artifactBefore===counts.artifact.enter,expected_error_exercised:threw,canceledEnter,canceledLeave};}};
'''
proc=None;session=None;result={};errors=[]
try:
 proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(70)'],creationflags=0x08000000)
 instrumentation="let physical=0;const observedInterceptor={attach(address,...args){if(address.equals(target))physical++;return Interceptor.attach(address,...args);},flush(){Interceptor.flush();}};"
 session=frida.attach(proc.pid);script=session.create_script(setup+'\n'+instrumentation+'\n((Process,Interceptor)=>{\n'+source(b,EXE_SHA)+'\n'+tail+'\n})(hostProcess,observedInterceptor);')
 script.on('message',lambda m,d:errors.append(m)if m.get('type')=='error'else None);script.load();time.sleep(.3)
 result=script.exports_sync.result()
 assert result['physical']==2 and result['lock_recursion']==0 and result['remaining_states']==0,result
 assert all(result[k]['duplicates']==0 and result[k]['ordered']for k in ('first','second','third','fourth')),result
 assert result['canceledEnter']==result['canceledLeave']==0,result
 assert all(v['enter']==v['leave']==v['native_contexts']and v['enter']>0 for v in result['counts'].values()),result
 assert result['artifact_detach_worked']and result['nested']>0 and result['expected_error_exercised'],result
 assert len(errors)==1 and 'expected logical observer error'in errors[0]['description'],errors
 result.update(ok=True,reported_errors=[e['description']for e in errors],owned_host_only=True,natural_game=False,production_modified=False,frida_version=frida.__version__)
except BaseException as e:
 result.update(ok=False,error=str(e),Frida_errors=errors)
 raise
finally:
 if proc is not None:proc.terminate();proc.wait(timeout=8)
 if session is not None:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'shared-sender-host.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
