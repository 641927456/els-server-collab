let noahVerifiedSenderReady=false;
// Pinned updated DX11 build. RVA candidates independently checked by native
// readers/callers in analysis/client-6c6b5180/decompiled before this probe.
const verifiedPrefixes=__VERIFIED_PREFIXES__;
const enterTown=__ENTER_TOWN__;
const enterDungeon=__ENTER_DUNGEON__;
const npcCandidate=__NPC_CANDIDATE__;
const autoReturn=__AUTO_RETURN__;
const gateIdentityTest=__GATE_IDENTITY_TEST__;
const populationTest=__POPULATION_TEST__;
const lightweightPlay=__LIGHTWEIGHT_PLAY__;
const game=Process.getModuleByName('x2_dx11.exe');
const sockets=new Set(),pending=new Map();let initialized=false,invoked=false;
let characterReady=0,channelsReady=0,selected=false,chosen=false;
let loadedCharacter=false;
let selectedCharacterUid=null;
let lastCharacterFrame=0;
let updatedCommand=null,lastFieldFrame=0,npcCatalogRead=false;
let npcOfflineProbeDone=false,npcInputBufferTemplate=null;
let dungeonGame=ptr(0),dungeonActor=ptr(0),inputProbe=null,inputDelivered=false,lastDungeonFrame=0;
const createdNpcs=new Map();
let returnGame=ptr(0),fixtureSeenAlive=false,fixtureDeadAt=0,fixtureEndRequested=false;
let physicalKeyConversions=null,timeSyncReceived=0;
// Cache wrappers once; allocating them on every game frame caused avoidable work.
const nativeCalls=new Map();
function nativeCall(r,t,a){const key=r+':'+t+':'+a.join(',');let f=nativeCalls.get(key);if(!f){f=new NativeFunction(game.base.add(r),t,a);nativeCalls.set(key,f);}return f;}
function actorSample(p){return {actor:p.toString(),vtable:p.readPointer().sub(game.base).toString(),xyz:[0,4,8].map(o=>p.add(0x19188+o).readFloat()),hp:nativeCall(0x7d8b00,'float',['pointer'])(p),state:nativeCall(0x15ae30,'int',['pointer'])(p)};}
function npcSample(p){return {actor:p.toString(),vtable:p.readPointer().sub(game.base).toString(),xyz:[0,4,8].map(o=>p.add(0x19c04+o).readFloat()),hp:nativeCall(0x7d8b00,'float',['pointer'])(p),initial_action:p.add(0x19ea4).readS32()};}
function receiveCommand(){recv('updated_probe_command',m=>{if(enterDungeon)updatedCommand=m.payload;receiveCommand();});}
if(enterDungeon)receiveCommand();
function note(x){send({timestamp:Date.now(),thread:Process.getCurrentThreadId(),...x});}
function packet(socket,direction,p,n){if(n>0&&n<=65536)note({event:'bootstrap_data',socket,direction,length:n,hex:Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('')});}
const w=Process.getModuleByName('ws2_32.dll');
for(const api of ['connect','WSAConnect'])Interceptor.attach(w.getExportByName(api),{
 onEnter(a){const p=a[1];if(a[2].toInt32()<16||p.readU16()!==2||((p.add(2).readU8()<<8)|p.add(3).readU8())!==9400)return;this.socket=a[0].toString();sockets.add(this.socket);this.addr=Memory.alloc(16);this.addr.writeByteArray([2,0,0x4b,0xc8,127,0,0,1,0,0,0,0,0,0,0,0]);a[1]=this.addr;note({event:'redirect_bootstrap',socket:this.socket,local_host:'127.0.0.1',local_port:19400});}
});
function finish(x,n){for(const b of x.buffers){const len=Math.min(n,b.n);packet(x.socket,x.direction,b.p,len);n-=len;if(n<=0)break;}}
if(!lightweightPlay){
for(const api of ['WSASend','WSARecv'])Interceptor.attach(w.getExportByName(api),{
 onEnter(a){const socket=a[0].toString();if(!sockets.has(socket))return;const buffers=[];for(let i=0;i<Math.min(a[2].toUInt32(),32);i++)buffers.push({n:a[1].add(16*i).readU32(),p:a[1].add(16*i+8).readPointer()});this.item={socket,buffers,direction:api==='WSASend'?'out':'in'};this.count=a[3];this.overlapped=a[5];if(!this.overlapped.isNull())pending.set(this.overlapped.toString(),this.item);},
 onLeave(r){if(this.item&&r.toInt32()===0&&!this.count.isNull()){finish(this.item,this.count.readU32());pending.delete(this.overlapped.toString());}}
});
Interceptor.attach(Process.getModuleByName('kernel32.dll').getExportByName('GetQueuedCompletionStatus'),{
 onEnter(a){this.count=a[1];this.overlapped=a[3];},onLeave(r){if(r.toInt32()&& !this.overlapped.isNull()){const key=this.overlapped.readPointer().toString(),item=pending.get(key);if(item){finish(item,this.count.readU32());pending.delete(key);}}}
});
}
let tries=0;
const timer=setInterval(()=>{
 tries++;
 if(Object.entries(verifiedPrefixes).every(([r,h])=>Array.from(new Uint8Array(game.base.add(Number(r)).readByteArray(8)),v=>v.toString(16).padStart(2,'0')).join('')===h)){
  clearInterval(timer);
  let lastBootstrapState='';
  Interceptor.attach(game.base.add(0x6845e0),{onEnter(a){this.session=a[0];},onLeave(){const ready=this.session.add(0xe8).readU8();initialized ||= ready===1;const key=this.session.add(0xea).readU16(),state=ready+':'+key;if(state!==lastBootstrapState){lastBootstrapState=state;note({event:'bootstrap_session_state',initialized:ready,key});}}});
  Interceptor.attach(game.base.add(0x682d80),{onEnter(a){note({event:'client_event_send',event_id:a[1].add(16).readU32(),event_kind:a[1].add(0x34).readU16()});}});
  Interceptor.attach(game.base.add(0x30f6730),{
   onEnter(a){this.login=a[0];},onLeave(){
    if(!initialized||invoked)return;invoked=true;
    try{const data=game.base.add(0x4817e50).readPointer();
     for(const [o,value] of [[0x60,'local'],[0x80,'test']]){const p=data.add(o);if(p.add(24).readU64().toNumber()!==7||p.add(16).readU64().toNumber()!==0)throw new Error('Login fields are not fresh and empty');p.writeUtf16String(value);p.add(16).writeU64(value.length);}
     data.add(0xb0).writeU8(0);note({event:'local_identity_native_request',official_credentials:false});
     nativeCall(0x30f8e00,'void',['pointer'])(this.login);
    }catch(e){note({event:'local_identity_error',error:String(e)});}
   }
  });
  Interceptor.attach(game.base.add(0x2b4eaa0),{
   onEnter(a){this.data=a[1];this.stream=a[0].add(8).readPointer();this.start=this.stream.add(0x20).readU32();},
   onLeave(r){const ok=r.toInt32()&255,end=this.stream.add(0x20).readU32(),size=this.stream.add(16).readPointer().sub(this.stream.add(8).readPointer()).toInt32();note({event:'character_list_payload_parsed',ok,result:this.data.readS32(),end,start:this.start,size});if(ok&&this.data.readS32()===0&&end===size)characterReady=Date.now();}
  });
  if(enterTown){
   Interceptor.attach(game.base.add(0x13a11f0),{onEnter(a){this.state=a[0];},onLeave(){const n=this.state.add(0x420).readPointer().sub(this.state.add(0x418).readPointer()).toInt32()/0x8b;note({event:'channel_list_handler_return',count:n,index:this.state.add(0x5b4).readS32()});if(n===1)channelsReady=Date.now();}});
   Interceptor.attach(game.base.add(0x137ad80),{
    onEnter(a){this.state=a[0];},onLeave(){const p=this.state;
     if(Date.now()-lastCharacterFrame>=2000){lastCharacterFrame=Date.now();const u=p.add(0x4f8).readPointer();note({event:'updated_character_frame',state:p.toString(),vtable:p.readPointer().sub(game.base).toString(),unit:u.toString(),uid:u.isNull()?null:u.add(0x48).readU64().toString(),characterReady,channelsReady,selected,chosen});}
     if(!p.readPointer().equals(game.base.add(0x41dcee0)))return;
     if(!loadedCharacter&&characterReady&&Date.now()-characterReady>10000&&p.add(0x4f8).readPointer().isNull()){
      const manager=game.base.add(0x4817e70).readPointer().add(0xc8).readPointer(),b=manager.add(0xa8).readPointer(),n=manager.add(0xb0).readPointer().sub(b).toInt32()/8;
      if(n===1){const source=b.readPointer();if(!source.isNull()){
       selectedCharacterUid=source.add(0x48).readU64().toString();
       loadedCharacter=true;note({event:'native_character_card_selected',uid:selectedCharacterUid,source:source.toString()});
       // Original role-loading continuation used by the character card callback.
       nativeCall(0x13835c0,'void',['pointer','pointer'])(p,source);
       return;
      }}
     }
     const u=p.add(0x4f8).readPointer();if(u.isNull())return;
     selectedCharacterUid=u.add(0x48).readU64().toString();
     if(!selected&&characterReady&&Date.now()-characterReady>10000){selected=true;note({event:'native_character_selection_request',uid:selectedCharacterUid});nativeCall(0x13a0f90,'void',['pointer'])(p);}
     if(selected&&!chosen&&channelsReady&&Date.now()-channelsReady>5000){const n=p.add(0x420).readPointer().sub(p.add(0x418).readPointer()).toInt32()/0x8b;if(n!==1||p.add(0x5b4).readS32()!==0)return;chosen=true;note({event:'native_channel_choice_request',count:n,index:0});nativeCall(0x13aeb90,'void',['pointer'])(p);}
    }
   });
  }
  if(enterDungeon&&gateIdentityTest&&populationTest){
   // The paired Ain script requests Rose03. Finish only that foreign scene
   // through its original Skip lifecycle before returning to the game frame.
   // No replacement dialogue or original completion predicate is fabricated.
   function ownAinTutorial(g){
    if(g.isNull()||!g.readPointer().equals(game.base.add(0x41bfd28))||g.add(0x2d0).readS32()!==2)return null;
    const app=game.base.add(0x4817e70).readPointer(),manager=app.add(0xc8).readPointer(),selected=manager.add(0xa0).readPointer(),party=app.add(0xa8).readPointer();
    if(selected.isNull()||party.isNull()||party.add(0x10).readS32()!==41420)return null;
    const definition=selected.add(0x29c0).readPointer(),actor=nativeCall(0x8571d0,'pointer',['pointer'])(g);
    if(definition.isNull()||definition.readS32()!==12||actor.isNull()||!actor.add(0x1a3e0).readPointer().equals(selected))return null;
    return selected.add(0x48).readU64().toString();
   }

   function sceneText(p){const n=p.add(16).readU64().toNumber(),cap=p.add(24).readU64().toNumber();if(n>64||cap<n)throw Error('Tutorial scene name bound');return (cap>7?p.readPointer():p).readUtf16String(n);}
   Interceptor.attach(game.base.add(0x10509b0),{onEnter(a){this.ain=null;try{if(a[1].readCString()!=='Tutorial_Rose_03')return;const uid=ownAinTutorial(a[0]);if(uid!==null)this.ain={game:a[0],uid};}catch(e){note({event:'ain_scene_skip_guard_error',error:String(e)});}},onLeave(){if(this.ain===null)return;try{
    if(ownAinTutorial(this.ain.game)!==this.ain.uid)return;
    const app=game.base.add(0x4817e70).readPointer(),stx=app.add(0x4b0).readPointer(),movie=app.add(0x4a8).readPointer();let source=null;
    if(!stx.isNull()&&sceneText(stx.add(0xd8))==='Tutorial_Rose_03'&&nativeCall(0x4ab640,'uint8',['pointer'])(stx.add(0x160))===1){nativeCall(0x1a3eb80,'void',['pointer','uint8'])(stx,1);source='STXFunc_EndEventScene original 1A3EB80';}
    else if(!movie.isNull()&&movie.readPointer().equals(game.base.add(0x4242530))&&movie.add(8).readU8()===1&&sceneText(movie.add(0xa8))==='Tutorial_Rose_03'){nativeCall(0x1c96d20,'void',['pointer','uint8'])(movie,0);source='original movie Skip 1C96D20';}
    if(source!==null){
     // RF27 set CannotInput(9999) for this copied scene. Its original
     // RF29 counterpart uses CannotInput(0.1), converted by the integer
     // binding to zero. Undo only this skipped foreign scene's input hold.
     nativeCall(0x1050c30,'void',['pointer','int'])(this.ain.game,0);
     note({event:'ain_foreign_scene_original_skip_completed',uid:this.ain.uid,map:41420,scene:'Tutorial_Rose_03',source,before_game_frame_returns:true,original_completion_predicate_preserved:true,orphaned_scene_input_released_by_original_CannotInput:true,raw_actor_memory_writes:0,replacement_dialogue_invented:false});
    }
   }catch(e){note({event:'ain_scene_original_skip_error',error:String(e)});}}});
  }
  if(enterDungeon){
   if(gateIdentityTest)Interceptor.attach(game.base.add(0x16d2090),{onEnter(a){
    // Shared death DTO enrichment, used by combat and expiry (16E1760).
    // 1AA4A40 searches UID at +3D0; +3C8 is a reusable vector slot, NOT
    // that UID. Summons surviving a stage transition make them diverge.
    // Change only this outgoing DTO identity after both ownership checks.
    try{
     const actor=a[0],dto=a[1],id=actor.add(0x3d0).readU64().toNumber(),slot=actor.add(0x3c8).readS32(),reported=dto.readS32();
     if(reported!==0||id===0||!Number.isInteger(id)||id<0||id>=(populationTest?16384:80)||slot<0||slot>=80||dungeonGame.isNull())return;
     const stageParent=dungeonGame.add(0x1440).readPointer(),stage=stageParent.isNull()?-1:stageParent.add(0x10).readS32();
     const limit=populationTest?[7,10,1][stage]:2;
     const sentry=populationTest&&id>=16&&actor.add(0x19e20).readPointer().readS32()===384;
     // Static solo routes can assign IDs across several parts. The original
     // UID lookup and live slot/actor ownership below provide the witness;
     // the El Tree fixture's 7/10/1 limits do not describe other dungeons.
     if(!populationTest&&(limit===undefined||(!sentry&&id>limit)))return;
     if(!dungeonGame.readPointer().equals(game.base.add(0x41bfd28))||dungeonGame.add(0x2d0).readS32()!==2)return;
     const begin=dungeonGame.add(0x378).readPointer(),end=dungeonGame.add(0x380).readPointer();
     if(end.sub(begin).toInt32()!==80*8||!begin.add(slot*8).readPointer().equals(actor))return;
     const found=nativeCall(0x1aa4a40,'pointer',['pointer','int'])(dungeonGame,id);
     if(!found.equals(actor))return;
     const hp=nativeCall(0x7d8b00,'float',['pointer'])(actor);
     // Original captured Lithia controllers' DYING_END retires through 16E1760 while
     // retaining positive HP. Preserve all ordinary zero-HP admission rules.
     const caller=this.returnAddress.sub(game.base).toInt32(),definition=actor.add(0x19e20).readPointer();
     const tutorialRetirement=populationTest&&actor.readPointer().equals(game.base.add(0x41ea620))
       &&caller===0x16e199d&&dto.add(4).readU8()===255
       &&dto.add(5).readU64().toString()==='18446744073709551615'
       &&dto.add(13).readU64().toString()==='18446744073709551615'
       &&!definition.isNull()&&[2084,9288,9289,9290,9463].includes(definition.readS32())&&Number.isFinite(hp)&&hp>0;
     if(hp>0&&!tutorialRetirement)return;
     dto.writeS32(id);note({event:'isolated_death_identity_repair',actor:actor.toString(),reported,native_uid:id,instance_index:slot,original_lookup_matches:true,vector_slot_matches:true,sentry,substage:stage,population_test:populationTest,tutorial_script_retirement:tutorialRetirement,hp,caller_rva:caller,source_template:tutorialRetirement?definition.readS32():null});
    }catch(e){note({event:'isolated_death_identity_repair_error',error:String(e)});}
   }});
   // Per-key diagnostic Interceptor intentionally omitted during normal play.
   Interceptor.attach(game.base.add(0xc25b90),{onEnter(a){
    this.timeSample=null;if(a[3].toUInt32()!==0x9c||dungeonGame.isNull())return;
    const buffer=a[4];this.timeSample={buffer,start:buffer.add(0x20).readU32(),g:ptr(dungeonGame.toString()),before:dungeonGame.add(0xa88).readS32()};
   },onLeave(){const s=this.timeSample;if(!s)return;timeSyncReceived++;note({event:'updated_dungeon_time_sync',kind:0x9c,start:s.start,end:s.buffer.add(0x20).readU32(),before:s.before,after:s.g.add(0xa88).readS32()});}});
   Interceptor.attach(game.base.add(0xc231c0),{onEnter(a){this.state=a[0];},onLeave(){
    const ref=this.state.add(0x908);if(ref.readS32()<0||ref.add(4).readU32()===0)return;
    const g=nativeCall(0x7ada60,'pointer',['pointer'])(ref);if(g.isNull()||!g.readPointer().equals(game.base.add(0x41bfd28)))return;
    dungeonGame=g;dungeonActor=nativeCall(0x8571d0,'pointer',['pointer'])(g);
    if(dungeonActor.isNull()||Date.now()-lastDungeonFrame<1000)return;lastDungeonFrame=Date.now();
    const vectors=[0x348,0x360,0x378,0x390,0x3f0].map(o=>{const b=g.add(o).readPointer(),n=g.add(o+8).readPointer().sub(b).toInt32()/8;return {offset:o,count:n,pointers:n>=0&&n<=128&&Number.isInteger(n)?Array.from({length:n},(_,i)=>b.add(i*8).readPointer().toString()).filter(p=>p!=='0x0'):[]};});
    const npcs=[];for(const [id,p] of createdNpcs)try{if(p.readPointer().equals(game.base.add(0x41ea620)))npcs.push({key:id,...npcSample(p),script:p.add(0x19e20).readPointer().toString(),model_definition:p.add(0x19e30).readPointer().toString(),spawn_xyz:[0,4,8].map(o=>p.add(0x19fe4+o).readFloat()),registered_in:vectors.filter(v=>v.pointers.includes(p.toString())).map(v=>v.offset)});}catch(e){note({event:'updated_npc_sample_error',key:id,error:String(e)});}
    note({event:'updated_dungeon_frame',game:g.toString(),mode:g.add(0x2d0).readS32(),substage:g.add(0x1440).readPointer().isNull()?null:g.add(0x1440).readPointer().add(0x10).readS32(),actors_suspended:g.add(0x620).readU8(),input_time_credit:g.add(0xa88).readS32(),input_time_mode:g.add(0xaa4).readS32(),physical_key_conversions:physicalKeyConversions,time_sync_received:timeSyncReceived,player:{...actorSample(dungeonActor),mp:nativeCall(0x19ec9b0,'float',['pointer'])(dungeonActor)},vectors,npc_count:npcs.length,npcs});
    if(autoReturn&&g.add(0x2d0).readS32()===2&&g.add(0x620).readU8()===0){
     if(!returnGame.equals(g)){returnGame=ptr(g.toString());fixtureSeenAlive=false;fixtureDeadAt=0;fixtureEndRequested=false;}
     // Local map30000 fixture only. Observe actual native HP; never change
     // actor health, movement, game mode or clear/reward state.
     const fixture=npcs.find(n=>n.key===100001);
     if(fixture&&fixture.hp>0){fixtureSeenAlive=true;fixtureDeadAt=0;}
     if(fixtureSeenAlive&&fixture&&fixture.hp<=0&&!fixtureDeadAt){fixtureDeadAt=Date.now();note({event:'local_training_npc_dead',key:100001,game:g.toString(),hp:fixture.hp});}
     if(fixtureDeadAt&&Date.now()-fixtureDeadAt>=2000&&!fixtureEndRequested&&nativeCall(0x7d8b00,'float',['pointer'])(dungeonActor)>0){
      fixtureEndRequested=true;
      const result=nativeCall(0x1ab2b10,'uint8',['pointer','int'])(g,0x72);
      note({event:'local_training_return_requested',reason:0x72,result,automatic:true,rewards:false});
     }
    }
   }});
   Interceptor.attach(game.base.add(0x1aa5b80),{onEnter(a){this.game=a[0];inputDelivered=false;},onLeave(){
    if(this.game.equals(dungeonGame)&&!dungeonActor.isNull()&&!inputDelivered&&(inputProbe||updatedCommand?.op==='dungeon_input'))nativeCall(0x18c7160,'void',['pointer','pointer'])(dungeonActor,this.game.add(0x46c));
   }});
   Interceptor.attach(game.base.add(0x18c7160),{onEnter(a){this.sample=null;
    if(!a[0].equals(dungeonActor)||dungeonGame.isNull()||dungeonGame.add(0x2d0).readS32()!==2||dungeonGame.add(0x620).readU8()!==0)return;inputDelivered=true;
    if(updatedCommand?.op==='dungeon_input'){
     const c=updatedCommand;updatedCommand=null;const offsets={left:0,right:4,jump:8,attack_z:16,skill_a:28,skill_s:32};
     if(!(c.action in offsets)||!Number.isInteger(c.duration_ms)||c.duration_ms<50||c.duration_ms>1500||inputProbe){note({event:'updated_input_refused',action:c.action});return;}
     inputProbe={action:c.action,offset:offsets[c.action],started:Date.now(),until:Date.now()+c.duration_ms,first:true,buffer:Memory.alloc(104),samples:0};note({event:'updated_input_started',action:c.action,before:actorSample(a[0])});
    }
    const p=inputProbe;if(!p)return;p.buffer.writeByteArray(a[1].readByteArray(104));for(const o of [0,4,8,12,16,20,24,28,32])p.buffer.add(o).writeU32(0);
    const release=Date.now()>=p.until;if(release)p.buffer.add(p.offset+3).writeU8(1);else{p.buffer.add(p.offset).writeU8(1);if(p.first){p.buffer.add(p.offset+1).writeU8(1);p.buffer.add(p.offset+2).writeU8(1);}}
    p.first=false;a[1]=p.buffer;this.sample={p,actor:a[0],release};
   },onLeave(){const s=this.sample;if(!s)return;s.p.samples++;if(s.release){note({event:'updated_input_finished',action:s.p.action,samples:s.p.samples,after:actorSample(s.actor),mp:nativeCall(0x19ec9b0,'float',['pointer'])(s.actor)});inputProbe=null;}}});
   Interceptor.attach(game.base.add(0x184afa0),{onEnter(a){this.local=a[0].equals(dungeonActor);this.actor=a[0];this.requested=a[1].toInt32();},onLeave(r){if(this.local&&inputProbe)note({event:'updated_action_state',action:inputProbe.action,requested:this.requested,result:r.toInt32()&255,after:actorSample(this.actor),mp:nativeCall(0x19ec9b0,'float',['pointer'])(this.actor)});}});
   Interceptor.attach(game.base.add(0x2b42890),{onEnter(a){this.dto=a[1];this.buffer=a[0].add(8).readPointer();this.start=this.buffer.add(0x20).readU32();},onLeave(r){note({event:'updated_npc_record_decoded',ok:r.toInt32()&255,key:this.dto.readS32(),template:this.dto.add(4).readS32(),start:this.start,end:this.buffer.add(0x20).readU32()});}});
   Interceptor.attach(game.base.add(0x107f480),{onEnter(a){note({event:'updated_npc_factory_enter',key:a[0].readS32(),template:a[0].add(4).readS32(),override_template:a[1].isNull()?null:a[1].readS32(),level:a[0].add(0x3c).readS32(),xyz:[0,4,8].map(o=>a[0].add(0x30+o).readFloat())});},onLeave(){note({event:'updated_npc_factory_finished'});}});
   Interceptor.attach(game.base.add(0x15684e0),{onEnter(a){this.key=a[2].toInt32();this.template=a[3];},onLeave(r){if(!r.isNull()){
    createdNpcs.set(this.key,ptr(r.toString()));
    // Native allocator may reuse the same Game address on the next entry.
    // A fresh fixture constructor is a new lifecycle even at the same pointer.
    if(this.key===100001){returnGame=ptr(0);fixtureSeenAlive=false;fixtureDeadAt=0;fixtureEndRequested=false;}
   }note({event:'updated_npc_actor_created',key:this.key,actor:r.toString(),vtable:r.isNull()?null:r.readPointer().sub(game.base).toString(),template_script:this.template.add(0x138).readPointer().toString()});}});
   Interceptor.attach(game.base.add(0x1562bc0),{onEnter(a){for(const [id,p] of createdNpcs)if(p.equals(a[0])){note({event:'updated_npc_actor_destroyed',key:id,actor:p.toString()});createdNpcs.delete(id);}}});
   Interceptor.attach(game.base.add(0xc231c0),{onLeave(){
    if(npcOfflineProbeDone||!npcInputBufferTemplate||!npcCandidate)return;npcOfflineProbeDone=true;
    try{
     const bytes=h=>h.match(/../g).map(x=>parseInt(x,16)),wire=bytes(npcCandidate.wire_hex),storage=Memory.alloc(wire.length),buffer=Memory.alloc(0x30),stream=Memory.alloc(0x28),dto=Memory.alloc(0xa4),head=Memory.alloc(0x20);
     storage.writeByteArray(wire);buffer.writeByteArray(npcInputBufferTemplate);buffer.add(8).writePointer(storage);buffer.add(0x10).writePointer(storage.add(wire.length));buffer.add(0x18).writePointer(storage.add(wire.length));buffer.add(0x20).writeU32(0);
     nativeCall(0x3b6d140,'pointer',['pointer'])(stream);
     nativeCall(0x3b6d1c0,'uint8',['pointer','pointer','uint8'])(stream,buffer,0);
     dto.writeByteArray(Array(0xa4).fill(0));head.writeByteArray(Array(0x20).fill(0));for(const o of [0,8,16])head.add(o).writePointer(head);head.add(0x18).writeU16(0x101);dto.add(0x94).writePointer(head);
     const ok=nativeCall(0x2b42890,'uint8',['pointer','pointer'])(stream,dto),fields=npcCandidate.fields.map(f=>({...f,actual:Array.from(new Uint8Array(dto.add(f.offset).readByteArray(f.size)),v=>v.toString(16).padStart(2,'0')).join('')}));
     note({event:'updated_npc_offline_decode',ok,consumed:buffer.add(0x20).readU32(),size:wire.length,key:dto.readS32(),template:dto.add(4).readS32(),fields_match:fields.every(f=>f.actual===f.hex),fields,applied_to_game:false});
    }catch(e){note({event:'updated_npc_offline_decode_error',error:String(e)});}
   }});
   Interceptor.attach(game.base.add(0x2bdcf00),{onEnter(a){const r=this.returnAddress.sub(game.base).toInt32();if(r>=0x2b47830&&r<=0x2b47913){const s=a[0].add(8).readPointer();note({event:'updated_npc_vector_mode',mode:this.context.rsi.toInt32(),stream:a[0].toString(),offset:s.add(0x20).readU32(),caller:r});}}});
   Interceptor.attach(game.base.add(0x30d0660),{
    onLeave(){
     if(Date.now()-lastFieldFrame<1000)return;lastFieldFrame=Date.now();
     const manager=game.base.add(0x4817e70).readPointer(),unit=manager.add(0xc8).readPointer().add(0xa0).readPointer();
     if(unit.isNull()||selectedCharacterUid===null||unit.add(0x48).readU64().toString()!==selectedCharacterUid)return;
     const ui=manager.add(0x558).readPointer(),party=manager.add(0xa8).readPointer();
     note({event:'updated_field_frame',uid:selectedCharacterUid,selected_map:party.add(0x10).readS32()});
     if(!npcCatalogRead){
      npcCatalogRead=true;const npc=manager.add(0x60).readPointer(),head=npc.add(0x120).readPointer(),stack=[head.add(8).readPointer()],entries=[],seen=new Set();
      while(stack.length&&entries.length<16384){const n=stack.pop();if(n.add(0x19).readU8()||seen.has(n.toString()))continue;seen.add(n.toString());const s=n.add(0x70),len=s.add(16).readU64().toNumber(),cap=s.add(24).readU64().toNumber();let filename=null;if(len>0&&len<=256&&cap>=len)filename=(cap>7?s.readPointer():s).readUtf16String(len);entries.push({id:n.add(0x20).readS32(),filename});stack.push(n.readPointer(),n.add(0x10).readPointer());}
      note({event:'updated_npc_catalog',entries,bounded:stack.length===0});
     }
     if(updatedCommand?.op==='dungeon_enter'){
      updatedCommand=null;const object=ui.add(0x320).readPointer();
      if(party.add(0x10).readS32()!==30000||object.isNull()||!object.readPointer().equals(game.base.add(0x42bd758))){note({event:'updated_dungeon_entry_refused',object:object.toString(),vtable:object.isNull()?null:object.readPointer().sub(game.base).toString()});return;}
      nativeCall(0x2cc06d0,'void',['pointer','uint64','uint64','uint64','uint64'])(object,0,0x467,0x3783,0);
      note({event:'native_dungeon_ui_action_invoked',action:0x3783});
     }
    }
   });
   for(const rva of [0x2b4d0d0,0x2b4cef0])Interceptor.attach(game.base.add(rva),{onEnter(a){this.stream=a[0].add(8).readPointer();this.start=this.stream.add(0x20).readU32();if(rva===0x2b4cef0)npcInputBufferTemplate=this.stream.readByteArray(0x30);},onLeave(r){note({event:'updated_dungeon_payload_parsed',reader:rva,ok:r.toInt32()&255,start:this.start,end:this.stream.add(0x20).readU32()});}});
  }
  Interceptor.attach(game.base.add(0xd9b170),{
   onEnter(a){this.data=a[1];this.stream=a[0].add(8).readPointer();this.start=this.stream.add(0x20).readU32();},
     onLeave(r){note({event:'character_full_dto_parsed',ok:r.toInt32()&255,uid:this.data.add(9).readU64().toString(),level:this.data.add(0x65).readU8(),scalar5d:this.data.add(0x5d).readU64().toString(),scalar66:this.data.add(0x66).readS32(),end:this.stream.add(0x20).readU32(),start:this.start});}
  });
  noahVerifiedSenderReady=true;
  note({event:'updated_login_hooks_ready'});
 }else if(tries>=600){clearInterval(timer);note({event:'hooks_unavailable'});}
},50);

