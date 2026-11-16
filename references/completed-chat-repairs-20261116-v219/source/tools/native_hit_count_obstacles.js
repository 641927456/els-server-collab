// Preserve the native hit-count and repeatable switch state machines.
// Original Lua callbacks own counters, platform movement and collision changes.
let elsHitCountObstacles=null;
function installElsHitCountObstacles(){
 'use strict';
 if(elsHitCountObstacles)return elsHitCountObstacles;
 const m=Process.getModuleByName('x2_dx11.exe'),pins=__HIT_COUNT_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error('Hit-count obstacle native identity '+r);
 const native=(r,ret,args)=>new NativeFunction(m.base.add(r),ret,args,{exceptions:'propagate'});
 const getGame=native(0x159670,'pointer',['pointer']);
 const byUID=native(0x1aa4a40,'pointer',['pointer','int']);
 const getInt=native(0x7d5560,'int',['pointer','int']);
 const getHP=native(0x7d8b00,'float',['pointer']);
 const getState=native(0x16e14a0,'pointer',['pointer']);
 const switchSources={6:8321,7:8322,8:8322,9:8323,10:8324,11:8324,12:8325,32:8326,33:8327,34:8328};
 const switchStates=new Set(['DEVILDOM4_TRICKYHOUSE_LINE_TRIGGER_LINE_START_WAIT','DEVILDOM4_TRICKYHOUSE_LINE_TRIGGER_LINE_WAIT','DEVILDOM4_TRICKYHOUSE_LINE_TRIGGER_DAMAGE']);
 let active=true,protectedChanges=0,switchProtectedChanges=0,originalDelta;
 function qualified(actor){
  if(actor.isNull()||!actor.readPointer().equals(m.base.add(0x41ea620)))return false;
  const script=actor.add(0x19e20).readPointer();if(script.isNull())return false;
  const template=script.readS32();if(template!==8184&&(template<8321||template>8328))return false;
  const game=getGame(m.base.add(0x478cb88));
  if(game.isNull()||!game.readPointer().equals(m.base.add(0x41bfd28))||game.add(0x2d0).readS32()!==2)return false;
  const parent=game.add(0x1440).readPointer();if(parent.isNull())return false;
  const definition=parent.readPointer();if(definition.isNull())return false;
  const map=definition.add(0x18).readS32(),stage=parent.add(0x10).readS32();
  const key=actor.add(0x3d0).readU64().toString();
  const pillar=map===34720&&stage===1&&template===8184&&(key==='18'||key==='63');
  const repeatable=map===34770&&stage===3&&switchSources[key]===template;
  if(!pillar&&!repeatable)return false;
  const slot=actor.add(0x3c8).readS32(),begin=game.add(0x378).readPointer(),end=game.add(0x380).readPointer();
  if(!(slot>=0&&slot<80&&end.sub(begin).toInt32()===80*8&&begin.add(slot*8).readPointer().equals(actor)&&byUID(game,Number(key)).equals(actor)))return false;
  if(pillar){const count=getInt(actor,0);return count>=0&&count<50;}
  const state=getState(actor);
  return !state.isNull()&&switchStates.has(state.readCString());
 }
 const deltaReplacement=new NativeCallback((actor,delta,minimum)=>{
  // Qualify at the common HP write: positive damage still reaches original Lua.
  // A floor does not revive zero-HP objects or retain explicit dying states.
  if(active&&delta<0&&qualified(actor)&&getHP(actor)>0&&minimum<1){
   minimum=1;protectedChanges++;
   if(actor.add(0x19e20).readPointer().readS32()!==8184)switchProtectedChanges++;
  }
  originalDelta(actor,delta,minimum);
 },'void',['pointer','float','float']);
 const trampoline=Interceptor.replaceFast(m.base.add(0x16e3a00),deltaReplacement);
 originalDelta=new NativeFunction(trampoline,'void',['pointer','float','float'],{exceptions:'propagate'});
 elsHitCountObstacles={active:()=>active,protectedChanges:()=>protectedChanges,switchProtectedChanges:()=>switchProtectedChanges,stop(){
  if(!active)return;active=false;Interceptor.revert(m.base.add(0x16e3a00));
 }};
 send({event:'native_hit_count_obstacles_ready',native_counter_and_break_retained:true,scope:'34720 stage1 original 8184 sources; 34770 stage3 original repeatable switch sources in interaction states',EXE_KOM_modified:false});
 return elsHitCountObstacles;
}
installElsHitCountObstacles();

