// Preserve the native hit-count obstacle state machine through lethal hits.
// The original Lua callback owns the counter, Break state and collision change.
let elsHitCountObstacles=null;
function installElsHitCountObstacles(){
 'use strict';
 if(elsHitCountObstacles)return elsHitCountObstacles;
 const m=Process.getModuleByName('x2_dx11.exe'),pins={"1414768": "40534883ec20488bd9488d15", "27937344": "4c8b81780300004533c94c8b", "8213856": "85d2780b4863c28b848114a0", "8227584": "488b81101400004885c07421", "24001024": "40534883ec500f297424408d", "23679568": "488bc4488958185556574154"};
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error('Hit-count obstacle native identity '+r);
 const native=(r,ret,args)=>new NativeFunction(m.base.add(r),ret,args,{exceptions:'propagate'});
 const getGame=native(0x159670,'pointer',['pointer']);
 const byUID=native(0x1aa4a40,'pointer',['pointer','int']);
 const getInt=native(0x7d5560,'int',['pointer','int']);
 const getHP=native(0x7d8b00,'float',['pointer']);
 const scopes=new Map();let active=true,protectedChanges=0,originalDelta;
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
  const stack=scopes.get(Process.getCurrentThreadId()),scope=stack&&stack[stack.length-1];
  if(active&&delta<0&&scope&&scope.actor&&scope.actor.equals(actor)){
   const count=getInt(actor,0);
   if(count>=0&&count<50&&getHP(actor)>0&&minimum<1){minimum=1;protectedChanges++;}
  }
  originalDelta(actor,delta,minimum);
 },'void',['pointer','float','float']);
 const trampoline=Interceptor.replaceFast(m.base.add(0x16e3a00),deltaReplacement);
 originalDelta=new NativeFunction(trampoline,'void',['pointer','float','float'],{exceptions:'propagate'});
 const damageHook=Interceptor.attach(m.base.add(0x1695250),{
  onEnter(args){
   this.thread=Process.getCurrentThreadId();this.scope={actor:active&&qualified(args[0])?args[0]:null};
   let stack=scopes.get(this.thread);if(!stack){stack=[];scopes.set(this.thread,stack);}stack.push(this.scope);
  },
  onLeave(){const stack=scopes.get(this.thread);stack.pop();if(!stack.length)scopes.delete(this.thread);}
 });
 elsHitCountObstacles={active:()=>active,protectedChanges:()=>protectedChanges,stop(){
  if(!active)return;active=false;damageHook.detach();Interceptor.revert(m.base.add(0x16e3a00));
 }};
 send({event:'native_hit_count_obstacles_ready',native_counter_and_break_retained:true,scope:'34720 stage1 original 8184 sources',EXE_KOM_modified:false});
 return elsHitCountObstacles;
}
installElsHitCountObstacles();
