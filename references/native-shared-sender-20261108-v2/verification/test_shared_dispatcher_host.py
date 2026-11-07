"""Exercise exact shared dispatcher with real Gum and owned CModule functions."""
from pathlib import Path
import hashlib,json,subprocess,sys,time,traceback
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate'
sys.path.insert(0,str(C/'tools/pylibs'));import frida
p=C/'tools/native_send_serialization.js';raw=p.read_text('utf-8');dispatcher=raw[raw.index('function prepareElsNativeSendSerialization'):]
assert dispatcher.count('__SEND_SERIALIZATION_PINS__')==1;dispatcher=dispatcher.replace('__SEND_SERIALIZATION_PINS__','{}')
dispatcher=dispatcher.replace('module.base.add(0x682d80)','fixture.sender').replace('module.base.add(0x30d0660)','fixture.field')
source=r'''
const k=Process.getModuleByName('kernel32.dll'),fixture=new CModule(`#include <gum/guminterceptor.h>
extern void Sleep(unsigned int n);
extern volatile int ticks;
void sender(void *p){Sleep(0);ticks++;}
void field(void *p){Sleep(0);ticks++;}
`,{Sleep:k.getExportByName('Sleep'),ticks:Memory.alloc(4)});
function installElsNativeCryptoLock(){return{lifetime:{installed:true}};}
const fakeProcess={getModuleByName(){return{base:ptr(0)}}};
'''+ '\n((Process)=>{\n'+dispatcher+r'''
const ctl=prepareElsNativeSendSerialization()(),log=[],scopes=new Map();let counter=0,late,dead,lateCalls=0,deadCalls=0,errorsExpected=0;
for(const name of ['main','artifact','result'])ctl.observe({onEnter(){this.role=name;this.index=counter++;this.lastError=321;if(this.lastError!==321||this.context.rsp.isNull()||this.returnAddress.isNull())throw Error('native getter receiver');scopes.set(this.index,name);},onLeave(){if(this.role!==name||scopes.get(this.index)!==name)throw Error('logical this collision');scopes.delete(this.index);log.push(name);}});
ctl.observe({onEnter(){if(!late){late=ctl.observe({onEnter(){lateCalls++;}});dead.detach();}}});
dead=ctl.observe({onEnter(){deadCalls++;},onLeave(){deadCalls++;}});
ctl.observe({onEnter(){if(!errorsExpected++){throw Error('expected dispatcher logical error');}},onLeave(){log.push('error-listener-cleanup');}});
let mainField=0,artifactField=0,qaField=0,shopEnter=0,shopLeave=0;
ctl.observeField({onLeave(){mainField++;}});ctl.observeField({onLeave(){artifactField++;}});ctl.observeField({onLeave(){qaField++;}});
let dynamic=ctl.observeField({onEnter(){shopEnter++;this.key='shop';},onLeave(){if(this.key!=='shop')throw Error('shop scope');shopLeave++;dynamic.detach();}});
const sendNative=new NativeFunction(fixture.sender,'void',['pointer']),fieldNative=new NativeFunction(fixture.field,'void',['pointer']);Interceptor.flush();
for(let i=0;i<4;i++){sendNative(ptr(0));fieldNative(ptr(0));}
if(ctl!==prepareElsNativeSendSerialization()())throw Error('repeat install');
rpc.exports={result(){return{main:log.filter(x=>x==='main').length,artifact:log.filter(x=>x==='artifact').length,result:log.filter(x=>x==='result').length,error_cleanup:log.filter(x=>x==='error-listener-cleanup').length,lateCalls,deadCalls,remaining_scopes:scopes.size,mainField,artifactField,qaField,shopEnter,shopLeave,logical_fields_after_close:ctl.fieldObserverCount()};}};
})(fakeProcess);
'''
proc=None;session=None;errors=[];result={'ok':False}
try:
 proc=subprocess.Popen([sys.executable,'-c','import time;time.sleep(40)'],creationflags=0x08000000);session=frida.attach(proc.pid)
 script=session.create_script(source);script.on('message',lambda m,d:errors.append(m)if m.get('type')=='error'else None);script.load();time.sleep(.2);result=script.exports_sync.result()
 assert all(result[k]==4 for k in ['main','artifact','result','error_cleanup','mainField','artifactField','qaField']),result
 assert result['lateCalls']==3 and result['deadCalls']==0 and result['remaining_scopes']==0 and result['shopEnter']==result['shopLeave']==1 and result['logical_fields_after_close']==3,result
 assert len(errors)==1 and 'expected dispatcher logical error'in errors[0]['description'],errors
 result.update(ok=True,exact_candidate_JS_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),actual_Frida=frida.__version__,owned_host_only=True,original_game=False,crypto_retested=False,errors=[e['description']for e in errors])
except BaseException:
 result.update(error=traceback.format_exc(),errors=errors);raise
finally:
 if proc:proc.terminate();proc.wait(timeout=8)
 if session:
  try:session.detach()
  except frida.InvalidOperationError:pass
 (H/'shared-dispatcher-host.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
print(json.dumps(result))
