// Included inside the delivery observer closure; never invokes native code.
const effectWaits=new Map();let effectIdentity=0;
function readPointer(p){if(!readable(p,8))throw Error('effect_pointer');return p.readPointer();}
function vectorAt(p,stride,limit){
 if(!readable(p,16))throw Error('effect_vector');const b=readPointer(p),e=readPointer(p.add(8));
 if(e.compare(b)<0||e.compare(b.add(stride*limit))>0)throw Error('effect_vector_bound');
 const n=e.sub(b).toInt32()/stride;if(!Number.isInteger(n))throw Error('effect_vector_stride');
 if(n&&!readable(b,n*stride))throw Error('effect_vector_read');return{begin:b,count:n};
}
function treeFind(address,key,offset){
 const head=readPointer(address);if(!readable(head,40))throw Error('effect_tree_head');
 let p=readPointer(head.add(8));const visited=new Set();
 for(let i=0;i<64;i++){
  if(!readable(p,offset+4))throw Error('effect_tree_node');
  if(p.equals(head)||p.add(25).readU8())return null;
  const id=p.toString();if(visited.has(id))throw Error('effect_tree_cycle');visited.add(id);
  const value=p.add(offset).readS32(),cmp=Math.sign(value-key);
  if(cmp===0)return p;p=readPointer(p.add(cmp<0?16:0));
 }
 throw Error('effect_tree_depth');
}
function selectedUnit(){
 const e=readPointer(image.base.add(profile.engine_global)),roster=readPointer(e.add(0xc8)),unit=readPointer(roster.add(0xa0));
 if(!readable(unit,0x448))throw Error('effect_selected_owner');
 return{unit,uid:unit.add(0x48).readU64().toString()};
}
function gameAt(reference){
 const table=readPointer(image.base.add(profile.handle_table_global)),begin=readPointer(table),end=readPointer(table.add(8));
 const cell=begin.add(reference.handle_index*32);
 if(reference.handle_index<0||end.compare(cell.add(32))<0||!readable(cell,24)||!(cell.add(12).readU8()&1)||cell.add(16).readU32()!==reference.handle_generation)throw Error('effect_scene_retired');
 const game=readPointer(cell);if(!readable(game,0x1450)||!readPointer(game).equals(image.base.add(profile.dungeon_vtable)))throw Error('effect_game_identity');return game;
}
function lineAt(game){return readPointer(game.add(0x4d8));}
function itemState(owner,target){
 const container=owner.unit.add(0x440);if(target.group<0||target.group>29)throw Error('effect_item_group');
 const node=treeFind(container.add((target.group+9)*16),target.slot,32);
 if(!node)return{owner:owner.uid,present:false,group:target.group,slot:target.slot};
 const wrapper=readPointer(node.add(40)),item=readPointer(wrapper.add(8));
 if(!readable(item,24))throw Error('effect_item_record');
 return{owner:owner.uid,present:true,group:target.group,slot:target.slot,uid:item.readU64().toString(),template:item.add(8).readU32(),count:item.add(20).readU32()};
}
function questState(owner,target){
 const engine=readPointer(image.base.add(profile.engine_global)),manager=readPointer(engine.add(0x88));
 const active=treeFind(manager.add(0x88),target,32),done=treeFind(manager.add(0xa8),target,28);
 const result={owner:owner.uid,quest:target,active:!!active,completed:!!done,objectives:[]};
 if(active){
  const task=readPointer(active.add(40));if(!readable(task,40)||task.readS32()!==target)throw Error('effect_quest_identity');
  result.record_owner=task.add(8).readU64().toString();
  const v=vectorAt(task.add(16),8,64);
  for(let i=0;i<v.count;i++){const p=v.begin.add(i*8);result.objectives.push({id:p.readS32(),count:p.add(4).readU16(),completed:p.add(6).readU8()});}
 }
 return result;
}
function activeQuestIds(){
 const engine=readPointer(image.base.add(profile.engine_global)),manager=readPointer(engine.add(0x88)),head=readPointer(manager.add(0x88));
 const pending=[readPointer(head.add(8))],seen=new Set(),ids=[];
 while(pending.length){const p=pending.pop();if(!readable(p,40))throw Error('effect_quest_tree');
  if(p.equals(head)||p.add(25).readU8())continue;const key=p.toString();if(seen.has(key)||seen.size>=64)throw Error('effect_quest_tree_bound');seen.add(key);
  ids.push(p.add(32).readS32());pending.push(readPointer(p),readPointer(p.add(16)));
 }
 return ids;
}
function encodedFloat(p){
 if(!readable(p,24))throw Error('effect_float');const bits=(p.toUInt32()^p.add(8).readU32()^p.add(16).readU32())>>>0;
 const b=new ArrayBuffer(4),v=new DataView(b);v.setUint32(0,bits,true);const n=v.getFloat32(0,true);
 if(!Number.isFinite(n))throw Error('effect_nonfinite');return n;
}
function readPart(result,key,fn){try{result[key]=fn();}catch(error){(result.unavailable_fields||=[]).push(key+':'+String(error.message).slice(0,80));}}
function actorState(actor,owner){
 if(!readable(actor.add(0x1a3e0),8))throw Error('effect_actor');const unit=readPointer(actor.add(0x1a3e0));
 if(!unit.equals(owner.unit)||unit.add(0x48).readU64().toString()!==owner.uid)throw Error('effect_actor_owner');
 const result={owner:owner.uid};
 readPart(result,'hp',()=>encodedFloat(readPointer(readPointer(actor.add(0x1410)).add(0x40)).add(8)));
 readPart(result,'max_hp',()=>encodedFloat(readPointer(readPointer(actor.add(0x1410)).add(0x40)).add(32)));
 for(const [key,offset]of [['mp',8],['max_mp',32]])readPart(result,key,()=>{
  const stats=readPointer(actor.add(0x1410));if(!readPointer(stats).equals(image.base.add(profile.actor_stats_vtable)))throw Error('effect_stats_type');
  return encodedFloat(readPointer(stats.add(0x20)).add(offset));});
 readPart(result,'temporary_weapon',()=>{if(!readable(actor.add(0x1aea0),4))throw Error('effect_weapon');return actor.add(0x1aea0).readS32();});
 readPart(result,'buffs',()=>{const buffs=vectorAt(actor.add(0x1858),8,128),ids=[];
  for(let i=0;i<buffs.count;i++){const b=readPointer(buffs.begin.add(i*8));if(!readable(b.add(0x50),4))throw Error('effect_buff');ids.push(b.add(0x50).readS32());}return ids.sort((a,b)=>a-b);});
 readPart(result,'mount',()=>{const manager=readPointer(image.base.add(profile.mount_manager_global));
  if(!readable(manager.add(0x50),8))throw Error('effect_mount_manager');const selected=manager.add(0x50).readU64().toString(),v=vectorAt(manager.add(0x58),128,64);
  for(let i=0;i<v.count;i++){const p=v.begin.add(i*128);if(p.readU64().toString()===selected)return{uid:selected,stamina:encodedFloat(p.add(0x68))};}
  return{present:false};});
 return result;
}
function geometryState(map,lineId){
 const geometry=vectorAt(map.add(0x260),8,512),flags=[];let matches=0;
 for(let i=0;i<geometry.count;i++){const p=readPointer(geometry.begin.add(i*8));if(!readable(p,0x80))throw Error('effect_geometry');
  const id=p.add(0x7c).readS32();if(lineId!==undefined&&id!==lineId)continue;flags.push(id,p.add(8).readU8());matches++;}
 const encoded=new Uint8Array(flags.length*4),view=new DataView(encoded.buffer);flags.forEach((v,i)=>view.setInt32(i*4,v,true));
 return{geometry_count:matches,geometry_sha256:sha256(encoded),geometry_enabled:flags.filter((_,i)=>i%2&&flags[i]!==0).length,lines:flags.reduce((v,id,i)=>{if(!(i%2))v.push({id,enabled:flags[i+1]});return v;},[])};
}
function triggerState(game,target){
 const line=lineAt(game),map=readPointer(line.add(0x40));const active=vectorAt(map.add(0x3d0),4,512),rules=vectorAt(map.add(0x3e8),64,4096);
 const ids=[];for(let i=0;i<active.count;i++)ids.push(active.begin.add(i*4).readS32());
 const known=target>=0&&target<rules.count&&rules.begin.add(target*64+4).readS32()>=0;
 const result={trigger:target,definition_present:known,active:ids.includes(target),active_count:ids.length};
 readPart(result,'geometry',()=>geometryState(map));return result;
}
function gateState(game,target){
 const parent=readPointer(game.add(0x1440)),stage=parent.add(16).readS32();
 const head=readPointer(parent.add(0x38));let p=readPointer(head.add(8)),visited=new Set();
 for(let i=0;i<64;i++){
  if(!readable(p,46))throw Error('effect_gate_node');if(p.equals(head)||p.add(25).readU8())return{stage,target,known:false};
  const key=p.toString();if(visited.has(key))throw Error('effect_gate_cycle');visited.add(key);
  const a=p.add(28).readS32(),b=p.add(32).readS32(),cmp=a!==stage?Math.sign(a-stage):Math.sign(b-target);
  if(cmp===0)return{stage,target,known:true,passage_enabled:p.add(44).readU8()===1,paired_enabled:p.add(45).readU8()===1};
  p=readPointer(p.add(cmp<0?16:0));
 }
 throw Error('effect_gate_depth');
}
function inventoryTargets(payload,start){
 const view=new DataView(payload.buffer,payload.byteOffset,payload.byteLength);let pos=start;
 function take(n){if(n<0||pos+n>payload.length)throw Error('effect_inventory_wire');const p=pos;pos+=n;return p;}
 function count(max){const n=view.getUint32(take(4),false);if(n>max)throw Error('effect_inventory_count');return n;}
 const total=count(1024),items=[];
 for(let i=0;i<total;i++){
  const p=take(11),item={uid:view.getBigUint64(p,false).toString(),group:view.getUint8(p+8),slot:view.getInt16(p+9,false)};
  const begin=pos;
  for(const f of profile.inventory_fields){
   if(f.offset===0xd)take(4*count(4));
   else if(f.offset===0x25){if(count(33)!==33)throw Error('effect_inventory_options');for(let j=0;j<33;j++)take(4*count(64));}
   else if(f.offset===0x350){const n=count(256);if(n%2)throw Error('effect_inventory_utf16');take(n);}
   else if(f.offset===0x37d||f.offset===0x389){if(count(3)!==3)throw Error('effect_inventory_triple');take(12);}
   else take(f.size);
  }
  item.template=view.getUint32(begin,false);item.count=view.getUint32(begin+5,false);take(9);if(i<16)items.push(item);
 }
 return{items,items_omitted:Math.max(0,total-16)};
}
function effectTargets(v,payload){
 const view=new DataView(payload.buffer,payload.byteOffset,payload.byteLength),n=payload.length;
 if([0xad8,0x105,0x21a].includes(v.kind))return inventoryTargets(payload,v.kind===0x21a?4:0);
 const u64=o=>view.getBigUint64(o,false).toString(),i32=o=>view.getInt32(o,false);
 if((v.kind===0x114||v.kind===0x65f)&&n>=24)return{item:{uid:u64(4),group:view.getUint8(12),slot:view.getInt16(13,false),template:view.getUint32(15,false),count:view.getUint32(20,false)}};
 if(v.kind===0x115&&n===22)return{effect_owner:u64(0),template:i32(8)};
 if([0xb7,0xbd].includes(v.kind)&&n)return{transition:true,transition_part:view.getInt8(0)};
 if(v.kind===0xba&&n===1)return{gate:view.getInt8(0)};
 if(v.kind===0x30c&&n===4)return{trigger:i32(0)};
 if(v.kind===0xf5&&n>=8)return{quests:[i32(4)]};
 if(v.kind===0xf0&&n>=24)return{quests:[i32(0)]};
 if(v.kind===0xf3||v.kind===0x2b){
  let o=v.kind===0x2b?4:0;if(n<o+4)return{};const total=view.getUint32(o,false),quests=[];o+=4;if(total>256)return{};
  for(let i=0;i<total;i++){if(n<o+24)return{};const count=view.getUint32(o+20,false);if(count>64||n<o+24+count*7)return{};if(i<16)quests.push(i32(o));o+=24+count*7;}
  return{quests,quests_omitted:Math.max(0,total-16)};
 }
 return{};
}
function effectSnapshot(row){
 const owner=selectedUnit();if(row.effect_uid&&(owner.uid!==row.effect_uid||owner.unit.toString()!==row.unit_identity))throw Error('effect_owner_changed');
 const result={owner:owner.uid},target=row.targets||{};
 if(target.items){result.items=[];for(const item of target.items)try{result.items.push(itemState(owner,item));}catch(error){(result.unavailable_fields||=[]).push('item:'+item.group+':'+item.slot+':'+String(error.message).slice(0,60));}}
 if(target.item)readPart(result,'item',()=>itemState(owner,target.item));
 if(target.quests){result.quests=[];for(const q of target.quests){try{result.quests.push(questState(owner,q));}catch(error){(result.unavailable_fields||=[]).push('quest:'+q+':'+String(error.message).slice(0,60));}}}
 function sceneGame(){
  if(!row.before)throw Error('effect_scene_unavailable');const game=gameAt(row.before),parent=readPointer(game.add(0x1440));
  if((row.parent_identity&&parent.toString()!==row.parent_identity)||parent.add(16).readS32()!==row.before.stage)throw Error('effect_scene_changed');
  if((target.trigger!==undefined&&(lineAt(game).toString()!==row.line_identity||readPointer(parent.add(8)).add(16).readS32()!==row.before.part))||(target.effect_owner!==undefined&&readPointer(parent.add(8)).add(16).readS32()!==row.before.part))throw Error('effect_scene_changed');
  result.scene={handle_index:row.before.handle_index,handle_generation:row.before.handle_generation,stage:parent.add(16).readS32(),part:readPointer(parent.add(8)).add(16).readS32()};return game;
 }
 if(target.gate!==undefined)readPart(result,'gate',()=>gateState(sceneGame(),target.gate));
 if(target.trigger!==undefined)readPart(result,'trigger',()=>triggerState(sceneGame(),target.trigger));
 if(target.gate!==undefined)readPart(result,'geometry',()=>geometryState(readPointer(lineAt(sceneGame()).add(0x40))));
 if(target.effect_owner!==undefined)readPart(result,'actor',()=>{const game=sceneGame(),actor=readPointer(readPointer(game.add(0x300))).sub(0x278);
  if(row.actor_identity&&actor.toString()!==row.actor_identity)throw Error('effect_actor_changed');return actorState(actor,owner);});
 if(target.gate!==undefined||target.trigger!==undefined||target.effect_owner!==undefined){try{sceneGame();}catch(error){for(const key of ['gate','trigger','geometry','actor'])delete result[key];(result.unavailable_fields||=[]).push('scene:'+String(error.message).slice(0,80));}}
 const latest=selectedUnit();if(!latest.unit.equals(owner.unit)||latest.uid!==owner.uid)throw Error('effect_owner_changed');return result;
}
function snapshotResult(row){try{return{snapshot:effectSnapshot(row)};}catch(error){const reason=String(error.message);return{unavailable:/^effect_[a-z_]+$/.test(reason)?reason:'effect_read_failed'};}}
function emitEffects(row,phase,extra={}){emit(phase,{trace_id:row.trace_id,kind:row.kind,thread:row.thread,...extra});}
function beginEffects(row){
 row.effect_count=0;const targets=row.targets||{};
 if(!targets.item&&!targets.items&&!targets.quests&&targets.gate===undefined&&targets.trigger===undefined&&targets.effect_owner===undefined&&!targets.transition)return;
 try{const owner=selectedUnit();row.effect_uid=owner.uid;row.unit_identity=owner.unit.toString();
  if(row.kind===0x2b)try{row.targets.quests=Array.from(new Set([...activeQuestIds(),...(row.targets.quests||[])])).slice(0,64);}catch(error){row.quest_enumeration_unavailable=true;}
  if(row.before)try{row.parent_identity=readPointer(gameAt(row.before).add(0x1440)).toString();}catch(error){}
  if(targets.trigger!==undefined&&row.before)try{row.line_identity=lineAt(gameAt(row.before)).toString();}catch(error){}
  if(targets.effect_owner!==undefined&&row.before)try{const game=gameAt(row.before);row.actor_identity=readPointer(readPointer(game.add(0x300))).sub(0x278).toString();}catch(error){}
 }catch(error){row.effect_before={unavailable:'effect_owner_or_scene_unavailable'};return;}
 row.effect_before=snapshotResult(row);
}
function finishEffects(row){
 startLifecycle(row);
 if(!row.effect_before)return;
 emitEffects(row,'state_observed',{checkpoint:'dispatch_return',before:row.effect_before,...snapshotResult(row),native_effect_calls:row.effect_count,quest_enumeration_unavailable:!!row.quest_enumeration_unavailable});
 // Reacquire selected owner / generation at each checkpoint. No retained object is dereferenced.
 if(!row.effect_uid||(!row.effect_before.snapshot&&row.effect_before.unavailable==='effect_owner_or_scene_unavailable'))return;
 const copied={trace_id:row.trace_id,kind:row.kind,thread:row.thread,targets:row.targets,before:row.before,parent_identity:row.parent_identity,line_identity:row.line_identity,actor_identity:row.actor_identity,effect_uid:row.effect_uid,unit_identity:row.unit_identity,effect_before:row.effect_before};
 if(effectWaits.size>=32){omitted++;return;}
 const id=++effectIdentity;effectWaits.set(id,copied);
 for(const delay of [250,1200])setTimeout(()=>{
  if(!active||!effectWaits.has(id))return;
  emitEffects(copied,'state_observed',{checkpoint:delay===250?'after_250ms':'after_1200ms',...snapshotResult(copied)});
  if(delay===1200)effectWaits.delete(id);
 },delay);
}
function definitionState(p){
 const raw=bytes(p,232),offset=p.add(0xac).readU32();let effects=[];
 if(offset){const pool=readPointer(image.base.add(profile.effect_pool_global)),start=pool.add(offset);
  if(!readable(start,4))throw Error('effect_definition');const n=start.readU32();if(n>64)throw Error('effect_definition_bound');
  const v=bytes(start.add(4),n*24),dv=new DataView(v.buffer,v.byteOffset,v.byteLength);
  for(let i=0;i<n;i++)effects.push(Array.from({length:6},(_,j)=>dv.getUint32(i*24+j*4,true)));
 }
 return{definition_sha256:sha256(raw),effect_vector:effects,linked_factor:p.add(0xa8).readU32()};
}
function installEffects(){
 for(const site of profile.effect_sites){hooks.push(Interceptor.attach(image.base.add(site.rva),{
  onEnter:guarded(function(a){
   const row=current(dispatches,this.threadId);if(!row)return;this.effect=null;
   if(site.role==='item_effect'&&row.kind===0x115){
    const owner=selectedUnit();if(!row.targets||owner.uid!==row.targets.effect_owner||!readable(a[1],4)||a[1].readU32()!==row.targets.template)return;
    row.definition={};readPart(row.definition,'definition',()=>definitionState(a[1]));
    this.effect={row,actor:a[2],owner,before:(()=>{try{return actorState(a[2],owner);}catch(error){return{unavailable:'effect_actor_read'};}})(),site_rva:site.rva};
   }else if(site.role==='geometry_write'&&[0xba,0xb7,0xbd,0x30c].includes(row.kind)&&row.before){
    const game=gameAt(row.before),map=readPointer(lineAt(game).add(0x40));if(!a[0].equals(map))return;
    this.effect={row,game,map,line_id:a[1].toInt32(),requested_enabled:a[2].toUInt32()&255,site_rva:site.rva,before:geometryState(map,a[1].toInt32())};
   }else if(site.role==='trigger_apply'&&row.kind===0x30c&&row.before){
    const game=gameAt(row.before);if(!a[0].equals(lineAt(game)))return;
    this.effect={row,site_rva:site.rva,before:(()=>{try{return triggerState(game,row.targets.trigger);}catch(error){return{unavailable:'effect_trigger_read'};}})(),game};
   }else if(site.role==='gate_apply'&&row.kind===0xba&&row.before){
    const game=gameAt(row.before);if(!a[0].equals(game)||a[1].toInt32()!==row.targets.gate)return;
    this.effect={row,site_rva:site.rva,before:(()=>{try{return gateState(game,row.targets.gate);}catch(error){return{unavailable:'effect_gate_read'};}})(),game};
   }
  }),
  onLeave:guarded(function(){
   const effect=this.effect;if(!effect)return;const row=effect.row;
   let after;try{if(site.role==='item_effect')after=actorState(effect.actor,effect.owner);
   else if(site.role==='geometry_write')after=geometryState(effect.map,effect.line_id);
   else if(site.role==='trigger_apply')after=triggerState(effect.game,row.targets.trigger);
   else after=gateState(effect.game,row.targets.gate);}catch(error){after={unavailable:'effect_post_read'};}
   row.effect_count++;emitEffects(row,'effect_observed',{effect:site.role,site_rva:effect.site_rva,before:effect.before,after,line_id:effect.line_id,requested_enabled:effect.requested_enabled,definition:row.definition});
  })}));}
}