// Current native tutorial return chooses a stale pre-tutorial position for Noah.
// Supply the native village default to the original world initializer input.
{
 const prefixes={"12137632": "488bc44889580855", "7562416": "40534883ec204c8b"};let attempts=0,clear=null;
 const timer=setInterval(()=>{
  if(!noahVerifiedSenderReady)return;
  attempts++;if(!Object.entries(prefixes).every(([r,h])=>Array.from(new Uint8Array(game.base.add(Number(r)).readByteArray(h.length/2)),v=>v.toString(16).padStart(2,'0')).join('')===h)){if(attempts>=600){clearInterval(timer);note({event:'noah_natural_spawn_guard_unavailable'});}return;}clearInterval(timer);
  function selected(){const data=game.base.add(0x4817e70).readPointer();if(data.isNull())return null;const roles=data.add(0xc8).readPointer();if(roles.isNull())return null;const s=roles.add(0xa0).readPointer();if(s.isNull())return null;const d=s.add(0x29c0).readPointer();if(d.isNull()||d.readS32()!==14)return null;const u=s.add(0x48),decode=o=>(u.add(o).toUInt32()^u.add(o+8).readU32()^u.add(o+16).readU32())>>>0;if(decode(0x758)!==20012||decode(0xa8)!==1||decode(0xc0)!==0)return null;return{data,uid:u.readU64().toString(),manager:data.add(0x490).readPointer()};}
  Interceptor.attach(game.base.add(0x682d80),{onEnter(a){try{if(a[1].add(16).readU32()!==0x202||a[1].add(0x34).readU16()!==0x110)return;const s=selected();if(!s)return;const party=s.data.add(0xa8).readPointer();if(party.isNull()||party.add(0x10).readS32()!==34570)return;clear={uid:s.uid,until:Date.now()+15000};note({event:'noah_natural_clear_return_observed',uid:s.uid,map:34570});}catch(e){clear=null;note({event:'noah_natural_clear_guard_error',reason:String(e)});}}});
  Interceptor.attach(game.base.add(0xb934a0),{onEnter(a){
   if(this.returnAddress.sub(game.base).toInt32()!==0xba7c6b||!clear||Date.now()>clear.until||a[1].toInt32()!==0)return;
   try{const s=selected();if(!s||s.uid!==clear.uid||s.manager.isNull()||a[2].isNull())return;const before=[0,4,8].map(o=>a[2].add(o).readFloat());if(before.some(v=>v!==0))return;
    const source=Memory.alloc(12),point=Memory.alloc(12);source.writeByteArray(new Uint8Array(12));point.writeByteArray(new Uint8Array(12));
    nativeCall(0x7364b0,'pointer',['pointer','pointer','int'])(s.manager,source,20012);
    nativeCall(0x7362e0,'pointer',['pointer','pointer','int'])(s.manager,point,710);
    const xyz=[0,4,8].map(o=>source.add(o).readFloat()),known=[-858.6,1000,-1924];
    if([0,4,8].some(o=>!Number.isFinite(point.add(o).readFloat()))||xyz.some((v,i)=>!Number.isFinite(v)||Math.abs(v-known[i])>.01||Math.abs(v-point.add(i*4).readFloat())>.01)){note({event:'noah_natural_default_source_mismatch',xyz});return;}
    this.keep=source;a[1]=ptr(20012);a[2]=source;clear=null;
    note({event:'noah_natural_default_input_selected',uid:s.uid,from_town:0,to_town:20012,before_input:before,source_xyz:xyz,source:'original 7364B0 village first-entry/default source, cross-checked against native point710; original B934A0 / BA7C6B input',actor_XYZ_writes:0,saved_XYZ_writes:0,EXP_writes:0});
   }catch(e){note({event:'noah_natural_spawn_guard_error',reason:String(e)});}
  },onLeave(){this.keep=null;}});note({event:'noah_natural_spawn_guard_ready',caller:'BA7C6B',original_initializer:'B934A0',actor_XYZ_writes:0});
 },50);
}

