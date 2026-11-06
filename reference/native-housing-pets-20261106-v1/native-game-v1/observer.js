// One owned original client; complete native requests and original scene code.
const originalOwnedHousingInstall=installElsGuildNativePower;
let ownedHousingInstalled=false;
installElsGuildNativePower=function(){
 const support=originalOwnedHousingInstall();if(ownedHousingInstalled)return support;ownedHousingInstalled=true;
 (()=>{
  const mod=Process.getModuleByName('x2_dx11.exe'),pins=__PINS__,directory=__DIRECTORY__;
  const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
  for(const[r,h]of Object.entries(pins))if(hex(mod.base.add(+r),h.length/2)!==h)throw Error('Owned housing pin '+r);
  const scenario=JSON.parse(File.readAllText(directory+'/server-ready.json'));
  const entry=new NativeFunction(mod.base.add(0xbdeab0),'void',['pointer','uint64','int','uint64']);
  const action=new NativeFunction(mod.base.add(0x3287520),'void',['pointer','pointer','uint32','uint64','pointer']);
  const body=Memory.alloc(9);body.writeU8(1);body.add(1).writeU64(scenario.pet_uid);
  let disabled=false,entered=false,population=false,own=false,placed=false,retrieved=false,placeSent=false,removeSent=false,done=false;
  let frames=0,first=0,last=0,placeAt=0,removeAt=0,lastSample=0,projectionSignature='';const gates=[];
  function write(name,value){const f=new File(directory+'/'+name,'w');f.write(JSON.stringify(value));f.flush();f.close();}
  function fail(e){disabled=true;const v={ok:false,reason:String(e),stack:String(e.stack)};send({event:'owned_housing_observer_failed',...v});write('native-observer-failure.json',v);}
  function identity(){
   const engine=mod.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
   const cache=engine.add(0xc8).readPointer();if(cache.isNull())return null;
   const user=cache.add(0xa0).readPointer();if(user.isNull()||user.add(0x48).readU64().toString()!==String(scenario.uid))return null;
   const state=mod.base.add(0x4817e80).readPointer();if(state.isNull())return null;
   return{engine,state:state.add(0x160).readS32(),scene:state.add(0x168).readPointer()};
  }
  function placedPets(){
   const manager=mod.base.add(0x4817f30).readPointer();if(manager.isNull())return[];
   const set=manager.add(manager.add(0x1a0).readU8()===1?0x360:0x370),head=set.readPointer(),found=[];
   function visit(p){if(p.equals(head))return;if(found.length>4)throw Error('Owned placed set bound');visit(p.readPointer());found.push(p.add(0x24).readU64().toString());visit(p.add(16).readPointer());}
   visit(head.add(8).readPointer());return found;
  }
  function entities(v){
   const manager=v.engine.add(0x5e8).readPointer();if(manager.isNull())return[];
   const game=mod.base.add(0x4817e58).readPointer();if(game.isNull())return[];
   // Original2451350 stores the selected mat item's UID in Game+B00;
   // 2460890/2DAF6B0 key the pet manager by that mat, not the character UID.
   const target=game.add(0xb00).readU64();if(target.compare(uint64(scenario.mat_uid))!==0)return[];
   const head=manager.add(0x88).readPointer();let p=head.add(8).readPointer();
   for(let n=0;n<64&&!p.equals(head);n++){
    const comparison=p.add(0x20).readU64().compare(target);
    if(comparison===0){
     const begin=p.add(0x28).readPointer(),end=p.add(0x30).readPointer(),size=end.sub(begin).toInt32();
     if(size<0||size%8||size>32)throw Error('Owned housing pet entity vector '+size);
     const rows=[];for(let i=0;i<size/8;i++){const pet=begin.add(i*8).readPointer();rows.push({uid:pet.add(0x9a8).readU64().toString(),vtable:pet.readPointer().sub(mod.base).toString()});}return rows;
    }
    p=p.add(comparison<0?16:0).readPointer();
   }return[];
  }
  function projection(v){
   const pets=placedPets(),actors=entities(v),game=mod.base.add(0x4817e58).readPointer();
   if(placeSent&&pets.includes(String(scenario.pet_uid))&&actors.some(p=>p.uid===String(scenario.pet_uid)))placed=true;
   if(removeSent&&!pets.length&&!actors.some(p=>p.uid===String(scenario.pet_uid)))retrieved=true;
   const value={pets,entities:actors,placed,retrieved,mat_uid:String(scenario.mat_uid),native_mat_uid:game.add(0xb00).readU64().toString()};
   const signature=JSON.stringify(value);if(signature!==projectionSignature){projectionSignature=signature;send({event:'owned_housing_original_pet_projection',...value});}
  }
  Interceptor.attach(mod.base.add(0x244b250),{onEnter(a){
   if(disabled)return;try{send({event:'owned_housing_original_layout_spawn',legacy_count:a[0].add(0x980).readU64().toString(),modern_count:a[0].add(0x990).readU64().toString(),native_grid_size:a[0].add(0x9e0).readS32()});}catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x244d960),{onEnter(a){
   this.game=a[0];this.out=a[1];this.dto=a[2];this.flag=a[3].toInt32()&255;
   this.template=this.dto.add(8).readS32();
   if(disabled||this.template!==570234)return;
   try{
    const manager=mod.base.add(0x4817f30).readPointer(),head=manager.add(8).readPointer();let p=head.add(8).readPointer(),model=null,found=false;
    for(let n=0;n<64&&!p.equals(head);n++){
     const key=p.add(0x20).readS32();if(key===this.template){found=true;model=p.add(0x68).readPointer().toString();break;}p=p.add(key<this.template?16:0).readPointer();
    }
    send({event:'owned_housing_original_mat_factory_input',uid:this.dto.readU64().toString(),template:this.template,position:this.dto.add(12).readS32(),xyz:[16,20,24].map(x=>this.dto.add(x).readFloat()),flag:this.flag,template_found:found,model});
   }catch(e){fail(e);}
  },onLeave(){
   if(disabled||this.template!==570234)return;try{const entity=this.out.readPointer();send({event:'owned_housing_original_mat_factory_result',entity:entity.toString(),native_mat_uid:this.game.add(0xb00).readU64().toString()});}catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x2451350),{onEnter(a){this.game=a[0];this.item=a[1].readPointer();},onLeave(){
   if(disabled||this.item.isNull())return;try{
    const tag=this.item.add(0x278).readU8(),template=this.item.add(tag===0?0x297:0x303).readS32();
    if(template!==570234)return;
    const spec=this.item.add(0x280).readPointer();
    send({event:'owned_housing_original_mat_applied',tag,template,uid:this.item.add(tag===0?0x28f:0x2fb).readU64().toString(),special_type:spec.isNull()?null:spec.add(0x220).readS32(),native_mat_uid:this.game.add(0xb00).readU64().toString()});
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x2daf6b0),{onEnter(a){
   if(disabled)return;try{send({event:'owned_housing_original_pet_factory',mat_uid:a[1].toString(),pet_uid:a[2].readU64().toString(),unit:a[2].add(8).readS32()});}catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x74ffa0),{onEnter(a){this.kind=a[1].toInt32();},onLeave(r){
   if([0x924,0x92f,0xa39,0xa3b].includes(this.kind)){const row={kind:this.kind,accepted:r.toInt32()&255};gates.push(row);send({event:'owned_housing_original_pending_gate',...row});}
  }});
  Interceptor.attach(mod.base.add(0x328f7d0),{onLeave(){population=true;send({event:'owned_housing_original92F_returned'});}});
  Interceptor.attach(mod.base.add(0x21460e0),{onEnter(a){this.game=a[0];this.current=a[1];},onLeave(r){
   if(disabled)return;try{
    const v=identity();if(!v||v.state!==29||this.current.add(0x48).readU64().toString()!==String(scenario.uid))return;
    if(r.isNull()||!r.add(0x270).readPointer().equals(this.current)||!this.game.add(8).readPointer().equals(r))throw Error('Original self actor identity');
    own=true;send({event:'owned_housing_original_self_actor_created',uid:String(scenario.uid),actor_vtable:r.readPointer().sub(mod.base).toString(),game_vtable:this.game.readPointer().sub(mod.base).toString(),identity_source:'actor+270 matches current NativeUser; Game+8 is returned self actor'});
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x2460890),{onLeave(){
   if(disabled)return;try{
    const v=identity();if(!v||v.state!==29)return;
    projection(v);
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x3286550),{onEnter(a){this.scene=a[0];},onLeave(){
   if(disabled)return;try{
    const v=identity();if(!v||v.state!==29||!v.scene.equals(this.scene))return;
    if(!v.scene.readPointer().equals(mod.base.add(0x4302e90)))throw Error('Original StateHousing identity');
    frames++;if(!first)first=Date.now();
    if(Date.now()-lastSample>50){lastSample=Date.now();projection(v);}
    if(Date.now()-last>=1000){last=Date.now();send({event:'owned_housing_original_scene_frames',state:v.state,frames,seconds:(Date.now()-first)/1000,population,own,placed,retrieved});}
    if(population&&own&&!placeSent&&Date.now()-first>1500){placeSent=true;placeAt=Date.now();action(v.scene,ptr(0),0,uint64(0x17f5e),body);send({event:'owned_housing_original_A38_requested',original:'3287520 UI17F5E with originalA39 pending'});}
    if(placed&&!removeSent&&Date.now()-placeAt>2000){removeSent=true;removeAt=Date.now();action(v.scene,ptr(0),0,uint64(0x17f60),body);send({event:'owned_housing_original_A3A_requested',original:'3287520 UI17F60 with originalA3B pending'});}
    if(placeSent&&!placed&&Date.now()-placeAt>30000)throw Error('Original housing pet placement did not project');
    if(removeSent&&!retrieved&&Date.now()-removeAt>30000)throw Error('Original housing pet retrieval did not project');
    if(!done&&own&&placed&&retrieved&&Date.now()-first>=scenario.minimum_scene_seconds*1000){
     done=true;const result={ok:true,uid:String(scenario.uid),pet_uid:String(scenario.pet_uid),state:v.state,frames,seconds:(Date.now()-first)/1000,
      original_self_actor:true,original_placed_pet_entity:true,original_retrieved_entity:true,pending_gates:gates,natural_GUI:false,physical_input_actions:0};
     write('native-observer-complete.json',result);send({event:'owned_housing_original_scene_complete',...result});
    }
   }catch(e){fail(e);}
  }});
  Interceptor.attach(mod.base.add(0x30d0660),{onLeave(){
   if(disabled||entered)return;try{
    const v=identity();if(!v||v.state!==14)return;let status;try{status=JSON.parse(File.readAllText(directory+'/status.json'));}catch(e){return;}
    if(status.phase!=='town_ready')return;
    entered=true;entry(v.scene,uint64(0),1,uint64(0));send({event:'owned_housing_original923_requested',original:'BDEAB0 complete current-State own-room action with original924 pending',physical_input_actions:0});
   }catch(e){fail(e);}
  }});
  send({event:'owned_housing_observer_ready',natural_GUI:false,physical_input_actions:0});
 })();return support;
};
