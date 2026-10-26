// Current owned Unit only. All arithmetic and effect refreshes remain native.
function installElsNativeCacheSync() {
 'use strict';
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__CACHE_SYNC_PINS__;
 const bytes=p=>Array.from(new Uint8Array(p.readByteArray(8)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'steal'});
 const build=call(0x896870,'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const store=call(0x8a1400,'void',['pointer','float']);
 const myActor=call(0x8571d0,'pointer',['pointer']);
 const empty1=Memory.alloc(24),empty2=Memory.alloc(24),cp=Memory.alloc(4),dp=Memory.alloc(4);
 const records=new Map(),hooks=[];
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
   const selected=own();if(!selected){records.clear();identity='';return;}
   const key=selected.uid+':'+selected.unit+':'+selected.klass;
   if(key!==identity){records.clear();identity=key;}
   const active=[remember(selected.unit,selected,'selected')];
   if(state&&!state.isNull()&&state.readPointer().equals(module.base.add(0x41bfd28))&&state.add(0x2d0).readS32()===2&&state.add(0x620).readU8()===0){
    const actor=myActor(state);if(!actor.isNull()){const unit=actor.add(0x1a3e0).readPointer();if(!unit.equals(selected.unit))active.push(remember(unit,selected,'actor'));}
   }
   for(const record of active)if(record)sync(record,'stable-native-frame');
   if(Date.now()-lastMetrics>=10000){lastMetrics=Date.now();emit('metrics',{calculations,writes,total_ms:totalMs,main_thread:mainThread,ready_units:active.filter(x=>x&&x.seen>=2).length});}
  }catch(error){disabled=true;emit('disabled',{reason:String(error),writes});}
 }
 // Avoid nesting a new producer inside an original producer already in progress.
 hooks.push(Interceptor.attach(module.base.add(0x896870),{onEnter(){nativeBuildDepth++;},onLeave(){nativeBuildDepth--;}}));
 // Frame updates are invoked by verified host callbacks.
 // These are the verified non-stack Unit+3048 reads in the pinned image.
 // Resolve the exact native Unit at the read, before the consumer uses its cache.
 for(const [r,register]of [[0x89188f,'rdi'],[0x117e5ea,'rax'],[0x1c0f996,'rax'],[0x1c27227,'rcx'],[0x363ed6f,'rcx']]){
  hooks.push(Interceptor.attach(module.base.add(r),{onEnter(){
   if(disabled||busy||processing||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread)return;
   const record=records.get(this.context[register].toString());if(record)sync(record,'original-cache-consumer');
  }}));
 }
 emit('ready',{native_calculator:'896870',native_setter:'8A1400',new_damage_formula:false,client_executable_sha256:__CACHE_SYNC_EXE_SHA__,hooks:hooks.length});
 return {begin(){processing++;},end(){processing--;tick(null);},frame(game){tick(game);}};
}
