"""Add only logical QA observers and an owned normal shop-toggle action."""
from pathlib import Path
import runpy,sys
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate'
sys.path[:0]=[str(C/'tools'),str(C),str(C/'tools/pylibs')]
import native_cache_sync
compose=native_cache_sync.compose
def observed(*args):
 source=compose(*args).replace('__LIGHTWEIGHT_PLAY__','false')
 anchor='const observerListener=Interceptor.attach(address,{'
 assert source.count(anchor)==1
 source=source.replace(anchor,"note({event:'owned_physical_observer_attached',RVA:address.sub(module.base).toString()});\n  "+anchor)
 anchor="send({event:'local_ed_shop_bridge_ready'"
 assert source.count(anchor)==1
 source=source.replace(anchor,"""globalThis.__elsOwnedShopQA={toggle:ebScheduleToggle,snapshot(s){
 if(!ebOwnedState(s))return null;const ui=s.add(0x440).readPointer();
 return{open:ui.add(0x128).readU8()===1,ready:ui.add(0x500).readU8()===1,initialized:!!(ebContext&&ebCurrent(ebContext)&&ebContext.initialized),selector:s.add(0x4b4).readS32(),availability:ebM.base.add(0x4817e50).readPointer().add(0x3f8).readU8(),entryState:ebM.base.add(0x4817e50).readPointer().add(0x3f9).readU8()};
}};
"""+anchor)
 return source+r'''
const ownedSendCheck=setInterval(()=>{
 const installed=globalThis.elsNativeSendSerialization;if(!installed)return;
 const repeated=prepareElsNativeSendSerialization()();
 note({event:'owned_send_serialization_loaded',active:installed.active(),repeated_install_same:installed===repeated,unwind_call_sites:installed.unwind.length});
 const aliases=new Map();
 elsObserveNativeSend({onEnter(args){this.kind=args[1].add(0x34).readU16();const key=args[0].toString();if(!aliases.has(key))aliases.set(key,aliases.size+1);note({event:'owned_send_enter',kind:this.kind,sender_alias:aliases.get(key),caller_RVA:this.returnAddress.sub(Process.getModuleByName('x2_dx11.exe').base).toString()});},onLeave(){note({event:'owned_send_leave',kind:this.kind});}});
 elsObserveNativeSend({onLeave(){note({event:'owned_send_leave_only'});}});
 let opened=false,closed=false,openRequested=false,closeRequested=false,openedAt=0,firstOwnedAt=0,fieldEnter=0,fieldLeave=0;
 elsObserveNativeField({onEnter(args){this.state=args[0];fieldEnter++;},onLeave(){
  fieldLeave++;const qa=globalThis.__elsOwnedShopQA;if(!qa)return;const state=this.state,snapshot=qa.snapshot(state);if(!snapshot)return;
  if(!firstOwnedAt)firstOwnedAt=Date.now();
  if(!openRequested&&Date.now()-firstOwnedAt<2000)return;
  if(!openRequested&&!snapshot.open){openRequested=true;qa.toggle(state,false);note({event:'owned_shop_open_requested',no_OS_input:true,native_state:snapshot});return;}
  if(openRequested&&!opened&&snapshot.open&&snapshot.ready&&snapshot.initialized){opened=true;openedAt=Date.now();note({event:'owned_shop_open_verified',native_open:true,native_ready:true});}
  if(opened&&!closeRequested&&Date.now()-openedAt>=1500){closeRequested=true;qa.toggle(state,false);note({event:'owned_shop_close_requested',no_OS_input:true});return;}
  if(closeRequested&&!closed&&!snapshot.open){closed=true;note({event:'owned_shop_closed_verified',native_closed:true});}
 }});
 setInterval(()=>note({event:'owned_send_lock_state',recursion:installed.lock.add(12).readS32(),logical_observers:installed.observerCount(),logical_field_observers:installed.fieldObserverCount(),fieldEnter,fieldLeave,opened,closed,stats:installed.stats()}),500);
 clearInterval(ownedSendCheck);
},250);
'''
native_cache_sync.compose=observed
sys.argv=[str(C/'tools/probe_updated_client.py'),*sys.argv[1:]]
runpy.run_path(sys.argv[0],run_name='__main__')
