// One native9E writer for both extensions. A fast entry also runs when the
// original sender is called from a Gum listener, which suppresses listeners.
function prepareElsReportWriter(){
 'use strict';
 if(prepareElsReportWriter.prepared)return prepareElsReportWriter.prepared;
 const module=Process.getModuleByName('x2_dx11.exe'),consumers=new Map();
 const originalBytes=Array.from(new Uint8Array(module.base.add(0xda2f50).readByteArray(16)),v=>v.toString(16).padStart(2,'0')).join('');
 const support={original:null,installed:false};
 support.callback=new NativeCallback(function(stream,dto,caller){
  const ok=support.original(stream,dto);
  if(ok===1&&caller.equals(module.base.add(0xc690a1)))for(const append of consumers.values())append(stream,dto);
  return ok;
 },'uint8',['pointer','pointer','pointer']);
 // Forward the original return address as a third callback argument. The
 // original bool writer consumes only stream/dto, as its native reader proves.
 const code=[0x4c,0x8b,0x04,0x24,0xff,0x25,0,0,0,0];
 let address=BigInt(support.callback.toString());for(let i=0;i<8;i++){code.push(Number(address&255n));address>>=8n;}
 support.entry=Memory.alloc(Process.pageSize);support.entry.writeByteArray(code);
 if(!Memory.protect(support.entry,Process.pageSize,'r-x'))throw Error('Native report writer entry protection');
 const api={matchesOriginal:expected=>support.installed&&originalBytes===expected,register(name,append){
  if(consumers.has(name))throw Error('Native report writer duplicate '+name);
  if(!support.installed){
   const original=Interceptor.replaceFast(module.base.add(0xda2f50),support.entry);
   support.original=new NativeFunction(original,'uint8',['pointer','pointer'],{exceptions:'propagate'});
   support.installed=true;
  }
  consumers.set(name,append);let registered=true;
  return()=>{if(!registered)return;registered=false;consumers.delete(name);};
 }};
 prepareElsReportWriter.prepared=api;
 return api;
}

// Read the original owned Actor maximum HP only while its original9E is built.
function installElsPvpHpSource(){
 'use strict';
 if(globalThis.elsPvpHpSource)return globalThis.elsPvpHpSource;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__PVP_HP_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins)){
  if(+r===0xda2f50&&prepareElsReportWriter.prepared?.matchesOriginal(h))continue;
  if(hex(module.base.add(+r),h.length/2)!==h)throw Error('PvP HP source identity '+r);
 }
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const actorOf=call(0x8571d0,'pointer',['pointer']),maximumHP=call(0x7d57a0,'float',['pointer']),currentHP=call(0x7d8b00,'float',['pointer']);
 const writeInt=call(0x3b6dbd0,'bool',['pointer','int']),writeFloat=call(0x3b6dcc0,'bool',['pointer','float']);
 const active=new Map(),hooks=[];let disabled=false,writes=0,disposed=false;
 function capture(game){
  if(!game.readPointer().equals(module.base.add(0x4183dd0)))return null; // original ordinary team game
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const manager=engine.add(0xc8).readPointer();if(manager.isNull())return null;
  const unit=manager.add(0xa0).readPointer(),actor=actorOf(game);if(unit.isNull()||actor.isNull())return null;
  const actorUnit=actor.add(0x1a3e0).readPointer();if(actorUnit.isNull())return null;
  const uid=unit.add(0x48).readU64().toString();if(uid==='0'||actorUnit.add(0x48).readU64().toString()!==uid)return null;
  return {game,engine,manager,unit,actor,actorUnit,uid};
 }
 function same(a,b){return b&&a.uid===b.uid&&['game','engine','manager','unit','actor','actorUnit'].every(k=>a[k].equals(b[k]));}
 hooks.push(Interceptor.attach(module.base.add(0x1ab7ac0),{
  onEnter(args){this.thread=Process.getCurrentThreadId();this.previous=active.get(this.thread);try{this.bound=disabled?null:capture(args[0]);}catch(error){disabled=true;this.bound=null;send({event:'pvp_native_hp_source_disabled',reason:String(error),writes});}active.set(this.thread,this.bound);},
  onLeave(){if(this.previous===undefined)active.delete(this.thread);else active.set(this.thread,this.previous);}
 }));
 const removeWriter=prepareElsReportWriter().register('pvp',function(stream,dto){
   const bound=disabled?null:active.get(Process.getCurrentThreadId());if(!bound)return;
   try{
    const a=bound,b=capture(a.game);if(!same(a,b))throw Error('PvP report owner changed');
    const current=currentHP(a.actor),maximum=maximumHP(a.actor),reported=dto.readFloat();
    if(!Number.isFinite(current)||!Number.isFinite(maximum)||maximum<=0||current<0||current>maximum||reported!==current)throw Error('PvP original report health changed');
    if(!same(a,capture(a.game)))throw Error('PvP report generation changed');
    if(!writeInt(stream,0x50565031)||!writeFloat(stream,maximum))throw Error('PvP native HP extension encoding');
    writes++;
    send({event:'pvp_native_hp_source_written',uid:a.uid,maximum,current,original_fields_untouched:true,writes});
   }catch(error){disabled=true;send({event:'pvp_native_hp_source_disabled',reason:String(error),writes});}
 });
 const controller={active:()=>!disabled,dispose(){if(disposed)return;disposed=true;removeWriter();for(const h of hooks)h.detach();active.clear();disabled=true;if(globalThis.elsPvpHpSource===controller)delete globalThis.elsPvpHpSource;send({event:'pvp_native_hp_source_disabled',reason:'disposed',writes});}};
 globalThis.elsPvpHpSource=controller;
 send({event:'pvp_native_hp_source_ready',native_getters:['7D8B00','7D57A0'],game_vtable:'4183DD0',writes_to_actor:false});
 return controller;
}
