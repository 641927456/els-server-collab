// Original entry, achievement, party requests and Chaos rewards from the current owned actor.
function installElsRaidNativePower(){
 'use strict';
 if(globalThis.elsRaidNativePower)return globalThis.elsRaidNativePower;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__RAID_POWER_PINS__;
 const rewardPins=__RAID_REWARD_POWER_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Raid native CP identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const build=call(0x896870,'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const store=call(0x8a1400,'void',['pointer','float']);
 const contexts=new Map(),henirInputs=new Map(),hooks=[];let disabled=false,displayDisabled=false,calculating=false,writes=0,rewardRoom=null,rewardDisabled=false;
 function capture(sender){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  // Engine+C0 owns the shared sender handle. The common682D80 receives
  // its pointee, after the original template has copied that shared owner.
  const senderOwner=engine.add(0xc0).readPointer();if(senderOwner.isNull()||!senderOwner.readPointer().equals(sender))return null;
  const senderControl=senderOwner.add(8).readPointer();
  const carrier=engine.add(0xc8).readPointer();if(carrier.isNull())return null;
  const unit=carrier.add(0xa0).readPointer();if(unit.isNull())return null;
  const definition=unit.add(0x29c0).readPointer();if(definition.isNull())return null;
  const uid=unit.add(0x48).readU64().toString(),family=definition.readS32(),klass=unit.add(0x58).readU16();
  if(uid==='0'||uid==='18446744073709551615'||family<1||family>15||!klass)return null;
  return{sender,senderOwner,senderControl,engine,carrier,unit,definition,uid,family,klass};
 }
 function same(a,b){return b&&['sender','senderOwner','senderControl','engine','carrier','unit','definition'].every(k=>a[k].equals(b[k]))&&['uid','family','klass'].every(k=>a[k]===b[k]);}
 function power(a,cache){
  const empty1=Memory.alloc(24),empty2=Memory.alloc(24),cp=Memory.alloc(4),dp=Memory.alloc(4);
  function side(n){
   cp.writeFloat(0);dp.writeFloat(0);build(a.unit,n,0,empty1,empty2,cp,dp,1,-1,ptr(0));
   const value=cp.readFloat();
   if(!Number.isFinite(value)||value<0||value>4294967040||!Number.isFinite(dp.readFloat())||dp.readFloat()<0)throw Error('Raid native CP result');
   if([...new Uint8Array(empty1.readByteArray(24)),...new Uint8Array(empty2.readByteArray(24))].some(v=>v!==0))throw Error('Raid native CP borrowed inputs changed');
   return value;
  }
  const first=side(0),value=a.family===10?Math.max(first,side(1)):first;
  if(!same(a,capture(a.sender)))throw Error('Raid native CP actor changed');
  if(!cache)return value;
  store(a.unit,value);return a.unit.add(0x3048).readFloat();
 }
 function fail(error,display=false){
  if(display)displayDisabled=true;else disabled=true;
  send({event:display?'party_display_power_disabled':'raid_native_power_disabled',reason:String(error),writes});
 }
 function rewardFailure(error){
  rewardRoom=null;rewardDisabled=true;
  send({event:'chaos_reward_power_disabled',reason:String(error)});
 }
 function rewardScene(){
  const engine=module.base.add(0x4817e70).readPointer();
  if(engine.isNull()||engine.add(0x41c).readS32()!==30)return null;
  const owner=engine.add(0xc0).readPointer();
  return owner.isNull()?null:capture(owner.readPointer());
 }
 // Return addresses from the original invite, reply, create and apply senders.
 const displaySenders=new Map([[0x136,0x2e0d612],[0x139,0x2e0d9d6],[0x8ee,0x235c97d],[0x8f3,0x235ccdd]]);
 // 2D62090/2D6D830 copy the selected mode into byte6 of the entry DTO.
 // 2E09A80 receives this borrowed DTO before the virtualized inner writer.
 // Keep it only within that synchronous native call and its owned actor.
 hooks.push(Interceptor.attach(module.base.add(0x2e09a80),{
  onEnter(args){
   this.thread=Process.getCurrentThreadId();this.previous=henirInputs.get(this.thread);
   henirInputs.delete(this.thread);
   try{
    const kind=args[1].toUInt32()&65535;
    if(disabled||![0x37f,0x382].includes(kind)||args[2].readS32()!==38100)return;
    const engine=module.base.add(0x4817e70).readPointer();
    if(engine.isNull()||!engine.add(0xc0).readPointer().equals(args[0]))throw Error('Henir entry sender owner');
    const a=capture(args[0].readPointer()),mode=args[2].add(6).readU8();
    if(!a||![1,2].includes(mode))throw Error('Henir original selected mode');
    henirInputs.set(this.thread,{actor:a,mode,kind});
   }catch(error){fail(error);}
  },onLeave(){if(this.previous===undefined)henirInputs.delete(this.thread);else henirInputs.set(this.thread,this.previous);}
 }));
 hooks.push(Interceptor.attach(module.base.add(0x682d80),{
  onEnter(args){this.thread=Process.getCurrentThreadId();this.previous=contexts.get(this.thread);this.bound=null;
   const rewardSender=this.returnAddress.equals(module.base.add(0x368cacc));
   try{
    const event=args[1],kind=event.add(0x34).readU16(),site=displaySenders.get(kind);
    const display=!displayDisabled&&site!==undefined&&this.returnAddress.equals(module.base.add(site));
    const reward=!rewardDisabled&&kind===0xcd6&&rewardSender;
    if(!disabled&&!calculating&&event.add(0x10).readU32()===0x202){
     if([0x7d4,0x37f,0x382].includes(kind))rewardRoom=null;
     if(display||reward||[0x6be,0x7d4,0x14c,0x37f,0x382].includes(kind)){
      const a=capture(args[0]);if(a)this.bound={...a,event,kind,display,reward,written:false};
     }
    }
   }catch(error){if(rewardSender)rewardFailure(error);else fail(error);}
   contexts.set(this.thread,this.bound);
  },onLeave(){if(this.previous===undefined)contexts.delete(this.thread);else contexts.set(this.thread,this.previous);}
 }));
 hooks.push(Interceptor.attach(module.base.add(0x680b50),{
  onEnter(args){
   this.saved=null;const a=contexts.get(Process.getCurrentThreadId()),event=args[1];
   if(disabled||!a||a.written||!event.equals(a.event)||event.add(0x10).readU32()!==0x202||event.add(0x34).readU16()!==a.kind||event.add(0x36).readU8()!==0)return;
   const display=a.display;
   try{
    const begin=event.add(0x3e).readPointer(),end=event.add(0x46).readPointer(),length=end.sub(begin).toInt32();
    if(a.kind===0x136&&(length<46||length>254)||a.kind===0x139&&length!==30||
       a.kind===0x8ee&&(length<30||length>190)||a.kind===0x8f3&&length!==8)return;
    let combat;
    if(a.reward){
     if(length!==4||!same(a,rewardRoom)||!same(a,rewardScene()))return;
     combat=rewardRoom.power;
    }else{
     if(a.kind===0x6be&&length!==0||a.kind===0x7d4&&length!==8||a.kind===0x14c&&length!==5||[0x37f,0x382].includes(a.kind)&&(length<23||length>86))throw Error('Raid native entry payload shape');
     if(!same(a,capture(a.sender)))throw Error('Raid native entry actor changed');
     calculating=true;try{combat=power(a,!display);}finally{calculating=false;}
     if(!Number.isFinite(combat)||combat<0||combat>4294967040)throw Error('Raid native cached CP range');
    }
    const selection=henirInputs.get(Process.getCurrentThreadId());
    const henir=selection&&selection.kind===a.kind&&same(selection.actor,capture(a.sender))?selection:null;
    const extra=henir?13:0;
    const bytes=new Uint8Array(length+extra+16),view=new DataView(bytes.buffer);if(length)bytes.set(new Uint8Array(begin.readByteArray(length)));
    const uid=uint64(a.uid).toString(16).padStart(16,'0');
    if(henir){
     view.setUint32(length,0x484e5231,false);
     for(let i=0;i<8;i++)bytes[length+4+i]=parseInt(uid.slice(i*2,i*2+2),16);
     bytes[length+12]=henir.mode;
    }
    const footer=length+extra;
    view.setUint32(footer,a.reward?0x48435031:display?0x50435031:0x52435031,false);
    for(let i=0;i<8;i++)bytes[footer+4+i]=parseInt(uid.slice(i*2,i*2+2),16);
    if(a.reward)view.setInt32(footer+12,combat,false);else view.setFloat32(footer+12,combat,false);
    const raw=Memory.alloc(bytes.length);raw.writeByteArray(bytes);this.storage=raw;this.event=event;
    this.saved=event.add(0x3e).readByteArray(24);this.reward=a.reward;a.written=true;
    event.add(0x3e).writePointer(raw);event.add(0x46).writePointer(raw.add(bytes.length));event.add(0x4e).writePointer(raw.add(bytes.length));
   }catch(error){if(a.reward)rewardFailure(error);else fail(error,display&&this.saved===null);}
  },onLeave(result){
   if(this.saved===null)return;
   try{this.event.add(0x3e).writeByteArray(this.saved);if((result.toUInt32()&255)===0)throw Error('Raid native CP encoder failed');writes++;}
   catch(error){if(this.reward)rewardFailure(error);else fail(error);}
  }
 }));
 try{
  for(const[r,h]of Object.entries(rewardPins))
   if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Chaos reward CP identity '+r);
  // R15d holds the integer CP after shared cache sync. R8d also supplies the displayed requirement.
  hooks.push(Interceptor.attach(module.base.add(0x363edd4),function(){
   if(disabled||rewardDisabled)return;
   try{
    const actor=rewardScene();
    if(!actor||!this.context.r13.equals(actor.engine.add(0x3b8)))return;
    if(!same(actor,rewardRoom)){
     const power=this.context.r15.toInt32();
     if(power<0)return;
     rewardRoom={...actor,power};
    }
    let threshold=this.context.r8.toInt32();
    if(this.context.rdi.toInt32()===1&&threshold===1000000){
     threshold=1100000;
     this.context.r8=ptr(threshold);
    }
    // Only equality needs adjusting for the original strict comparison.
    this.context.r15=ptr(rewardRoom.power+(rewardRoom.power===threshold?1:0));
   }catch(error){rewardFailure(error);}
  }));
 }catch(error){rewardFailure(error);}
 const controller={active:()=>!disabled,dispose(){for(const h of hooks)h.detach();contexts.clear();henirInputs.clear();rewardRoom=null;disabled=true;if(globalThis.elsRaidNativePower===controller)delete globalThis.elsRaidNativePower;}};
 globalThis.elsRaidNativePower=controller;
 send({event:'raid_native_power_ready',original_calculator:'896870',original_cache:'8A1400',original_encoder:'680B50',client_EXE_changed:false});
 return controller;
}
