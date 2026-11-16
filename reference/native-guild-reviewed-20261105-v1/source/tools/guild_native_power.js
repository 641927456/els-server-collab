// Scope: one original ABC signup. All CP arithmetic is the existing native producer.
function installElsGuildNativePower(){
 'use strict';
 if(globalThis.elsGuildNativePower)return globalThis.elsGuildNativePower;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__GUILD_POWER_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Guild native power identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const build=call(0x896870,'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const writeInt=call(0x3b6dbd0,'bool',['pointer','int']),writeUID=call(0x3b6dda0,'bool',['pointer','uint64']),writeFloat=call(0x3b6dcc0,'bool',['pointer','float']);
 const contexts=new Map(),hooks=[];let disabled=false,writes=0,calculating=false;
 function capture(sender){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const carrier=engine.add(0xc8).readPointer();if(carrier.isNull()||!engine.add(0xc0).readPointer().equals(sender))return null;
  const unit=carrier.add(0xa0).readPointer();if(unit.isNull())return null;
  const definition=unit.add(0x29c0).readPointer();if(definition.isNull())return null;
  const uid=unit.add(0x48).readU64().toString(),family=definition.readS32(),klass=unit.add(0x58).readU16();
  if(uid==='0'||uid==='18446744073709551615'||family<1||family>15||!klass)return null;
  return {sender,engine,carrier,unit,definition,uid,family,klass};
 }
 function same(a,b){return b&&['sender','engine','carrier','unit','definition'].every(k=>a[k].equals(b[k]))&&['uid','family','klass'].every(k=>a[k]===b[k]);}
 function power(a){
  const empty1=Memory.alloc(24),empty2=Memory.alloc(24),cp=Memory.alloc(4),dp=Memory.alloc(4);
  function side(n){
   cp.writeFloat(0);dp.writeFloat(0);build(a.unit,n,0,empty1,empty2,cp,dp,1,-1,ptr(0));
   const v=cp.readFloat();
   if(!Number.isFinite(v)||v<0||v>=2147483648||!Number.isFinite(dp.readFloat())||dp.readFloat()<0)throw Error('Guild native CP range');
   if([...new Uint8Array(empty1.readByteArray(24)),...new Uint8Array(empty2.readByteArray(24))].some(v=>v!==0))throw Error('Guild borrowed native input vectors changed');
   return v;
  }
  const first=side(0),value=a.family===10?Math.max(first,side(1)):first;
  if(!same(a,capture(a.sender)))throw Error('Guild native CP actor changed');
  return value;
 }
 function fail(error){disabled=true;send({event:'guild_native_power_disabled',reason:String(error),writes});}
 hooks.push(Interceptor.attach(module.base.add(0x242f510),{
  onEnter(args){
   this.thread=Process.getCurrentThreadId();this.previous=contexts.get(this.thread);this.bound=null;
   try{
    if(!disabled&&!calculating&&args[1].toUInt32()===0xabc&&this.returnAddress.equals(module.base.add(0x30dd8ba))){
     const stage=args[2].readS8(),a=capture(args[0]);
     if(a&&stage>=1&&stage<=12){calculating=true;try{this.bound={...a,stage,cp:power(a),written:false};}finally{calculating=false;}}
    }
   }catch(error){fail(error);}
   contexts.set(this.thread,this.bound);
  },
  onLeave(){if(this.previous===undefined)contexts.delete(this.thread);else contexts.set(this.thread,this.previous);}
 }));
 hooks.push(Interceptor.attach(module.base.add(0x3b6da30),{
  onEnter(args){
   this.bound=contexts.get(Process.getCurrentThreadId());this.stream=args[0];
   if(disabled||!this.bound||this.bound.written||!this.returnAddress.equals(module.base.add(0x24318be))||args[1].toInt32()!==this.bound.stage)this.bound=null;
  },
  onLeave(result){
   if(!this.bound||(result.toInt32()&255)!==1)return;
   try{
    const a=this.bound;if(!same(a,capture(a.sender)))throw Error('Guild signup actor changed before serialization');
    a.written=true;
    if(!writeInt(this.stream,0x47505731)||!writeUID(this.stream,uint64(a.uid))||!writeFloat(this.stream,a.cp))throw Error('Guild signup CP extension encoding');
    writes++;send({event:'guild_native_power_written',uid:a.uid,stage:a.stage,combat:a.cp,original_calculator:'896870',original_fields_untouched:true,writes});
   }catch(error){fail(error);}
  }
 }));
 const controller={active:()=>!disabled,dispose(){for(const h of hooks)h.detach();contexts.clear();disabled=true;if(globalThis.elsGuildNativePower===controller)delete globalThis.elsGuildNativePower;send({event:'guild_native_power_disabled',reason:'disposed',writes});}};
 globalThis.elsGuildNativePower=controller;
 send({event:'guild_native_power_ready',native_calculator:'896870',original_signup:'30DD8B5/242F510/24317B0',new_gameplay_formula:false});
 return controller;
}
