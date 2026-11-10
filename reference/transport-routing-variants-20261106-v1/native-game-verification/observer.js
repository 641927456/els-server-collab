// Owned native guest only. Original request factory/readers/scene remain intact.
const originalOwnedWeddingInstall=installElsGuildNativePower;
let ownedWeddingInstalled=false;
installElsGuildNativePower=function(){
 const support=originalOwnedWeddingInstall();if(ownedWeddingInstalled)return support;ownedWeddingInstalled=true;
 (()=>{
  const mod=Process.getModuleByName('x2_dx11.exe'),pins=__PINS__,directory=__DIRECTORY__;
  const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
  for(const[r,h]of Object.entries(pins))if(hex(mod.base.add(+r),h.length/2)!==h)throw Error('Owned wedding observation pin '+r);
  const scenario=JSON.parse(File.readAllText(directory+'/server-ready.json'));
  // The original wrapper locks the current shared connection and passes the
  // typed DTO in argument6 to DBFE10; it also releases the borrowed reference.
  const joinNative=new NativeFunction(mod.base.add(0xd34bd0),'bool',['pointer','pointer']);
  // Original StateWeddingGame UI59000 action sends417 and registers pending418.
  const exitNative=new NativeFunction(mod.base.add(0x2126c20),'void',['pointer','uint64','uint64','uint64','uint64']);
  let disabled=false,requested=false,reading=false,qualified=false,returned=false,exiting=false,first=0,frames=0,last=0;
  function fail(e){disabled=true;send({event:'owned_wedding_observer_failed',reason:String(e),stack:String(e.stack)});}
  function identity(){
   const engine=mod.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
   const manager=engine.add(0xc8).readPointer();if(manager.isNull())return null;
   const unit=manager.add(0xa0).readPointer();if(unit.isNull()||unit.add(0x48).readU64().toString()!==String(scenario.uid))return null;
   const state=mod.base.add(0x4817e80).readPointer();if(state.isNull())return null;
   return {engine,state:state.add(0x160).readS32(),scene:state.add(0x168).readPointer()};
  }
  Interceptor.attach(mod.base.add(0xd28770),{onEnter(){reading=true;},onLeave(){
   reading=false;send({event:'owned_wedding_original415_returned',full32_reader_qualified:qualified});
  }});
  Interceptor.attach(mod.base.add(0x74ffa0),{onEnter(a){this.kind=a[1].toInt32();},onLeave(r){
   if(this.kind===0x415||this.kind===0x418)send({event:'owned_wedding_original_pending_gate',kind:this.kind,accepted:r.toInt32()&255});
  }});
  Interceptor.attach(mod.base.add(0x909b60),{onLeave(){send({event:'owned_wedding_original_game_constructed'});}});
  Interceptor.attach(mod.base.add(0xd9bcc0),{onEnter(a){this.ours=reading;this.dto=a[1];},onLeave(){
   if(!this.ours||disabled)return;
   try{const p=this.dto;send({event:'owned_wedding_original_metadata',room_type:p.readU8(),
    maximum:p.add(0x50).readU8(),joined:p.add(0x51).readU8(),world:p.add(0xa1).readU16()});}catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0xdb7cf0),{onEnter(a){this.ours=reading&&this.returnAddress.equals(mod.base.add(0xd2888f));this.vector=a[1];},onLeave(){
   if(!this.ours||disabled)return;
   try{
    const begin=this.vector.readPointer(),end=this.vector.add(8).readPointer(),size=end.sub(begin).toInt32();
    if(size!==32*0x3e)throw Error('Original32-slot vector size '+size);
    const found=[];
    for(let i=0;i<32;i++){
     const s=begin.add(i*0x3e),m=s.add(10).readPointer(),tail=s.add(18).readPointer();
     if(tail.sub(m).toInt32()!==0x6b0)throw Error('Original FullUser size');
     const row={index:s.readU8(),uid:m.add(0xe1).readU64().toString(),role:m.add(0x48c).readU8(),
      first_port:m.add(0x137).readU16(),second_port:m.add(0x159).readU16()},expected=scenario.slots[i];
     if(row.index!==i||row.uid!==String(expected.uid)||row.role!==expected.role||row.first_port!==21100+i||row.second_port!==21100+i)throw Error('Original slot mismatch '+JSON.stringify(row));
     found.push(row);
    }
    qualified=true;send({event:'owned_wedding_original_full32_vector',slots:found,all_nested_readers_unmodified:true});
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x2126820),{onEnter(a){this.scene=a[0];},onLeave(){
   if(disabled)return;
   try{
    const v=identity();if(!v||v.state!==22||!qualified)return;
    if(!v.scene.equals(this.scene)||!this.scene.readPointer().equals(mod.base.add(0x42918e8)))throw Error('Original wedding scene identity');
    const room=mod.base.add(0x4817e38).readPointer();
    if(room.isNull()||!room.readPointer().equals(mod.base.add(0x415fed8)))throw Error('Original wedding room identity');
    frames++;if(!first)first=Date.now();
    if(Date.now()-last>=1000){last=Date.now();send({event:'owned_wedding_original_scene_frames',state:v.state,
      scene_vtable:'42918E8',game_vtable:'415FED8',frames,seconds:(Date.now()-first)/1000,
      remaining_exit_seconds:this.scene.add(0x67c).readFloat(),full32:true});}
    // Original2126C20 refuses exit while its native67C countdown is positive.
    // Read that original timer; do not rewrite it or submit a premature action.
    if(!exiting&&Date.now()-first>=scenario.minimum_scene_seconds*1000&&this.scene.add(0x67c).readFloat()<=0){
     exiting=true;exitNative(this.scene,uint64(0),uint64(0),uint64(59000),uint64(0));
     send({event:'owned_wedding_original417_requested',original_action:'StateWeddingGame2126C20 UI59000 with original418 pending',physical_input_actions:0});
    }
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x30d0660),{onLeave(){
   if(disabled)return;
   try{
    const v=identity();if(!v)return;
    if(!requested&&v.state===14){
     let status;try{status=JSON.parse(File.readAllText(directory+'/status.json'));}catch(e){return;}
     if(!status.protocol31_ready||status.phase!=='town_ready')return;
     const sender=v.engine.add(0xc0).readPointer();if(sender.isNull())return;
     const dto=Memory.alloc(46);dto.writeS8(3);dto.add(1).writeU64(0);dto.add(9).writeS32(scenario.reservation);
     dto.add(13).writeU8(0);dto.add(14+16).writeU64(0);dto.add(14+24).writeU64(7);
     const manager=v.engine.add(0x618).readPointer();if(manager.isNull())throw Error('Original current wedding hall manager absent');
     requested=true;const result=joinNative(manager,dto);
     send({event:'owned_wedding_original88B_requested',original_factory:'D34BD0 ->DAD010 ->DBFE10 and original415 pending',result,natural_GUI:false,physical_input_actions:0});
    }
    if(exiting&&v.state===14&&!returned){returned=true;send({event:'owned_wedding_original_town_return',state:v.state,frames,physical_input_actions:0});}
   }catch(e){fail(e);}
  }});
  send({event:'owned_wedding_observer_ready',natural_GUI:false,physical_input_actions:0});
 })();return support;
};