// Keep unrepresentable HP increments in the native scalar's double remainder.
// Damage calculation, admission, HP writes/clamps and peer sync remain native.
let elsNpcHpPrecision=null;
function installElsNpcHpPrecision(){
 'use strict';
 if(elsNpcHpPrecision)return elsNpcHpPrecision;
 const m=Process.getModuleByName('x2_dx11.exe'),pins=__NPC_HP_PRECISION_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error('NPC HP precision native identity '+r);
 const native=(r,t,a)=>new NativeFunction(m.base.add(r),t,a,{exceptions:'propagate'});
 const getGame=native(0x159670,'pointer',['pointer']);
 const playerCount=native(0x1aa5ac0,'int',['pointer']);
 const actorState=native(0x7d5a20,'int',['pointer']);
 const hp=native(0x7d8b00,'float',['pointer']),maximumHP=native(0x7d57a0,'float',['pointer']);
 const reference=m.base.add(0x478cb88),slots=new Map();
 let active=true,epoch='',corrections=0,absoluteResets=0,originalDelta,originalSet;
 function frame(){
  const generation=reference.readU64().toString(),game=getGame(reference);
  if(game.isNull()||!game.readPointer().equals(m.base.add(0x41bfd28))||game.add(0x2d0).readS32()!==2)return null;
  const local=game.add(0x2d8).readU64().toString(),master=game.add(0x2e0).readU64().toString();
  if(local==='0'||local!==master)return null;
  const players=playerCount(game);
  if(players<2)return null;
  const begin=game.add(0x378).readPointer(),end=game.add(0x380).readPointer();
  if(begin.isNull()||end.sub(begin).toInt32()!==80*8||reference.readU64().toString()!==generation)return null;
  const key=generation+':'+game;
  if(epoch!==key){slots.clear();epoch=key;}
  return{game,begin,key};
 }
 function bound(actor,current){
  if(actor.isNull()||!actor.readPointer().equals(m.base.add(0x41ea620))||actor.add(0x3c4).readS32()!==1)return null;
  const f=current||frame();if(!f)return null;
  const slot=actor.add(0x3c8).readS32();
  if(slot<0||slot>=80||!f.begin.add(slot*8).readPointer().equals(actor))return null;
  const manager=actor.add(0x1410).readPointer();if(manager.isNull())return null;
  const scalar=manager.add(0x40).readPointer();if(scalar.isNull())return null;
  const record={actor,slot,manager,scalar,uid:actor.add(0x3d0).readU64().toString(),epoch:f.key};
  slots.set(slot,record);return record;
 }
 const deltaReplacement=new NativeCallback((actor,delta,minimum)=>{
  const b=active?bound(actor):null;
  if(!b){originalDelta(actor,delta,minimum);return;}
  const state=actorState(actor);
  if(delta>0&&state===4){originalDelta(actor,delta,minimum);return;}
  const before=hp(actor),maximum=maximumHP(actor),remainder=b.scalar.add(0x68),carry=remainder.readDouble();
  if(![before,maximum,delta,minimum,carry].every(Number.isFinite))throw Error('NPC HP precision non-finite native scalar');
  if(carry===0&&(delta===0||Math.fround(before+delta)!==before)){originalDelta(actor,delta,minimum);return;}
  const total=carry+delta;
  if(state===4&&total>0){remainder.writeDouble(total);return;}
  remainder.writeDouble(0);
  originalDelta(actor,Math.fround(total),minimum);
  const after=hp(actor),requested=before+total;
  remainder.writeDouble(requested<=minimum||requested>=maximum?0:total-(after-before));
  corrections++;
 },'void',['pointer','float','float']);
 const setReplacement=new NativeCallback((manager,value)=>{
  let target=null,before=0;
  const f=active&&slots.size?frame():null;
  if(f)for(const saved of slots.values()){
   if(!saved.manager.equals(manager))continue;
   // Read the live slot first: a saved actor may already have been retired.
   const actor=f.begin.add(saved.slot*8).readPointer();
   if(!actor.equals(saved.actor))break;
   const b=bound(actor,f);
   if(b&&b.manager.equals(manager)&&b.scalar.equals(saved.scalar)&&b.uid===saved.uid&&b.epoch===saved.epoch){
    target=b;before=hp(actor);
   }
   break;
  }
  originalSet(manager,value);
  // An identical absolute snapshot is a native no-op, not a new HP baseline.
  if(target&&hp(target.actor)!==before){target.scalar.add(0x68).writeDouble(0);absoluteResets++;}
 },'void',['pointer','float']);
 const deltaTrampoline=Interceptor.replaceFast(m.base.add(0x19e2a90),deltaReplacement);
 originalDelta=new NativeFunction(deltaTrampoline,'void',['pointer','float','float'],{exceptions:'propagate'});
 try{
  const setTrampoline=Interceptor.replaceFast(m.base.add(0x854170),setReplacement);
  originalSet=new NativeFunction(setTrampoline,'void',['pointer','float'],{exceptions:'propagate'});
 }catch(error){Interceptor.revert(m.base.add(0x19e2a90));throw error;}
 elsNpcHpPrecision={status:()=>({active,corrections,absoluteResets,boundSlots:slots.size}),stop(){
  if(!active)return;active=false;
  Interceptor.revert(m.base.add(0x854170));Interceptor.revert(m.base.add(0x19e2a90));slots.clear();
 }};
 send({event:'native_npc_hp_precision_ready',scope:'current_shared_dungeon_native_host_NPC',native_HP_write_and_clamps:true,EXE_KOM_modified:false});
 return elsNpcHpPrecision;
}
installElsNpcHpPrecision();
