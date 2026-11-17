// Serialize native104 requests through the original105 wait lifecycle.
function installElsWearSync() {
 'use strict';
 if(globalThis.elsWearSync)throw Error('Native wear synchronization already installed');
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__WEAR_SYNC_PINS__;
 for(const [r,expected] of Object.entries(pins)){
  const actual=Array.from(new Uint8Array(module.base.add(+r).readByteArray(expected.length/2)),x=>x.toString(16).padStart(2,'0')).join('');
  if(actual!==expected)throw Error('Native wear synchronization identity '+r);
 }
 const target=module.base.add(0x22634a0);
 const types=['pointer','int','int','uint64','int','int','uint64'];
 const original=new NativeFunction(target,'uint8',types,{exceptions:'propagate'});
 const waiting=new NativeFunction(module.base.add(0x74fa90),'uint8',['pointer','int'],{exceptions:'propagate'});
 const state={blocked:0};
 const replacement=new NativeCallback((controller,sourceGroup,sourceSlot,sourceUID,destinationGroup,destinationSlot,destinationUID)=>{
  const app=module.base.add(0x4817e80).readPointer();
  if(waiting(app,0x105)){
   state.blocked++;
   return 0;
  }
  return original(controller,sourceGroup,sourceSlot,sourceUID,destinationGroup,destinationSlot,destinationUID);
 },'uint8',types);
 Interceptor.replace(target,replacement);
 Interceptor.flush();
 state.replacement=replacement;
 state.dispose=()=>{
  Interceptor.revert(target);
  Interceptor.flush();
  delete globalThis.elsWearSync;
 };
 globalThis.elsWearSync=state;
 send({event:'native_wear_sync_ready',request:'22634A0',pending_query:'74FA90',response:0x105});
 return state;
}
