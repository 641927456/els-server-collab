// Preserve the native hit-count obstacle state machine through lethal hits.
// The original Lua callback owns the counter, Break state and collision change.
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
 let active=true,protectedChanges=0,originalDelta;
 function qualified(actor){
  if(actor.isNull()||!actor.readPointer().equals(m.base.add(0x41ea620)))return false;
  const script=actor.add(0x19e20).readPointer();if(script.isNull()||script.readS32()!==8184)return false;
  const game=getGame(m.base.add(0x478cb88));
  if(game.isNull()||!game.readPointer().equals(m.base.add(0x41bfd28))||game.add(0x2d0).readS32()!==2)return false;
  const parent=game.add(0x1440).readPointer();if(parent.isNull()||parent.add(0x10).readS32()!==1)return false;
  const definition=parent.readPointer();if(definition.isNull()||definition.add(0x18).readS32()!==34720)return false;
  const key=actor.add(0x3d0).readU64().toString();if(key!=='18'&&key!=='63')return false;
  const slot=actor.add(0x3c8).readS32(),begin=game.add(0x378).readPointer(),end=game.add(0x380).readPointer();
  return slot>=0&&slot<80&&end.sub(begin).toInt32()===80*8&&begin.add(slot*8).readPointer().equals(actor)&&byUID(game,Number(key)).equals(actor);
 }
 const deltaReplacement=new NativeCallback((actor,delta,minimum)=>{
  // The native NPC update also changes HP outside the damage callback.
  // Qualify the current actor at the shared write, so both paths keep Lua alive.
  if(active&&delta<0&&qualified(actor)){
   const count=getInt(actor,0);
   if(count>=0&&count<50&&getHP(actor)>0&&minimum<1){minimum=1;protectedChanges++;}
  }
  originalDelta(actor,delta,minimum);
 },'void',['pointer','float','float']);
 const trampoline=Interceptor.replaceFast(m.base.add(0x16e3a00),deltaReplacement);
 originalDelta=new NativeFunction(trampoline,'void',['pointer','float','float'],{exceptions:'propagate'});
 elsHitCountObstacles={active:()=>active,protectedChanges:()=>protectedChanges,stop(){
  if(!active)return;active=false;Interceptor.revert(m.base.add(0x16e3a00));
 }};
 send({event:'native_hit_count_obstacles_ready',native_counter_and_break_retained:true,scope:'34720 stage1 original 8184 sources',EXE_KOM_modified:false});
 return elsHitCountObstacles;
}
installElsHitCountObstacles();