// Noah EXP0 entry: use this village's verified IsDefaultPos through original APIs.
{
 const expected={"7561952": "4c8bdc49895b1857", "20516400": "488bc44889580848"};let attempts=0;
 const timer=setInterval(()=>{
  attempts++;const ready=Object.entries(expected).every(([r,h])=>Array.from(new Uint8Array(game.base.add(Number(r)).readByteArray(h.length/2)),v=>v.toString(16).padStart(2,'0')).join('')===h);
  if(!ready){if(attempts>=600){clearInterval(timer);note({event:'noah_initial_point_guard_unavailable'});}return;}clearInterval(timer);
  Interceptor.attach(game.base.add(0x7362e0),{onEnter(a){
   if(this.returnAddress.sub(game.base).toInt32()!==0x1390fda||a[2].toInt32()!==1)return;
   try{
    const data=game.base.add(0x4817e70).readPointer();if(data.isNull())return;const roles=data.add(0xc8).readPointer();if(roles.isNull())return;const selected=roles.add(0xa0).readPointer();if(selected.isNull())return;const definition=selected.add(0x29c0).readPointer();if(definition.isNull()||definition.readS32()!==14)return;
    const unit=selected.add(0x48),decode=o=>(unit.add(o).toUInt32()^unit.add(o+8).readU32()^unit.add(o+16).readU32())>>>0;
    if(decode(0x758)!==20012||decode(0xa8)!==1||decode(0xc0)!==0||!a[0].equals(data.add(0x490).readPointer()))return;
    // Current 736E20 selects IsSummon (709), not IsDefaultPos. Validate the
    // witnessed IsDefaultPos=710 through the original point reader itself.
    const point=710,position=Memory.alloc(12);position.writeByteArray(new Uint8Array(12));nativeCall(0x7362e0,'void',['pointer','pointer','int'])(a[0],position,point);
    const xyz=[0,4,8].map(o=>position.add(o).readFloat()),expectedXYZ=[-858.6,1000,-1924];if(xyz.some((v,i)=>!Number.isFinite(v)||Math.abs(v-expectedXYZ[i])>.01)){note({event:'noah_initial_point_source_mismatch',point,xyz});return;}
    a[2]=ptr(point);note({event:'noah_initial_source_point_selected',uid:unit.readU64().toString(),town:20012,before:1,after:point,source_xyz:xyz,source:'Current DLG_Map_Village/20012 IsDefaultPos=710, validated by original 7362E0; original 1390FDA consumer',actor_XYZ_writes:0,EXP_writes:0});
   }catch(e){note({event:'noah_initial_point_guard_error',reason:String(e)});}
  }});note({event:'noah_initial_point_guard_ready',exact_caller:'1390FDA',unit_type:14,town:20012,EXP:0,level:1,actor_XYZ_writes:0});
 },50);
}
