// Current owned Unit only. All arithmetic and effect refreshes remain native.
function installElsNativeCacheSync() {
 'use strict';
 const installGroupWear=prepareElsGroupWearSync();let groupWear=null;
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
 function completeAbility(unit,side){const ext=Memory.alloc(0x880),out=Memory.alloc(52);constructExtended(ext);try{const returned=completeBuild(unit,out,side,0,ext),values=Array.from({length:7},(_,i)=>out.add(24+i*4).readFloat());if(!returned.equals(out)||!values.every(Number.isFinite)||values.some(v=>v<0)||values[0]<=0)throw Error('Original final ability result '+JSON.stringify({unit:String(unit),uid:unit.add(0x48).readU64().toString(),side,returned:String(returned),out:String(out),values,naked:sevenAt(unit.add(0x220)),final:sevenAt(unit.add(0x268))}));return{out,input:out.add(24),values};}finally{destroyExtended(ext);}}
 function abilityInputs(unit,selected,actor,reason,strict=false,provided=null){
  if(disabled||abilityBusy||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread||!describe(unit,selected))return;
  abilityBusy=true;const started=Date.now(),outside=!busy;
  try{
   const naked=sevenAt(unit.add(0x220)),first=provided?provided.first:completeAbility(unit,0),second=provided?provided.second:(selected.family===10?completeAbility(unit,1):first);
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
  }catch(error){if(strict)throw error;disabled=true;emit('disabled',{reason:String(error),writes,final_input_writes:finalInputWrites,actor_base_writes:actorBaseWrites,original_HP_clamps:healthClamps});}
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
  if(groupWear)groupWear.invalidateUnit(this.finalUserInfo.sub(0x48));
  if(disabled||busy||abilityBusy||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread)return;
  const selected=own();if(!selected||!this.finalUserInfo.equals(selected.unit.add(0x48)))return;const record=records.get(selected.unit.toString());if(record&&record.seen>=2)abilityInputs(selected.unit,selected,null,'original-full-UserInfo-return');
 }}));
 // Native player update invokes 1C143E0 itself after this entry. Only supply its
 // qualified base inputs; leave current HP, max-HP refresh, buffs and clamps native.
 hooks.push(Interceptor.attach(module.base.add(0x1bdc220),{onEnter(a){
  if(disabled||busy||abilityBusy||processing||nativeBuildDepth||!lastDungeon||Process.getCurrentThreadId()!==mainThread)return;
  try{if(!lastDungeon.readPointer().equals(module.base.add(0x41bfd28))||lastDungeon.add(0x2d0).readS32()!==2||lastDungeon.add(0x620).readU8()!==0)return;const actor=myActor(lastDungeon);if(actor.isNull())return;if(!actor.equals(a[0])){if(groupWear)groupWear.refreshPeer(lastDungeon,a[0]);return;}const selected=own();if(!selected)return;const unit=actor.add(0x1a3e0).readPointer();if(describe(unit,selected))abilityInputs(unit,selected,actor,'before-original-Actor-refresh');}catch(error){disabled=true;emit('disabled',{reason:String(error),writes});}
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
 function peerReady(game){return !disabled&&!busy&&!abilityBusy&&!nativeBuildDepth&&!processing&&mainThread===Process.getCurrentThreadId()&&game.readPointer().equals(module.base.add(0x41bfd28))&&game.add(0x2d0).readS32()===2&&game.add(0x620).readU8()===0;}
 function ownerState(game){
  if(!peerReady(game))return null;
  const selected=own();if(!selected)return null;const actor=myActor(game);if(actor.isNull())return null;
  const unit=actor.add(0x1a3e0).readPointer();if(!describe(unit,selected))return null;
  return{selected,actor,unit};
 }
 const api={begin(){processing++;},end(){processing--;lastDungeon=null;tick(null);if(groupWear)groupWear.frame(null);},frame(game){tick(game);if(groupWear)groupWear.frame(game);},peerReady,failed(){return disabled;},
 ownerUID(game){const selected=own();return selected?selected.uid:null;},
 capture(game){const owned=ownerState(game);if(!owned)return null;const{selected,actor,unit}=owned;
  busy=true;try{
   abilityInputs(unit,selected,actor,'committed-owner-report',true);
   const record={unit,family:selected.family},first=nativePower(record,0),second=selected.family===10?nativePower(record,1):null;
   store(unit,second?Math.max(first.combat,second.combat):first.combat);
   return{uid:selected.uid,first:sevenAt(unit.add(0x268)),second:sevenAt(unit.add(0x2b0)),combat:unit.add(0x3048).readFloat()};
  }finally{busy=false;}
 },peer(game,actor,provided){
  if(!peerReady(game))throw Error('Group wear native ability scene');
  if(!provided||![...provided.first,...provided.second,provided.combat].every(v=>Number.isFinite(v)&&v>=0)||provided.first[0]<=0||provided.second[0]<=0)throw Error('Group wear supplied native final sides');
  busy=true;try{
  const unit=actor.add(0x1a3e0).readPointer(),definition=unit.add(0x29c0).readPointer(),selected={unit,uid:unit.add(0x48).readU64().toString(),klass:unit.add(0x58).readU16(),family:definition.readS32()};
  const ownSelected=own();if(!ownSelected||selected.uid===ownSelected.uid)throw Error('Group wear foreign ability owner');
  const material=Memory.alloc(56);[...provided.first,...provided.second].forEach((v,i)=>material.add(i*4).writeFloat(v));
  abilityInputs(unit,selected,actor,'committed-peer-equipment',true,{first:{values:provided.first,input:material},second:{values:provided.second,input:material.add(28)}});
  store(unit,provided.combat);
  return{first:provided.first,second:provided.second,combat:provided.combat,base:sevenAt(actor.add(0x1698))};
  }finally{busy=false;}
 },peerCurrent(actor,snapshot){const unit=actor.add(0x1a3e0).readPointer();return sameSeven(sevenAt(unit.add(0x268)),snapshot.first)&&sameSeven(sevenAt(unit.add(0x2b0)),snapshot.second)&&sameSeven(sevenAt(actor.add(0x1698)),snapshot.base);
 }};
 groupWear=installGroupWear(api);return api;
}

// Independent native relationship source after one complete original55B.
// This installer is registered at the existing verified bootstrap. Scene/thread
// authority is the same complete original UserInfo55B invocation, not a prior frame.
function installElsRelationSourceSync() {
 'use strict';
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__RELATION_SOURCE_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Native relation source identity '+r);
 const refresh=new NativeFunction(module.base.add(0x903010),'void',['pointer'],{exceptions:'propagate'});
 const hooks=[],stacks=new Map();let epoch=0,transitionDepth=0,activeInvocations=0,restoring=false,disabled=false,disposed=false,calls=0,rejections=0,records=0;
 const emit=(event,row={})=>{if(records++<128)send({event:'native_relation_source_'+event,timestamp:Date.now(),...row});};
 function pointer(p){return p.toString();}
 function auth(){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const carrier=engine.add(0xc8).readPointer();if(carrier.isNull())return null;
  const account=carrier.readU64().toString();if(account==='0'||account==='18446744073709551615')return null;
  const send=engine.add(0xc0).readPointer(),network=engine.add(0x250).readPointer(),dispatcher=module.base.add(0x4817e80).readPointer();
  if(send.isNull()||network.isNull()||dispatcher.isNull())return null;
  const features=module.base.add(0x4817e50).readPointer();
  return{engine,carrier,account,send,network,dispatcher,features};
 }
 function authKey(a){return[pointer(a.engine),pointer(a.carrier),a.account,pointer(a.send),pointer(a.network),pointer(a.dispatcher),pointer(a.features)].join(':');}
 // The original SceneManager owns the current Stage. This is not a ready
 // flag. Cold kind5 is the original1378790 State, before Field14 exists.
 function scene(a){
  const kind=a.dispatcher.add(0x160).readS32(),state=a.dispatcher.add(0x168).readPointer();
  if(state.isNull())return null;
  const table=state.readPointer(),phase=state.add(0x18).readS32();if(phase===3)return null;
  const types={5:0x41dcee0,11:0x4180308,14:0x42eb158};
  if(types[kind]===undefined||!table.equals(module.base.add(types[kind])))return null;
  return[pointer(a.dispatcher),kind,pointer(state),pointer(table),phase].join(':');
 }

 function body(buffer){
  const start=buffer.add(8).readPointer(),end=buffer.add(16).readPointer(),capacity=buffer.add(24).readPointer();
  if(start.isNull()||end.compare(start)<0||capacity.compare(end)<0)return null;
  if(end.sub(start).compare(ptr(1048576))>0)return null;
  const length=end.sub(start).toUInt32();
  // A technical observation bound only; larger packets retain original handling.
  if(length<8||length>1048576)return null;
  const raw=hex(start,length),uid=uint64('0x'+raw.slice(0,16)).toString();
  if(uid==='0'||uid==='18446744073709551615')return null;
  return{start,end,capacity,length,raw,uid};
 }
 function relation(a,uid){
  const manager=a.engine.add(0x618).readPointer();if(manager.isNull())return null;
  const data=manager.add(8).readPointer();if(data.isNull())return null;
  // Only the independently qualified couple900 source. No marriage/friend or
  // feature51-only entitlement is enabled by this isolated candidate.
  const kind=data.readS32();if(kind!==1)return null;
  const peer=data.add(8).readU64().toString();if(peer==='0'||peer===uid||peer==='18446744073709551615')return null;
  return[pointer(manager),pointer(data),hex(data,32)].join(':');
 }
 function roster(a,uid){
  const first=a.carrier.add(0xa8).readPointer(),end=a.carrier.add(0xb0).readPointer(),capacity=a.carrier.add(0xb8).readPointer();
  if(first.isNull()||end.compare(first)<0||capacity.compare(end)<0)return null;
  if(end.sub(first).compare(ptr(8192))>0)return null;
  const span=end.sub(first).toUInt32();if(span%8)return null;
  let unit=null;
  for(let n=0;n<span;n+=8){const p=first.add(n).readPointer();if(p.isNull())return null;if(p.add(0x48).readU64().toString()===uid){if(unit!==null)return null;unit=p;}}
  if(unit===null||unit.add(0x50).readU64().toString()!==a.account)return null;
  const klass=unit.add(0x58).readU16(),definition=unit.add(0x29c0).readPointer();if(!klass||definition.isNull())return null;
  const family=definition.readS32();if(family<1||family>15)return null;
  const skill=unit.add(0x7c8);if(skill.add(0x1d00).readU32()!==klass)return null;
  return{unit,skill,klass,family,definition,first,end,capacity};
 }
 function native900Source(skill){
  // The already reviewed original main-source reader. This observes a native
  // source byte; it never supplies a rank or substitutes for903010.
  const head=skill.add(0x1d98).readPointer(),size=skill.add(0x1da0).readU64().toNumber();
  if(head.isNull()||size>8192)return null;
  let node=head.add(8).readPointer();const seen=new Set();
  for(let n=0;n<128;n++){
   if(node.isNull()||node.add(0x19).readU8()!==0)return null;
   const key=node.toString();if(seen.has(key))return null;seen.add(key);
   const id=node.add(0x1c).readS32();
   if(id===900)return{head,node,rank:node.add(0x20).readU8()};
   node=node.add(id<900?16:0).readPointer();
  }
  return null;
 }
 function capture(buffer,entrySP,caller){
  if(disabled||disposed||restoring||transitionDepth||activeInvocations||!caller.equals(module.base.add(0x1382b6b)))return null;
  const a=auth(),packet=body(buffer);if(a===null||packet===null||buffer.add(32).readU32()!==0)return null;
  const stage=scene(a);if(stage===null)return null;
  const owner=roster(a,packet.uid),rel=relation(a,packet.uid);if(owner===null||rel===null)return null;
  const source=native900Source(owner.skill);if(source===null||![1,2].includes(source.rank))return null;
  const selected=a.carrier.add(0xa0).readPointer();if(!selected.isNull()&&!selected.equals(owner.unit))return null;
  return{a,auth:authKey(a),packet,owner,source,rel,stage,epoch,buffer,entrySP,witnessed:false,parsed:false,done:false,invalid:false,thread:Process.getCurrentThreadId()};
 }
 function current(load,selected){
  if(disabled||disposed||restoring||transitionDepth||activeInvocations!==1||load.invalid||load.done||epoch!==load.epoch||Process.getCurrentThreadId()!==load.thread)return false;
  const a=auth();if(a===null||authKey(a)!==load.auth||scene(a)!==load.stage||relation(a,load.packet.uid)!==load.rel)return false;
  const r=roster(a,load.packet.uid);if(r===null)return false;
  for(const k of ['unit','skill','definition','first','end','capacity'])if(!r[k].equals(load.owner[k]))return false;
  if(r.klass!==load.owner.klass||r.family!==load.owner.family)return false;
  if(selected&&!a.carrier.add(0xa0).readPointer().equals(r.unit))return false;
  const p=body(load.buffer);return p!==null&&p.raw===load.packet.raw&&p.start.equals(load.packet.start)&&p.end.equals(load.packet.end)&&p.capacity.equals(load.packet.capacity);
 }
 // One shared original Scene transition producer, including before the
 // first Field frame. It ONLY invalidates in-flight work, including a State
 // pointer ABA. No particular transition caller must precede cold55B.
 try{
 hooks.push(Interceptor.attach(module.base.add(0x74c470),{
  onEnter(args){
   this.relationTransition=false;
   try{const live=module.base.add(0x4817e80).readPointer();if(live.isNull()||!args[0].equals(live))return;
    this.relationTransition=true;epoch++;transitionDepth++;
   }catch(error){disabled=true;emit('disabled',{reason:String(error)});}
  },onLeave(){if(this.relationTransition){epoch++;transitionDepth--;}}
 }));
 hooks.push(Interceptor.attach(module.base.add(0x13a34f0),{
  onEnter(args){
   this.relationThread=this.threadId;const list=stacks.get(this.threadId)||[];
   // A native nested handler invalidates the outer adaptation as well.
   if(activeInvocations)for(const items of stacks.values())for(const old of items)if(old)old.invalid=true;
   let load=null;
   try{if(!list.length)load=capture(args[4],this.context.rsp,this.returnAddress);}catch(error){rejections++;}
   this.relationLoad=load;list.push(load);stacks.set(this.threadId,list);activeInvocations++;
  },
  onLeave(){
   const list=stacks.get(this.relationThread),load=this.relationLoad;
   try{
    if(!list||list.length!==1||list[0]!==load||load===null||!load.parsed||!current(load,true))return;
    if(load.buffer.add(32).readU32()!==load.packet.length)return;
    load.done=true;restoring=true;
    try{const before=native900Source(load.owner.skill);refresh(load.owner.skill);calls++;const after=native900Source(load.owner.skill);emit('restored',{uid:load.packet.uid,account:load.a.account,unit:pointer(load.owner.unit),skill_manager:pointer(load.owner.skill),native_producer:'903010',prior_native_source_byte:load.source.rank,before_native_source_byte:before===null?null:before.rank,after_native_source_byte:after===null?null:after.rank,scene:load.stage,thread:load.thread,epoch:load.epoch});}
    finally{restoring=false;}
   }catch(error){disabled=true;emit('disabled',{reason:String(error),native_calls:calls});}
   finally{if(list){list.pop();if(!list.length)stacks.delete(this.relationThread);}else stacks.delete(this.relationThread);activeInvocations=Math.max(0,activeInvocations-1);}
  }
 }));
 // Read-only original parser result. All failed reader branches join here with
 // AL=0; the final DAED10's real success value is otherwise retained in AL.
 hooks.push(Interceptor.attach(module.base.add(0x13a3763),function(){
  const list=stacks.get(this.threadId);if(!list||list.length!==1)return;const load=list[0];if(load===null)return;
  try{
   if(load.witnessed){load.invalid=true;return;}load.witnessed=true;
   if(!current(load,false)||!this.context.rsp.equals(load.entrySP.sub(0x158))||!this.context.rbp.equals(load.entrySP.sub(0x58))||!this.context.rdi.equals(load.buffer))return;
   if((this.context.rax.toUInt32()&255)!==1||this.context.rsp.add(0x60).readU64().toString()!==load.packet.uid||load.buffer.add(32).readU32()!==load.packet.length)return;
   load.parsed=true;
  }catch(error){load.invalid=true;rejections++;}
 }));
 emit('registered',{hooks:hooks.length,sites:['13A34F0 entry/return','13A3763 read-only parser result','74C470 invalidation only'],thread_authority:'same original1382280 ->13A34F0 invocation',packet_authority:'original caller1382B6B and complete parser result',before_first_Field_frame:'native kind5/vtable41DCEE0 accepted with authenticated same Unit and pre-existing native couple900 source; no prior frame or synthetic ready'});
 }catch(error){
  disabled=true;disposed=true;
  for(const hook of hooks){try{hook.detach();}catch(detachError){/* Continue cleanup of every own listener. */}}
  hooks.length=0;stacks.clear();throw error;
 }
 return{status(){return{native_calls:calls,rejections,epoch,transition_depth:transitionDepth,disabled,disposed,active_invocations:activeInvocations,active_threads:stacks.size};},dispose(){disposed=true;epoch++;for(const h of hooks)h.detach();hooks.length=0;stacks.clear();}};
}
