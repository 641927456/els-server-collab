// Read-only, bounded lifecycle evidence. Native pointers never leave this closure.
const lifecycleRows=new Map(),buffWatches=new Map(),visualWatches=new Map(),curtainCalls=new Map(),transitionCalls=new Map(),gameTickCalls=new Map();
let lifecycleIdentity=0;
function floatAt(p){const b=bytes(p,4),v=new DataView(b.buffer,b.byteOffset,4).getFloat32(0,true);if(!Number.isFinite(v))throw Error('lifecycle_float');return v;}
function lifecycleScene(row,game){
 if(!row.before||!gameAt(row.before).equals(game))throw Error('lifecycle_scene_changed');
 const owner=selectedUnit(),parent=readPointer(game.add(0x1440));
 if(owner.uid!==row.effect_uid||owner.unit.toString()!==row.unit_identity||parent.toString()!==row.parent_identity||parent.add(16).readS32()!==row.before.stage)throw Error('lifecycle_owner_changed');
 return{owner:owner.uid,scene:{handle_index:row.before.handle_index,handle_generation:row.before.handle_generation,stage:row.before.stage,part:readPointer(parent.add(8)).add(16).readS32()}};
}
function lifecycleEvent(row,component,status,extra={}){
 emitEffects(row,'lifecycle_observed',{component,status,event_thread:Process.getCurrentThreadId(),owner:row.effect_uid,site_rva:profile.lifecycle_sites.find(s=>s.role==='game_tick').rva,elapsed_ms:Math.max(0,Date.now()-row.lifecycle_at),...extra});
}
function startLifecycle(row){
 if(!row.before||!row.effect_uid||![0x115,0x30c,0xb7,0xbd].includes(row.kind))return;
 row.lifecycle_at||=Date.now();row.lifecycle_window_ms=row.kind===0x115?120000:30000;
 if(lifecycleRows.size>=16){lifecycleEvent(row,'collection','capacity_omitted');return;}
 lifecycleRows.set(row.trace_id,row);
 lifecycleEvent(row,'collection','window_started',{window_ms:row.lifecycle_window_ms});
}
function buffState(buff){
 if(!readable(buff,0x168))throw Error('lifecycle_buff');
 const result={template:buff.add(0x50).readS32(),mode:buff.add(0x58).readS32(),stack_path:buff.add(0x5c).readU8(),stack_decay:buff.add(0x60).readS32(),expired:!!buff.add(0x86).readU8(),caster:buff.add(0x130).readU64().toString(),factor:buff.add(0x160).readU32()};
 readPart(result,'stack_count',()=>{const n=treeFind(buff.add(0x70),0,28);return n?floatAt(n.add(32)):null;});
 readPart(result,'timers',()=>{const v=vectorAt(buff.add(0x20),8,16),timers=[];
  for(let i=0;i<v.count;i++){const p=readPointer(v.begin.add(i*8));
   if(!readPointer(p).equals(image.base.add(profile.buff_timer_vtable))){timers.push({index:i,unavailable:'timer_type_uncovered'});continue;}
   timers.push({index:i,remaining:encodedFloat(p.add(0x28)),budget:floatAt(p.add(0x40)),paused:!!p.add(0x44).readU8(),forced_expiry:!!p.add(0x20).readU8()});}
  return timers;});return result;
}
function borrowedActor(row,game){
 lifecycleScene(row,game);const actor=readPointer(readPointer(game.add(0x300))).sub(0x278),owner=selectedUnit();
 if(actor.toString()!==row.actor_identity||!readPointer(actor.add(0x1a3e0)).equals(owner.unit))throw Error('lifecycle_actor_changed');return actor;
}
function pollLifecycles(game){
 const now=Date.now();
 for(const [id,row]of lifecycleRows){
  if(now-row.lifecycle_at>row.lifecycle_window_ms){lifecycleEvent(row,'collection','window_ended',{reason:'observation_window_limit'});lifecycleRows.delete(id);continue;}
  if(now-(row.lifecycle_sample_at||0)<1000)continue;
  let context;try{context=lifecycleScene(row,game);}catch(error){
   // Another dungeon's tick must not invalidate this one. Retired handles are detected separately.
   try{gameAt(row.before);}catch(e){lifecycleEvent(row,'collection','scope_ended',{reason:'scene_retired'});lifecycleRows.delete(id);}continue;}
  row.lifecycle_sample_at=now;
  if(context.scene.part!==row.before.part&&(!row.targets.transition||context.scene.part!==row.targets.transition_part)){lifecycleEvent(row,'collection','scope_ended',{...context,reason:'part_changed'});lifecycleRows.delete(id);continue;}
  if(row.kind===0x30c){try{lifecycleEvent(row,'trigger','sample',{...context,snapshot:triggerState(game,row.targets.trigger)});}catch(error){lifecycleEvent(row,'trigger','read_unavailable',{...context,reason:'trigger_read'});}}
  if(row.kind===0x115){
   for(const [observation_id,w]of buffWatches){if(w.row!==row)continue;
    try{const actor=borrowedActor(row,game),v=vectorAt(actor.add(0x1858),8,128);let buff=null;
     for(let i=0;i<v.count;i++){const p=readPointer(v.begin.add(i*8));if(p.toString()===w.identity){buff=p;break;}}
     if(!buff){lifecycleEvent(row,'buff','removed',{...context,observation_id});buffWatches.delete(observation_id);continue;}
     const state=buffState(buff);
     if(state.template!==w.template||state.factor!==w.factor||state.caster!==w.caster){lifecycleEvent(row,'buff','identity_changed',{...context,observation_id});buffWatches.delete(observation_id);continue;}
     lifecycleEvent(row,'buff','sample',{...context,observation_id,snapshot:state});
    }catch(error){lifecycleEvent(row,'buff','read_unavailable',{...context,observation_id,reason:'buff_read'});buffWatches.delete(observation_id);}
   }
  }
 }
 for(const [observation_id,w]of buffWatches)if(!lifecycleRows.has(w.row.trace_id))buffWatches.delete(observation_id);
 for(const [key,w]of visualWatches)if(now-w.row.lifecycle_at>30000){lifecycleEvent(w.row,'door','window_ended',{observation_id:w.observation_id,reason:'observation_window_limit'});visualWatches.delete(key);}
}
function visualState(p){return{elapsed:floatAt(p.add(0x7e8)),duration:floatAt(p.add(0x7f0)),delay:floatAt(p.add(0x840)),paused:!!p.add(0xa74).readU8(),retired:!!p.add(0x847).readU8()};}
function installLifecycles(){
 for(const site of profile.lifecycle_sites)hooks.push(Interceptor.attach(image.base.add(site.rva),{
  onEnter:guarded(function(a){
   if(site.role==='game_tick'){if(!lifecycleRows.size&&!visualWatches.size)return;this.lifecycle_game=a[0];push(gameTickCalls,this.threadId,a[0]);return;}
   const row=current(dispatches,this.threadId);
   if(site.role==='part_transition'){
    const candidates=[];
    for(const pending of lifecycleRows.values()){
     if(!pending.targets.transition||Date.now()-pending.lifecycle_at>30000)continue;
     try{const context=lifecycleScene(pending,a[0]);if(context.scene.part===pending.targets.transition_part)candidates.push(pending);}catch(error){}
    }
    let matched=row&&[0xb7,0xbd].includes(row.kind)?row:candidates.length===1?candidates[0]:null;
    if(!matched)return;
    this.transition_call={row:matched,association:row===matched?'nested_dispatch':'unique_pending_selected_part'};
    push(transitionCalls,this.threadId,this.transition_call);return;
   }
   if(site.role==='buff_apply'){
    for(const [observation_id,w]of buffWatches)if(w.identity===a[0].toString()){lifecycleEvent(w.row,'buff','superseded',{observation_id,site_rva:site.rva});buffWatches.delete(observation_id);}
    if(!row||row.kind!==0x115||row.targets?.effect_owner!==row.effect_uid||!row.actor_identity||a[1].toString()!==row.actor_identity)return;
    const before=buffState(a[0]);this.buff_call={row,p:a[0],before};return;
   }
   if(site.role==='curtain_break'){
    // The break effect belongs to the actual part-transition call, not every gate-enable packet.
    const transition=current(transitionCalls,this.threadId),doorRow=transition?.row||row;
    if(!doorRow||![0xb7,0xbd].includes(doorRow.kind)||!doorRow.before||!readPointer(a[0]).equals(image.base.add(profile.curtain_vtable)))return;
    const game=gameAt(doorRow.before),parent=readPointer(game.add(0x1440)),stage=readPointer(parent.add(8));let member=false;
    for(const offset of [8,24]){const part=readPointer(stage.add(offset));if(part.isNull())continue;const v=vectorAt(part.add(24),8,64);for(let i=0;i<v.count;i++)if(readPointer(v.begin.add(i*8)).equals(a[0]))member=true;}
    if(!member)return;
    doorRow.lifecycle_at||=Date.now();this.curtain_call={row:doorRow,association:transition?.association||'nested_dispatch',geometry_index:a[0].add(8).readS32(),part_index:a[0].add(16).readS32()};
    push(curtainCalls,this.threadId,this.curtain_call);lifecycleEvent(doorRow,'door','break_enter',{association:this.curtain_call.association,geometry_index:this.curtain_call.geometry_index,part_index:this.curtain_call.part_index,site_rva:site.rva});return;
   }
   if(site.role==='visual_factory'){
    this.visual_factory_enter=true;const call=current(curtainCalls,this.threadId);if(!call)return;const engine=readPointer(image.base.add(profile.engine_global));
    if(!a[0].equals(readPointer(engine.add(0x110)))&&!a[0].equals(readPointer(engine.add(0x118))))return;
    this.visual_call={...call,manager_identity:a[0].toString(),manager_enabled:!!a[0].add(0x6c).readU8(),manager_limit:a[0].add(0xf8).readU32()};return;
   }
   if(site.role==='visual_tick'){
    const w=visualWatches.get(a[0].toString());if(!w||Date.now()-w.at<1000)return;
    if(Date.now()-w.row.lifecycle_at>30000){visualWatches.delete(a[0].toString());return;}
    try{const running=current(gameTickCalls,this.threadId);if(!running)return;
     if(!running.equals(gameAt(w.row.before)))return;lifecycleScene(w.row,running);
     const engine=readPointer(image.base.add(profile.engine_global));let member=false;
     for(const offset of [0x110,0x118]){const manager=readPointer(engine.add(offset));if(manager.toString()!==w.manager_identity)continue;
      const v=vectorAt(manager.add(0x80),8,4096);for(let i=0;i<v.count;i++)if(readPointer(v.begin.add(i*8)).equals(a[0]))member=true;}
     if(!member)throw Error('visual_membership');
    }catch(e){lifecycleEvent(w.row,'door','scope_ended',{observation_id:w.observation_id,reason:'visual_owner_changed'});visualWatches.delete(a[0].toString());return;}
    w.at=Date.now();this.visual_tick={w,p:a[0]};
   }
  }),
  onLeave:guarded(function(ret){
   if(this.lifecycle_game){try{pollLifecycles(this.lifecycle_game);}finally{pop(gameTickCalls,this.threadId,this.lifecycle_game);}}
   if(this.visual_tick){const {w,p}=this.visual_tick;const snapshot=visualState(p);
    lifecycleEvent(w.row,'door','sample',{site_rva:site.rva,observation_id:w.observation_id,geometry_index:w.geometry_index,part_index:w.part_index,snapshot});
    if(snapshot.retired)visualWatches.delete(p.toString());
   }
   if(this.buff_call){const {row,p,before}=this.buff_call;row.lifecycle_at||=Date.now();const snapshot=buffState(p),observation_id='buff-'+(++lifecycleIdentity);
    // Re-applying a live object supersedes its old attribution; never blame the old request for renewal.
    for(const [old,w]of buffWatches)if(w.identity===p.toString()){lifecycleEvent(w.row,'buff','superseded',{observation_id:old});buffWatches.delete(old);}
    if(buffWatches.size<32){buffWatches.set(observation_id,{row,identity:p.toString(),template:snapshot.template,factor:snapshot.factor,caster:snapshot.caster});lifecycleEvent(row,'buff','applied',{site_rva:site.rva,observation_id,owner:row.effect_uid,before,snapshot});}
    else lifecycleEvent(row,'buff','capacity_omitted');
   }
   if(this.visual_factory_enter&&!ret.isNull()&&visualWatches.has(ret.toString())){const old=visualWatches.get(ret.toString());lifecycleEvent(old.row,'door','identity_changed',{observation_id:old.observation_id,site_rva:site.rva});visualWatches.delete(ret.toString());}
   if(this.visual_call){const c=this.visual_call,observation_id='visual-'+(++lifecycleIdentity);lifecycleEvent(c.row,'door',ret.isNull()?'factory_empty':'created',{site_rva:site.rva,association:c.association,observation_id,geometry_index:c.geometry_index,part_index:c.part_index,manager_enabled:c.manager_enabled,manager_limit:c.manager_limit});
    if(!ret.isNull()&&visualWatches.size<64)visualWatches.set(ret.toString(),{...c,observation_id,at:0});else if(!ret.isNull())lifecycleEvent(c.row,'door','capacity_omitted',{observation_id});}
   if(this.curtain_call)pop(curtainCalls,this.threadId,this.curtain_call);
   if(this.transition_call)pop(transitionCalls,this.threadId,this.transition_call);
  })}));
}
