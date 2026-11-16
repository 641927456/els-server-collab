let elsIdolTitlesState=null;
function installElsIdolTitles(){
 if(elsIdolTitlesState!==null)throw Error('Idol title initialization repeated');
 const module=Process.getModuleByName('x2_dx11.exe'),base=module.base;
 const pins=__IDOL_PINS__,sites=__IDOL_SITES__,functions=__IDOL_FUNCTIONS__;
 const definition=__IDOL_DEFINITIONS__,chunk=__IDOL_CHUNK__;
 const bytes=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 function identity(){for(const[r,h]of Object.entries(pins))if(bytes(base.add(+r),h.length/2)!==h)throw Error('Idol title native identity '+r);}
 identity();
 const engine=base.add(0x4817e70).readPointer(),service=base.add(0x48163b8).readPointer();
 if(engine.isNull()||service.isNull())throw Error('Idol title native services absent');
 const vm=service.add(8).readPointer(),options=engine.add(0x4c0).readPointer();
 const buffManager=new NativeFunction(base.add(0x7ecd30),'pointer',[],{exceptions:'propagate'})();
 if(vm.isNull()||options.isNull()||buffManager.isNull())throw Error('Idol title native registries absent');
 const lookup=new NativeFunction(base.add(0xa18590),'pointer',['pointer','uint32'],{exceptions:'propagate'});
 const countFactors=()=>buffManager.add(0x18).readPointer().sub(buffManager.add(0x10).readPointer()).toInt32()/8;
 if(countFactors()!==definition.native_factor_count_before)throw Error('Idol title factor reservation changed');
 for(const row of definition.options)if(!lookup(options,row.ID).isNull())throw Error('Idol title option ID already occupied '+row.ID);
 function integerNode(manager,id){
  const head=manager.readPointer();let p=head.add(8).readPointer(),found=head;
  while(p.add(25).readU8()===0){if(p.add(32).readS32()<id)p=p.add(16).readPointer();else{found=p;p=p.readPointer();}}
  return !found.equals(head)&&found.add(32).readS32()===id?found:null;
 }
 for(const row of definition.templates)if(integerNode(buffManager,row.BUFF_TEMPLET_ID)!==null)throw Error('Idol title template ID already occupied '+row.BUFF_TEMPLET_ID);
 const titleManager=engine.add(0x4d8).readPointer(),titleHead=titleManager.readPointer(),titleNodes=[];
 for(const row of definition.titles){
  let p=titleHead.add(8).readPointer(),found=titleHead;
  while(p.add(25).readU8()===0){if(p.add(32).readS32()<row.title)p=p.add(16).readPointer();else{found=p;p=p.readPointer();}}
  if(found.equals(titleHead)||found.add(32).readS32()!==row.title)throw Error('Idol title definition absent '+row.title);
  titleNodes.push(found);
 }
 const registry=base.add(0x4816400).readPointer().add(0x320).readPointer();
 const refresh=new NativeFunction(base.add(0x36d720),'uint8',['pointer','pointer'],{exceptions:'propagate'});
 const assignText=new NativeFunction(base.add(0x164530),'pointer',['pointer','pointer','uint64'],{exceptions:'propagate'});
 const oldText=titleNodes.flatMap(node=>[56,88].map(offset=>{
  const field=node.add(offset),length=field.add(16).readU64().toNumber(),capacity=field.add(24).readU64().toNumber();
  return {field,text:(capacity<8?field:field.readPointer()).readUtf16String(length),length};
 }));
 const symbols={game_handle:base.add(0x478cb88),dungeon_vtable:base.add(0x41bfd28),engine_global:base.add(0x4817e70)};
 for(const[name,rva]of Object.entries(functions))symbols[name]=base.add(rva);
 for(const name of Object.keys(sites)){symbols[name+'_slot']=Memory.alloc(8);symbols[name+'_slot'].writePointer(ptr(0));}
 const cm=new CModule(__IDOL_CODE__,symbols),applied=[];
 // Keep the compiled module and slots alive for the lifetime of redirected code.
 elsIdolTitlesState={status:'registering',cm,symbols,applied};
 const code=Memory.alloc(chunk.length);code.writeByteArray(chunk);
 const execute=new NativeFunction(base.add(0x3933fe0),'uint8',['pointer','pointer','uint64'],{exceptions:'propagate'});
 const stackDepth=()=>vm.add(0x28).readPointer().sub(vm.add(0x20).readPointer()).toInt32();
 const beforeStack=stackDepth(),beforeTemplates=buffManager.add(8).readU64().toNumber();
 const registrationName=Memory.allocUtf8String('__ELS_IdolTitleSocketRegistration');
 const pushClosure=new NativeFunction(base.add(0x3936ed0),'void',['pointer','pointer','int'],{exceptions:'propagate'});
 const setField=new NativeFunction(base.add(0x3937740),'void',['pointer','int','pointer'],{exceptions:'propagate'});
 const pushString=new NativeFunction(base.add(0x3936df0),'void',['pointer','pointer'],{exceptions:'propagate'});
 const setTop=new NativeFunction(base.add(0x39363f0),'void',['pointer','int'],{exceptions:'propagate'});
 try{
  try{
   pushClosure(vm,cm.idol_register_socket,0);
   setField(vm,-10002,registrationName);
   if(execute(vm,code,chunk.length)!==1)throw Error('Idol title native registration rejected');
   if(stackDepth()!==beforeStack)throw Error('Idol title registration stack imbalance');
  }finally{
   setTop(vm,beforeStack/8);
   try{
    pushString(vm,ptr(0));
    setField(vm,-10002,registrationName);
   }finally{setTop(vm,beforeStack/8);}
  }
  if(countFactors()!==definition.native_factor_count_before+definition.factors.length)throw Error('Idol title factors were not registered');
  if(buffManager.add(8).readU64().toNumber()!==beforeTemplates+definition.templates.length)throw Error('Idol title templates were not registered');
  for(const row of definition.options)if(lookup(options,row.ID).isNull())throw Error('Idol title option registration missing '+row.ID);
  for(const node of titleNodes)if(refresh(registry,node.add(32))!==1)throw Error('Idol title description integrity refresh failed');
  for(const[name,rva]of Object.entries(sites)){
   const site=base.add(rva),original=Interceptor.replaceFast(site,cm['idol_'+name]);
   symbols[name+'_slot'].writePointer(original);applied.push(site);
  }
  Interceptor.flush();
  elsIdolTitlesState.status='ready';
  send({event:'idol_titles_ready',titles:definition.titles.map(r=>r.title),registrations:definition.templates.length+definition.factors.length+definition.options.length+definition.effects.length,thread:Process.getCurrentThreadId()});
 }catch(error){
  const rollback=[];
  for(const site of [...applied].reverse())try{Interceptor.revert(site);}catch(e){rollback.push(String(e));}
  try{Interceptor.flush();}catch(e){rollback.push(String(e));}
  try{identity();}catch(e){rollback.push(String(e));}
  for(const row of oldText)try{assignText(row.field,Memory.allocUtf16String(row.text),row.length);}catch(e){rollback.push(String(e));}
  for(const node of titleNodes)try{if(refresh(registry,node.add(32))!==1)throw Error('Description rollback integrity');}catch(e){rollback.push(String(e));}
  elsIdolTitlesState.status='failed';
  // New gameplay definitions have no users without the adapter. Never retry into
  // a partially populated registry or claim successful removal of definitions.
  throw Error('Idol title installation failed: '+error+(rollback.length?'; rollback: '+rollback.join('; '):''));
 }
}
