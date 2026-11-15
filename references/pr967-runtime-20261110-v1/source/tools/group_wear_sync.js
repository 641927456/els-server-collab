// Isolated candidate. Marked equipment delta only; never run the complete106
// attribute receiver with missing attributes or empty auxiliary state.
function prepareElsGroupWearSync() {
 'use strict';
 if(globalThis.elsGroupWearSync)throw Error('Group wear support already installed');
 const M=Process.getModuleByName('x2_dx11.exe'),pins=__GROUP_WEAR_PINS__,tables=__GROUP_WEAR_VIRTUALS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(M.base.add(+r),h.length/2)!==h)throw Error('Group wear native identity '+r);

 return function installElsGroupWearSync(cache) {
 const nf=(r,t,a)=>new NativeFunction(M.base.add(r),t,a,{exceptions:'propagate'});
 const lookup=nf(0x1aa4580,'pointer',['pointer','uint64']);
 const validGame=nf(0x15a0b0,'uint8',['pointer']),resolveGame=nf(0x15a100,'pointer',['pointer']);
 const decode=nf(0x234b280,'void',['pointer','pointer']),disposeVector=nf(0x98bfc0,'void',['pointer']);
 const createItem=nf(0x7ebc80,'pointer',['pointer','pointer']),disposeItem=nf(0x7efc10,'void',['pointer']);
 const definition=nf(0x6d56c0,'pointer',['pointer','uint32']);
 const atSlot=nf(0x197f570,'pointer',['pointer','int','int']);
 const put=nf(0x197e5f0,'uint8',['pointer','uint32','int','pointer','uint8']);
 const remove=nf(0x197fa60,'void',['pointer','uint64']);
 const removeSources=nf(0x85d5e0,'void',['pointer','uint64']),addSources=nf(0x85ce30,'uint64',['pointer','pointer','int16','uint8']);
 const removeTemplate=nf(0x1ac13a0,'uint64',['pointer','pointer','pointer']);
 const removeItemEffects=nf(0x1ac18a0,'uint8',['pointer','pointer','pointer']);
 const addTemplate=nf(0x1ac1610,'uint64',['pointer','pointer','pointer']);
 const refreshModel=nf(0x18c2e40,'void',['pointer']);
 const clearAttachment=nf(0x1bdd4f0,'void',['pointer','pointer','uint8']),updateEquipment=nf(0x19245e0,'void',['pointer','uint8']);
 const updateAlternate=nf(0x1950650,'void',['pointer','uint8','pointer']),updateAppearance=nf(0x1950890,'void',['pointer']);
 const virtualCalls=new Map();
 function virtual(actor,slot,ret,args,values){
  const vt=actor.readPointer(),row=tables[vt.sub(M.base).toUInt32()],fn=vt.add(slot).readPointer();
  if(!row||row.functions[slot]===undefined||!fn.equals(M.base.add(row.functions[slot])))throw Error('Group wear player virtual identity '+slot);
  const key=fn+':'+ret+':'+args.join(',');let call=virtualCalls.get(key);if(!call){call=new NativeFunction(fn,ret,['pointer',...args],{exceptions:'propagate'});virtualCalls.set(key,call);}return call(actor,...values);
 }
 const dispatcher=M.base.add(0xbaa6f0),types=['pointer','uint64','uint32','uint64','pointer'];
 const original=new NativeFunction(dispatcher,'uint8',types,{exceptions:'propagate'});
 const hooks=[],initializedPeers=new Map(),pending=[];let disabled=false,gameKey=null,epoch=null,advertisedAt=0,applied=0,inspected=0,pendingBytes=0,flushing=false,ownerRequest=null,ownerReport=null;
 const emit=(event,row={})=>send({event:'native_group_wear_'+event,timestamp:Date.now(),...row});
 function currentGame(){
  // Use BAA6F0's current native weak handle, including its object generation.
  // A packet may arrive before the next cache/frame observer has run.
  const handle=M.base.add(0x478cb88);if(!validGame(handle))return null;
  const g=resolveGame(handle);
  if(g.isNull()||!g.readPointer().equals(M.base.add(0x41bfd28))||g.add(0x2d0).readS32()!==2||g.add(0x620).readU8()!==0)return null;
  return {g,key:hex(handle,8)+':'+g};
 }
 function body(buffer){
  const begin=buffer.add(8).readPointer(),end=buffer.add(16).readPointer(),offset=buffer.add(0x20).readU32();
  if(begin.isNull()||end.compare(begin)<0)return null;
  const size=end.sub(begin).toInt32();if(size<0||size>65500||offset>size)return null;
  return {begin,p:begin.add(offset),size,offset,left:size-offset};
 }
 function generation(current){if(gameKey!==current.key){gameKey=current.key;epoch=null;initializedPeers.clear();pending.length=0;pendingBytes=0;ownerRequest=null;ownerReport=null;}}
 function remember(current,actor,unit,uid,snapshot){initializedPeers.set(unit.toString(),{key:current.key+':'+actor+':'+uid+':'+unit.add(0x58).readU16(),snapshot});}
 function refreshPeer(g,actor){
  if(disabled||flushing||actor.isNull()||!tables[actor.readPointer().sub(M.base).toUInt32()])return;
  try{
   const current=currentGame();if(current===null||!current.g.equals(g))return;generation(current);if(!cache.peerReady(g))return;
   const engine=M.base.add(0x4817e70).readPointer(),carrier=engine.add(0xc8).readPointer(),selected=carrier.add(0xa0).readPointer(),unit=actor.add(0x1a3e0).readPointer();
   if(selected.isNull()||unit.isNull())return;const uid=unit.add(0x48).readU64();
   if(uid.toString()===selected.add(0x48).readU64().toString()||!lookup(g,uid).equals(actor))return;
   const key=current.key+':'+actor+':'+uid+':'+unit.add(0x58).readU16(),old=initializedPeers.get(unit.toString());
   if(!old||old.key!==key)return;
   if(old&&old.key===key&&cache.peerCurrent(actor,old.snapshot))return;
   remember(current,actor,unit,uid,cache.peer(g,actor,old.snapshot));emit('peer_initialized',{uid:uid.toString(),native_ability:'888CA0',from_current_original_Actor:true});
  }catch(error){fail(error);}
 }
 function consume(buffer,b){
  if(b.left<94||b.p.readU8()!==0x81||b.p.add(1).readU8()!==3)throw Error('Group wear delta header');
  const room=hex(b.p.add(2),16),uid=uint64('0x'+hex(b.p.add(18),8));
  const current=currentGame();
  // An already queued delta may follow the original exit ACK. Its room and
  // Actor no longer exist; discard it without disabling the next admission.
  if(current===null){buffer.add(0x20).writeU32(b.size);emit('obsolete',{reason:'outside-original-dungeon'});return;}
  const g=current.g;
  generation(current);
  if(epoch!==null&&epoch!==room){buffer.add(0x20).writeU32(b.size);emit('obsolete',{reason:'different-room-generation'});return;}
  const engine=M.base.add(0x4817e70).readPointer(),carrier=engine.add(0xc8).readPointer(),selected=carrier.add(0xa0).readPointer();
  if(selected.isNull()||selected.add(0x48).readU64().toString()===uid.toString())throw Error('Group wear foreign owner required');
  const actor=lookup(g,uid);if(actor.isNull())throw Error('Group wear admitted peer missing');
  const unit=actor.add(0x1a3e0).readPointer();
  if(unit.isNull()||unit.add(0x48).readU64().toString()!==uid.toString())throw Error('Group wear peer Unit identity');
  if(!tables[actor.readPointer().sub(M.base).toUInt32()])throw Error('Group wear player RTTI identity');
  const dto=Memory.alloc(28),items=[];dto.writeS32(-1);
  buffer.add(0x20).writeU32(b.offset+86);
  try {
   decode(buffer,dto);
   const begin=dto.add(4).readPointer(),end=dto.add(12).readPointer(),count=end.sub(begin).toInt32()/0x408;
   if(dto.readS32()!==0||buffer.add(0x20).readU32()!==b.size||!Number.isInteger(count)||count<1||count>2)throw Error('Group wear original105 decoding');
   const slots=new Set();
   // Decode and resolve every template before changing the original peer.
   for(let i=0;i<count;i++){
    const record=begin.add(i*0x408),slot=record.add(9).readS16();
    if(record.add(8).readU8()!==9||slot<0||slot>127||slots.has(slot))throw Error('Group wear equipped slot');slots.add(slot);
    const raw=Memory.alloc(0x328);createItem(raw,record);items.push({raw,slot});
    let item=ptr(0);
    if(record.readU64().toString()!=='0'){
     const template=definition(engine.add(0x58).readPointer(),raw.add(8).readU32());if(template.isNull()||template.readU32()!==raw.add(8).readU32())throw Error('Group wear item template');
     raw.add(0x310).writePointer(template);raw.add(0x318).writePointer(unit);raw.add(0x320).writeU8(0);item=raw;
    }
    items[items.length-1].item=item;
   }
   // Match the existing native cache's original event-processing fence.
   cache.begin();
   try{

   epoch=room;
   const inventory=unit.add(0x440);
   for(const {raw,slot,item}of items){
    const previous=atSlot(inventory,9,slot);
    if(!virtual(actor,0x1398,'uint8',['pointer','pointer','int16'],[item,previous,slot]))throw Error('Group wear native model rejected');
    if(!previous.isNull()){
     const oldUID=previous.readU64();removeTemplate(g,previous.add(0x310).readPointer(),actor);removeItemEffects(g,previous,actor);
     removeSources(unit,oldUID);remove(inventory,oldUID);
    }
    if(!item.isNull()){
     if(!put(inventory,9,slot,raw,0))throw Error('Group wear native inventory rejected');
     addSources(unit,item,0,1);addTemplate(g,item.add(0x310).readPointer(),actor);
    }
   }
   // Original106's equipment-specific finishing sequence, retaining each
   // class's native overrides. No title/option-map/progress replacement occurs.
   if(actor.add(0x1b120).readU8()===0&&actor.add(0x1b121).readU8()===0){
    virtual(actor,0x1388,'void',['uint8'],[1]);virtual(actor,0x1360,'void',[],[]);virtual(actor,0x1368,'void',[],[]);
    clearAttachment(actor,M.base.add(0x4179a78),0);clearAttachment(actor,M.base.add(0x4179a68),0);
    if(slots.has(9)||slots.has(10))virtual(actor,0x758,'void',[],[]);
    updateEquipment(actor,0);
    if(actor.add(0x1531).readU8()!==0)updateAlternate(actor,1,actor.add(0x1ba18));
    updateAppearance(actor);
   }
   virtual(actor,0x1500,'void',['uint8'],[virtual(actor,0x6c0,'uint8',[],[])]);
   virtual(actor,0x1508,'void',['uint8'],[virtual(actor,0x6c0,'uint8',[],[])]);
   refreshModel(actor);
   }finally{cache.end();}
   const wire=new DataView(b.p.add(26).readByteArray(60)),provided={first:Array.from({length:7},(_,i)=>wire.getFloat32(i*4,false)),second:Array.from({length:7},(_,i)=>wire.getFloat32(28+i*4,false)),combat:wire.getFloat32(56,false)};
   const snapshot=cache.peer(g,actor,provided);remember(current,actor,unit,uid,snapshot);
   virtual(actor,0x1358,'void',['uint8','uint8'],[0,0]);virtual(actor,0x1418,'void',[],[]);
   const currentMP=virtual(actor,0x2a0,'float',[],[]),maximumMP=virtual(actor,0x2a8,'float',[],[]);
   if(!Number.isFinite(currentMP)||!Number.isFinite(maximumMP)||maximumMP<0)throw Error('Group wear original MP bounds');
   if(currentMP>maximumMP)virtual(actor,0x2f8,'void',['float','int','int'],[maximumMP,0,3]);
   applied++;emit('applied',{uid:uid.toString(),room,slots:Array.from(slots),applied,native_item_reader:'234B280',native_ability:'888CA0',auxiliary_state_replaced:false});
  } finally {for(const {raw}of items)disposeItem(raw);disposeVector(dto.add(4));}
 }
 function fail(error){disabled=true;advertisedAt=0;pending.length=0;pendingBytes=0;ownerRequest=null;ownerReport=null;emit('disabled',{reason:String(error),applied});}
 function frame(game){
  if(disabled||flushing)return;
  try{
   if(cache.failed()){fail(Error('Original native cache stopped'));return;}
   const current=currentGame();if(current===null)return;generation(current);
   if(ownerRequest&&cache.peerReady(current.g)){
    const supplied=cache.capture(current.g);if(supplied){
     if(supplied.uid!==ownerRequest.uid)throw Error('Group wear native report owner changed');
     const bytes=new Uint8Array(101),wire=new DataView(bytes.buffer);bytes[0]=3;bytes.set(ownerRequest.token,1);bytes.set(ownerRequest.room,17);bytes.set(ownerRequest.owner,33);
     [...supplied.first,...supplied.second,supplied.combat].forEach((value,i)=>wire.setFloat32(41+i*4,value,false));
     ownerReport={key:current.key,bytes:bytes.buffer,token:ownerRequest.token};ownerRequest=null;
    }
   }
   if(game!==null&&!current.g.equals(game)||!cache.peerReady(current.g))return;
   flushing=true;
   while(pending.length&&cache.peerReady(current.g)){
    const next=pending.shift();pendingBytes-=next.bytes.byteLength;
    if(next.key!==current.key){emit('obsolete',{reason:'native-game-generation-changed'});continue;}
    const raw=Memory.alloc(next.bytes.byteLength);raw.writeByteArray(next.bytes);
    const buffer=Memory.alloc(48);buffer.add(8).writePointer(raw);buffer.add(16).writePointer(raw.add(next.bytes.byteLength));buffer.add(24).writePointer(raw.add(next.bytes.byteLength));buffer.add(32).writeU32(0);
    consume(buffer,body(buffer));
   }
  }catch(error){fail(error);}finally{flushing=false;}
 }
 const replacement=new NativeCallback((self,a,b,kind,buffer)=>{
  const payload=body(buffer);
  if(inspected++<8)emit('route',{kind:String(kind),body:payload?{size:payload.size,offset:payload.offset,left:payload.left,prefix:hex(payload.p,Math.min(payload.left,12))}:null});
  if(payload===null||payload.left===0||![0x81,0x82,0x83].includes(payload.p.readU8()))return original(self,a,b,kind,buffer);
  if(payload.p.readU8()===0x83){
   if(payload.left!==19||payload.p.add(1).readU8()!==3||payload.p.add(18).readU8()>1){fail(Error('Group wear native report acknowledgement'));return 1;}
   buffer.add(0x20).writeU32(payload.size);emit('owner_report_ack',{obsolete:payload.p.add(18).readU8()===1});return 1;
  }
  try{
   if(disabled)throw Error('Group wear adapter disabled');
   const request=payload.p.readU8()===0x82;
   if(payload.left<(request?42:94)||payload.p.add(1).readU8()!==3||(request&&payload.left!==42))throw Error('Group wear delta header');
   const current=currentGame();buffer.add(0x20).writeU32(payload.size);
   if(current===null){emit('obsolete',{reason:'outside-original-dungeon'});return 1;}
   generation(current);
   if(request){
    const uid=uint64('0x'+hex(payload.p.add(34),8)).toString(),ownUID=cache.ownerUID(current.g);
    if(uid!==ownUID||ownerRequest||ownerReport)throw Error('Group wear native owner request order');
    ownerRequest={key:current.key,uid,token:Array.from(new Uint8Array(payload.p.add(2).readByteArray(16))),room:Array.from(new Uint8Array(payload.p.add(18).readByteArray(16))),owner:Array.from(new Uint8Array(payload.p.add(34).readByteArray(8)))};
    return 1;
   }
   // The same limits already bound this recipient's server mailbox. Store only
   // bytes and the native generation; resolve every Actor again at its frame.
   if(pending.length>=256||pendingBytes+payload.left>256*1024)throw Error('Group wear frame consumer full');
   const bytes=payload.p.readByteArray(payload.left);pending.push({key:current.key,bytes});pendingBytes+=bytes.byteLength;
  }catch(error){fail(error);}
  return 1;
 },'uint8',types);
 Interceptor.replace(dispatcher,replacement);
 // The original encoder borrows the event synchronously. Advertise support in
 // an existing nine-byte no-op; restore its kind before returning to its owner.
 hooks.push(Interceptor.attach(M.base.add(0x680b50),{onEnter(a){
  const event=a[1];this.event=null;
  if(event.add(0x10).readU32()!==0x202||event.add(0x34).readU16()!==0x7d0)return;
  if(!disabled&&cache.failed())fail(Error('Original native cache stopped'));
  const current=currentGame();
  if(ownerReport&&current&&ownerReport.key===current.key){
   this.event=event;this.saved=event.add(0x36).readByteArray(32);this.report=ownerReport;
   const raw=Memory.alloc(ownerReport.bytes.byteLength);raw.writeByteArray(ownerReport.bytes);this.storage=raw;
   event.add(0x34).writeU16(0xff22);event.add(0x36).writeU8(0);
   event.add(0x3e).writePointer(raw);event.add(0x46).writePointer(raw.add(ownerReport.bytes.byteLength));event.add(0x4e).writePointer(raw.add(ownerReport.bytes.byteLength));
  }else if(Date.now()-advertisedAt>=5000){this.event=event;event.add(0x34).writeU16(disabled?0xff21:0xff20);advertisedAt=Date.now();}
 },onLeave(result){
  if(this.event===null)return;
  try{
   if(this.saved){
    this.event.add(0x36).writeByteArray(this.saved);
    if(result.toInt32()===0)throw Error('Original native report encoder failed');
    if(ownerReport!==this.report)throw Error('Group wear report serialization ownership');
    ownerReport=null;emit('owner_report_encoded',{original_encoder:'680B50/3B6E1D0',bytes:101});
   }
  }catch(error){fail(error);}
  finally{this.event.add(0x34).writeU16(0x7d0);}
 }}));
 Interceptor.flush();
 const state={replacement,hooks,frame,refreshPeer,invalidateUnit(unit){initializedPeers.delete(unit.toString());},status(){return {disabled,applied,epoch,pending:pending.length,owner_request_pending:ownerRequest!==null,owner_report_pending:ownerReport!==null};}};globalThis.elsGroupWearSync=state;
 emit('ready',{marked_notification:0x106,marker:0x81,version:3,apply_boundary:'existing-native-cache-frame',original_EXE_changed:false});return state;
 };
}
