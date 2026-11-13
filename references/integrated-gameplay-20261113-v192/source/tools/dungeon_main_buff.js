// Install only during the existing owned startup callback, before Actor updates.
let elsDungeonMainBuffSupport=null,elsDungeonMainBuffAttempted=false;
function installElsDungeonMainBuff(){
 'use strict';
 if(elsDungeonMainBuffSupport)return elsDungeonMainBuffSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),profile=__DUNGEON_MAIN_BUFF_PROFILE__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 function original(){
  if(Process.arch!=='x64'||Process.pointerSize!==8)throw Error('Dungeon main buff architecture');
  for(const [r,h]of Object.entries(profile.bodies))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Dungeon main buff native identity '+r);
  for(const [slot,rva]of Object.entries(profile.timer_virtuals))if(!module.base.add(profile.time_vtable+(+slot)).readPointer().equals(module.base.add(rva)))throw Error('Dungeon main buff timer virtual '+slot);
 }
 original();
 const site=module.base.add(profile.update),restoreSite=module.base.add(profile.restore);
 const originalSlot=Memory.alloc(Process.pointerSize),restoreSlot=Memory.alloc(Process.pointerSize);
 const archenemySlot=Memory.alloc(Process.pointerSize),archenemyModSlot=Memory.alloc(Process.pointerSize);
 const archenemySite=module.base.add(profile.archenemy),archenemyModSite=module.base.add(profile.archenemy_mod);
 originalSlot.writePointer(site);restoreSlot.writePointer(restoreSite);
 archenemySlot.writePointer(archenemySite);archenemyModSlot.writePointer(archenemyModSite);
 const code=new CModule(__DUNGEON_MAIN_BUFF_C__,{
  game_handle:module.base.add(profile.game_handle),dungeon_vtable:module.base.add(profile.dungeon_vtable),
  time_vtable:module.base.add(profile.time_vtable),original_slot:originalSlot,restore_slot:restoreSlot,
  archenemy_slot:archenemySlot,archenemy_mod_slot:archenemyModSlot,
  main_effect:module.base.add(profile.main_effect),set_effect_lifetime:module.base.add(profile.set_effect_lifetime),
  valid_game:module.base.add(profile.valid_game),resolve_game:module.base.add(profile.resolve_game),
  my_actor:module.base.add(profile.my_actor)
 });
 const armSite=module.base.add(profile.arm_site);
 const armStub=buildElsDungeonArmStub(armSite,module.base.add(profile.arm_resume),code.hold_arm,profile.arm_block);
 let state='prepared';const applied=[];
 const redirects=[[site,code.update_main,originalSlot],[restoreSite,code.restore_main,restoreSlot],
                  [armSite,armStub,null],[archenemySite,code.create_archenemy,archenemySlot],
                  [archenemyModSite,code.create_archenemy_mod,archenemyModSlot]];
 function restoreOriginal(){
  const errors=[];
  for(let i=applied.length-1;i>=0;i--){try{Interceptor.revert(applied[i]);}catch(error){errors.push('revert '+applied[i]+': '+error);}}
  try{Interceptor.flush();}catch(error){errors.push('flush: '+error);}
  try{original();}catch(error){errors.push('identity: '+error);}
  if(errors.length)throw Error(errors.join('; '));
 }
 const api={code,armStub,originalSlot,restoreSlot,archenemySlot,archenemyModSlot,profile,state:()=>state,
  // Quiescent owner-only shutdown. No hot toggle or public RPC is exposed.
  stop(){
   if(state==='stopped')return;
   if(state!=='active')throw Error('Dungeon main buff restore state '+state);
   try{restoreOriginal();state='stopped';}
   catch(error){state='failed';throw error;}
  }};
 // Native executable storage survives failed rollback until owner process exit.
 elsDungeonMainBuffSupport=api;
 try{
  for(const [target,replacement,slot]of redirects){const trampoline=Interceptor.replaceFast(target,replacement);applied.push(target);if(slot)slot.writePointer(trampoline);}
  Interceptor.flush();state='active';
 }catch(error){
  if(applied.length){try{restoreOriginal();state='stopped';}
   catch(rollbackError){state='failed';throw Error(String(error)+'; rollback: '+rollbackError);}}
  else state='stopped';
  throw error;
 }
 try{send({event:'dungeon_main_buff_ready',main_factors:profile.factors,original_file_modified:false,
       independent_passives_extended:false,enemy_states_extended:false});}
 catch(error){api.reportError=String(error);}
 return api;
}
function installElsDungeonMainBuffOnce(){
 if(elsDungeonMainBuffAttempted)return elsDungeonMainBuffSupport;
 elsDungeonMainBuffAttempted=true;
 try{return installElsDungeonMainBuff();}
 catch(error){
  const state=elsDungeonMainBuffSupport?elsDungeonMainBuffSupport.state():'unprepared';
  try{send({event:state==='failed'?'dungeon_main_buff_partial_failure':'dungeon_main_buff_disabled',reason:String(error),
            state,original_file_modified:false});}
  catch(reportError){installElsDungeonMainBuff.reportError=String(reportError);}
  return null;
 }
}
