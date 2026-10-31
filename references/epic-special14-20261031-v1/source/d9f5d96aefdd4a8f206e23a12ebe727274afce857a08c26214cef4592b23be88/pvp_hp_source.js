// Read the original owned Actor maximum HP only while its original9E is built.
function installElsPvpHpSource(){
 'use strict';
 if(globalThis.elsPvpHpSource)return globalThis.elsPvpHpSource;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__PVP_HP_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('PvP HP source identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const actorOf=call(0x8571d0,'pointer',['pointer']),maximumHP=call(0x7d57a0,'float',['pointer']),currentHP=call(0x7d8b00,'float',['pointer']);
 const writeInt=call(0x3b6dbd0,'bool',['pointer','int']),writeFloat=call(0x3b6dcc0,'bool',['pointer','float']);
 const active=new Map(),hooks=[];let disabled=false,writes=0;
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
 hooks.push(Interceptor.attach(module.base.add(0xda2f50),{
  onEnter(args){
   this.bound=active.get(Process.getCurrentThreadId());this.stream=args[0];this.dto=args[1];
   if(disabled||!this.returnAddress.equals(module.base.add(0xc690a1)))this.bound=null;
  },
  onLeave(result){
   if(!this.bound||(result.toInt32()&255)!==1)return;
   try{
    const a=this.bound,b=capture(a.game);if(!same(a,b))throw Error('PvP report owner changed');
    const current=currentHP(a.actor),maximum=maximumHP(a.actor),reported=this.dto.readFloat();
    if(!Number.isFinite(current)||!Number.isFinite(maximum)||maximum<=0||current<0||current>maximum||reported!==current)throw Error('PvP original report health changed');
    if(!same(a,capture(a.game)))throw Error('PvP report generation changed');
    if(!writeInt(this.stream,0x50565031)||!writeFloat(this.stream,maximum))throw Error('PvP native HP extension encoding');
    writes++;
    send({event:'pvp_native_hp_source_written',uid:a.uid,maximum,current,original_fields_untouched:true,writes});
   }catch(error){disabled=true;send({event:'pvp_native_hp_source_disabled',reason:String(error),writes});}
  }
 }));
 const controller={active:()=>!disabled,dispose(){for(const h of hooks)h.detach();active.clear();disabled=true;if(globalThis.elsPvpHpSource===controller)delete globalThis.elsPvpHpSource;}};
 globalThis.elsPvpHpSource=controller;
 send({event:'pvp_native_hp_source_ready',native_getters:['7D8B00','7D57A0'],game_vtable:'4183DD0',writes_to_actor:false});
 return controller;
}
