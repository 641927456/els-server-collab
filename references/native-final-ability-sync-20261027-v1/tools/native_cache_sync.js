// Current owned Unit only. All arithmetic and effect refreshes remain native.
function installElsNativeCacheSync() {
 'use strict';
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__CACHE_SYNC_PINS__;
 const bytes=p=>Array.from(new Uint8Array(p.readByteArray(8)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const build=call(0x896870,'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const store=call(0x8a1400,'void',['pointer','float']);
 const myActor=call(0x8571d0,'pointer',['pointer']);
 const empty1=Memory.alloc(24),empty2=Memory.alloc(24),cp=Memory.alloc(4),dp=Memory.alloc(4);
 const records=new Map(),hooks=[];
 const completeBuild=call(0x888ca0,'pointer',['pointer','pointer','uint32','uint8','pointer']),constructExtended=call(0x997b00,'pointer',['pointer']),destroyExtended=call(0x996270,'void',['pointer']);
 const supplyFinalInputs=call(0x88d6b0,'void',['pointer','pointer','pointer']),supplyActorBase=call(0x18e8300,'void',['pointer','pointer']);
 const refreshActor=call(0x1c143e0,'void',['pointer']),currentHP=call(0x7d8b00,'float',['pointer']),maximumHP=call(0x7d57a0,'float',['pointer']),clampCurrentHP=call(0x19204f0,'void',['pointer','float']);let healthClamps=0;
 const floatBits=Memory.alloc(4);let abilityBusy=false,lastDungeon=null,abilityCalculations=0,abilityMs=0,abilityOutsideCacheMs=0,finalInputWrites=0,actorBaseWrites=0;
 function sevenAt(property){const key=(property.toUInt32()^property.add(8).readU32())>>>0;return Array.from({length:7},(_,i)=>{floatBits.writeU32((property.add(40+i*4).readU32()^key)>>>0);return floatBits.readFloat();});}
 function sameSeven(a,b){return a.every((v,i)=>v===b[i]);}
 function completeAbility(unit,side){const ext=Memory.alloc(0x880),out=Memory.alloc(52);constructExtended(ext);try{const returned=completeBuild(unit,out,side,0,ext),values=Array.from({length:7},(_,i)=>out.add(24+i*4).readFloat());if(!returned.equals(out)||!values.every(Number.isFinite)||values.some(v=>v<0)||values[0]<=0)throw Error('Original final ability result');return{out,input:out.add(24),values};}finally{destroyExtended(ext);}}
 function abilityInputs(unit,selected,actor,reason){
  if(disabled||abilityBusy||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread||!describe(unit,selected))return;
  abilityBusy=true;const started=Date.now(),outside=!busy;
  try{
   const naked=sevenAt(unit.add(0x220)),first=completeAbility(unit,0),second=selected.family===10?completeAbility(unit,1):first;
   if(!sameSeven(sevenAt(unit.add(0x268)),first.values)||!sameSeven(sevenAt(unit.add(0x2b0)),second.values)){
    supplyFinalInputs(unit.add(0x48),first.input,second.input);finalInputWrites++;
    if(!sameSeven(sevenAt(unit.add(0x268)),first.values)||!sameSeven(sevenAt(unit.add(0x2b0)),second.values))throw Error('Original final ability consumer mismatch');
    emit('ability_inputs_written',{uid:selected.uid,unit:unit.toString(),family:selected.family,klass:selected.klass,reason,sides:[first.values,second.values],original_producer:'888CA0',original_consumer:'88D6B0',health_setter_calls:0});
   }
   if(actor){
    if(!actor.readPointer().add(0x4f8).readPointer().equals(module.base.add(0x18e8300)))throw Error('Unqualified original Actor ability virtual');
    let side=unit.add(0x2f54).readS32();if(side===2)side=unit.add(0x2f50).readU8()===1?1:0;if(side!==0&&side!==1)throw Error('Original Actor ability side');
    const value=side===1?second:first;
    if(!sameSeven(sevenAt(actor.add(0x1698)),value.values)){
     const beforeHealth={current:currentHP(actor),maximum:maximumHP(actor)};
     supplyActorBase(actor,value.input);actorBaseWrites++;
     // Original full attribute receiver BAA6F0 refreshes native dirty components
     // then limits current HP through Actor virtual2F0 only when HP exceeds max.
     // Match that sequence; raising max HP never invokes a current-HP setter.
     refreshActor(actor);const maximum=maximumHP(actor),current=currentHP(actor);let clamped=false;
     if(!Number.isFinite(maximum)||maximum<=0||!Number.isFinite(current))throw Error('Original refreshed health range');
     if(current>maximum){if(!actor.readPointer().add(0x2f0).readPointer().equals(module.base.add(0x19204f0)))throw Error('Unqualified original HP clamp virtual');clampCurrentHP(actor,maximum);healthClamps++;clamped=true;}
     const afterHealth={current:currentHP(actor),maximum:maximumHP(actor)};
     if(afterHealth.current>afterHealth.maximum||afterHealth.current>beforeHealth.current)throw Error('Original health clamp/preservation mismatch');
     if(!sameSeven(sevenAt(actor.add(0x1698)),value.values))throw Error('Original Actor base ability mismatch');
     emit('ability_actor_base_written',{uid:selected.uid,unit:unit.toString(),actor:actor.toString(),family:selected.family,klass:selected.klass,reason,side,seven:value.values,original_consumer:'18E8300',original_refresh:'1C143E0',original_full_refresh_reference:'BAA6F0/BAA949..BAA9BF',health_before:beforeHealth,health_after:afterHealth,original_current_HP_clamp:clamped,health_setter_calls:clamped?1:0});
    }
   }
   if(!sameSeven(sevenAt(unit.add(0x220)),naked))throw Error('Original naked input changed during final ability supply');
  }catch(error){disabled=true;emit('disabled',{reason:String(error),writes,final_input_writes:finalInputWrites,actor_base_writes:actorBaseWrites,original_HP_clamps:healthClamps});}
  finally{const elapsed=Date.now()-started;abilityCalculations++;abilityMs+=elapsed;if(outside)abilityOutsideCacheMs+=elapsed;abilityBusy=false;}
 }

 let busy=false,disabled=false,processing=0,nativeBuildDepth=0,mainThread=0,identity='',frame=0,lastTick=0,calculations=0,writes=0,totalMs=0,lastMetrics=0;
 const emit=(event,row={})=>send({event:'native_cache_sync_'+event,timestamp:Date.now(),...row});
 function own(){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const manager=engine.add(0xc8).readPointer();if(manager.isNull())return null;
  const unit=manager.add(0xa0).readPointer();if(unit.isNull())return null;
  const uid=unit.add(0x48).readU64().toString(),definition=unit.add(0x29c0).readPointer();
  if(uid==='0'||definition.isNull())return null;
  const family=definition.readS32(),klass=unit.add(0x58).readU16();
  if(family<1||family>15||klass===0)return null;
  return {unit,uid,family,klass};
 }
 function describe(unit,selected){
  if(unit.isNull()||unit.add(0x48).readU64().toString()!==selected.uid||unit.add(0x58).readU16()!==selected.klass)return null;
  const definition=unit.add(0x29c0).readPointer();if(definition.isNull()||definition.readS32()!==selected.family)return null;
  return {...selected,unit};
 }
 function remember(unit,selected,kind){
  const value=describe(unit,selected);if(!value)return null;
  const key=unit.toString();let record=records.get(key);
  if(!record||record.uid!==value.uid||record.klass!==value.klass){record={...value,kind,seen:0,lastFrame:-1,lastCP:null,lastCache:null};records.set(key,record);}
  if(record.lastFrame!==frame){record.seen++;record.lastFrame=frame;}
  return record;
 }
 function nativePower(record,side){
  cp.writeFloat(0);dp.writeFloat(0);
  // C2C700 passes LuCiel side in EDX, with R8B=0 in both calls.
  build(record.unit,side,0,empty1,empty2,cp,dp,1,-1,ptr(0));
  const power={combat:cp.readFloat(),defense:dp.readFloat()};
  if(!Object.values(power).every(Number.isFinite)||power.combat<0||power.combat>4294967040||power.defense<0)throw Error('Native power result range');
  if([...new Uint8Array(empty1.readByteArray(24)),...new Uint8Array(empty2.readByteArray(24))].some(x=>x!==0))throw Error('Native borrowed input vectors changed');
  return power;
 }
 function sync(record,reason){
  if(disabled||busy||processing||nativeBuildDepth||record.seen<2||Process.getCurrentThreadId()!==mainThread)return;
  const selected=own();if(!selected||!describe(record.unit,selected))return;
  busy=true;const start=Date.now();
  try{
   if(record.kind==='selected'&&!lastDungeon)abilityInputs(record.unit,selected,null,'stable-original-Field');
   const first=nativePower(record,0),second=record.family===10?nativePower(record,1):null;
   const value=second?Math.max(first.combat,second.combat):first.combat;
   const current=record.unit.add(0x3048).readFloat();
   if(record.lastCP!==value||record.lastCache!==current){
    const checked=own();if(!checked||!describe(record.unit,checked))throw Error('Native power owner changed during calculation');
    store(record.unit,value);
    const cache=record.unit.add(0x3048).readFloat();if(!Number.isFinite(cache)||cache<0||cache>4294967040)throw Error('Original power cache result range');
    record.lastCache=cache;record.lastCP=value;writes++;
    emit('written',{uid:record.uid,unit:record.unit.toString(),family:record.family,klass:record.klass,kind:record.kind,reason,combat:value,defense:first.defense,side_combat:second?[first.combat,second.combat]:[first.combat],before:current,after:cache});
   }
  }catch(error){disabled=true;emit('disabled',{reason:String(error),writes});}
  finally{calculations++;totalMs+=Date.now()-start;busy=false;}
 }
 function tick(state){
  if(disabled||busy||processing)return;
  const thread=Process.getCurrentThreadId();if(mainThread&&thread!==mainThread)return;mainThread=thread;
  if(!state&&Date.now()-lastTick<8)return;lastTick=Date.now();frame++;
  try{
   if(state&&!state.isNull()&&state.readPointer().equals(module.base.add(0x41bfd28)))lastDungeon=state;
   const selected=own();if(!selected){records.clear();identity='';return;}
   const key=selected.uid+':'+selected.unit+':'+selected.klass;
   if(key!==identity){records.clear();identity=key;}
   const active=[remember(selected.unit,selected,'selected')];
   if(state&&!state.isNull()&&state.readPointer().equals(module.base.add(0x41bfd28))&&state.add(0x2d0).readS32()===2&&state.add(0x620).readU8()===0){
    const actor=myActor(state);if(!actor.isNull()){const unit=actor.add(0x1a3e0).readPointer();if(!unit.equals(selected.unit))active.push(remember(unit,selected,'actor'));}
   }
   for(const record of active)if(record)sync(record,'stable-native-frame');
   if(Date.now()-lastMetrics>=10000){lastMetrics=Date.now();emit('metrics',{calculations,writes,total_ms:totalMs,main_thread:mainThread,ready_units:active.filter(x=>x&&x.seen>=2).length,ability_calculations:abilityCalculations,ability_total_ms:abilityMs,ability_outside_cache_ms:abilityOutsideCacheMs,final_input_writes:finalInputWrites,actor_base_writes:actorBaseWrites,original_HP_clamps:healthClamps});}
  }catch(error){disabled=true;emit('disabled',{reason:String(error),writes});}
 }
 // Avoid nesting a new producer inside an original producer already in progress.
 for(const producer of [0x896870,0x888ca0])hooks.push(Interceptor.attach(module.base.add(producer),{onEnter(){nativeBuildDepth++;},onLeave(){nativeBuildDepth--;}}));
 // Complete full-role projection before the original Unit clone/Actor initialization.
 hooks.push(Interceptor.attach(module.base.add(0x87caf0),{onEnter(a){this.finalUserInfo=a[0];},onLeave(){
  if(disabled||busy||abilityBusy||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread)return;
  const selected=own();if(!selected||!this.finalUserInfo.equals(selected.unit.add(0x48)))return;const record=records.get(selected.unit.toString());if(record&&record.seen>=2)abilityInputs(selected.unit,selected,null,'original-full-UserInfo-return');
 }}));
 // Native player update invokes 1C143E0 itself after this entry. Only supply its
 // qualified base inputs; leave current HP, max-HP refresh, buffs and clamps native.
 hooks.push(Interceptor.attach(module.base.add(0x1bdc220),{onEnter(a){
  if(disabled||busy||abilityBusy||processing||nativeBuildDepth||!lastDungeon||Process.getCurrentThreadId()!==mainThread)return;
  try{if(!lastDungeon.readPointer().equals(module.base.add(0x41bfd28))||lastDungeon.add(0x2d0).readS32()!==2||lastDungeon.add(0x620).readU8()!==0)return;const actor=myActor(lastDungeon);if(actor.isNull()||!actor.equals(a[0]))return;const selected=own();if(!selected)return;const unit=actor.add(0x1a3e0).readPointer();if(describe(unit,selected))abilityInputs(unit,selected,actor,'before-original-Actor-refresh');}catch(error){disabled=true;emit('disabled',{reason:String(error),writes});}
 }}));
 // Frame updates are invoked by verified host callbacks.
 // These are the verified non-stack Unit+3048 reads in the pinned image.
 // Resolve the exact native Unit at the read, before the consumer uses its cache.
 for(const [r,register]of [[0x89188f,'rdi'],[0x117e5ea,'rax'],[0x1c0f996,'rax'],[0x1c27227,'rcx'],[0x363ed6f,'rcx']]){
  hooks.push(Interceptor.attach(module.base.add(r),{onEnter(){
   if(disabled||busy||processing||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread)return;
   const record=records.get(this.context[register].toString());if(record)sync(record,'original-cache-consumer');
  }}));
 }
 emit('ready',{native_calculator:'896870',native_setter:'8A1400',native_final_ability_producer:'888CA0',native_final_ability_consumers:['88D6B0','18E8300'],native_Actor_refresh_retained:true,current_HP_updates:'original19204F0 only when original refreshed max is exceeded',new_healing_or_damage_formula:false,client_executable_sha256:__CACHE_SYNC_EXE_SHA__,hooks:hooks.length});
 return {begin(){processing++;},end(){processing--;lastDungeon=null;tick(null);},frame(game){tick(game);}};
}
