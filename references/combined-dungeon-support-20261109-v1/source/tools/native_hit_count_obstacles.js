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
