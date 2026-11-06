// Only the current owned actor's original entry/ready send; all CP arithmetic is native.
function installElsRaidNativePower(){
 'use strict';
 if(globalThis.elsRaidNativePower)return globalThis.elsRaidNativePower;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__RAID_POWER_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Raid native CP identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const build=call(0x896870,'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const store=call(0x8a1400,'void',['pointer','float']);
 const contexts=new Map(),hooks=[];let disabled=false,calculating=false,writes=0;
 function capture(sender){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const carrier=engine.add(0xc8).readPointer();if(carrier.isNull()||!engine.add(0xc0).readPointer().equals(sender))return null;
  const unit=carrier.add(0xa0).readPointer();if(unit.isNull())return null;
  const definition=unit.add(0x29c0).readPointer();if(definition.isNull())return null;
  const uid=unit.add(0x48).readU64().toString(),family=definition.readS32(),klass=unit.add(0x58).readU16();
  if(uid==='0'||uid==='18446744073709551615'||family<1||family>15||!klass)return null;
  return{sender,engine,carrier,unit,definition,uid,family,klass};
 }
 function same(a,b){return b&&['sender','engine','carrier','unit','definition'].every(k=>a[k].equals(b[k]))&&['uid','family','klass'].every(k=>a[k]===b[k]);}
 function power(a){
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
  store(a.unit,value);return a.unit.add(0x3048).readFloat();
 }
 function fail(error){disabled=true;send({event:'raid_native_power_disabled',reason:String(error),writes});}
 // 7D4/14C and37F/382 have distinct template senders. All reach this
 // original common sender with the already prepared202 event.
 hooks.push(Interceptor.attach(module.base.add(0x682d80),{
  onEnter(args){this.thread=Process.getCurrentThreadId();this.previous=contexts.get(this.thread);this.bound=null;
   try{const event=args[1],kind=event.add(0x34).readU16();if(!disabled&&!calculating&&event.add(0x10).readU32()===0x202&&[0x7d4,0x14c,0x37f,0x382].includes(kind)){const a=capture(args[0]);if(a)this.bound={...a,event,kind,written:false};}}catch(error){fail(error);}
   contexts.set(this.thread,this.bound);
  },onLeave(){if(this.previous===undefined)contexts.delete(this.thread);else contexts.set(this.thread,this.previous);}
 }));
 hooks.push(Interceptor.attach(module.base.add(0x680b50),{
  onEnter(args){
   this.saved=null;const a=contexts.get(Process.getCurrentThreadId()),event=args[1];
   if(disabled||!a||a.written||!event.equals(a.event)||event.add(0x10).readU32()!==0x202||event.add(0x34).readU16()!==a.kind||event.add(0x36).readU8()!==0)return;
   try{
    const begin=event.add(0x3e).readPointer(),end=event.add(0x46).readPointer(),length=end.sub(begin).toInt32();
    if(a.kind===0x7d4&&length!==8||a.kind===0x14c&&length!==5||[0x37f,0x382].includes(a.kind)&&(length<23||length>86))throw Error('Raid native entry payload shape');
    if(!same(a,capture(a.sender)))throw Error('Raid native entry actor changed');
    calculating=true;let combat;try{combat=power(a);}finally{calculating=false;}
    if(!Number.isFinite(combat)||combat<0||combat>4294967040)throw Error('Raid native cached CP range');
    const bytes=new Uint8Array(length+16),view=new DataView(bytes.buffer);bytes.set(new Uint8Array(begin.readByteArray(length)));
    view.setUint32(length,0x52435031,false);
    const uid=uint64(a.uid).toString(16).padStart(16,'0');for(let i=0;i<8;i++)bytes[length+4+i]=parseInt(uid.slice(i*2,i*2+2),16);
    view.setFloat32(length+12,combat,false);
    const raw=Memory.alloc(bytes.length);raw.writeByteArray(bytes);this.storage=raw;this.event=event;
    this.saved=event.add(0x3e).readByteArray(24);a.written=true;
    event.add(0x3e).writePointer(raw);event.add(0x46).writePointer(raw.add(bytes.length));event.add(0x4e).writePointer(raw.add(bytes.length));
   }catch(error){fail(error);}
  },onLeave(result){
   if(this.saved===null)return;
   try{this.event.add(0x3e).writeByteArray(this.saved);if((result.toUInt32()&255)===0)throw Error('Raid native CP encoder failed');writes++;}
   catch(error){fail(error);}
  }
 }));
 const controller={active:()=>!disabled,dispose(){for(const h of hooks)h.detach();contexts.clear();disabled=true;if(globalThis.elsRaidNativePower===controller)delete globalThis.elsRaidNativePower;}};
 globalThis.elsRaidNativePower=controller;
 send({event:'raid_native_power_ready',original_calculator:'896870',original_cache:'8A1400',original_encoder:'680B50',client_EXE_changed:false});
 return controller;
}
