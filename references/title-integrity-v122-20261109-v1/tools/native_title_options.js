function installElsTitleOptionData(){
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__TITLE_OPTION_PINS__;
 const bytes=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(bytes(module.base.add(+r),h.length/2)!==h)throw Error('Native title option identity '+r);
 const engine=module.base.add(0x4817e70).readPointer();
 if(engine.isNull())throw Error('Native title option engine absent');
 const manager=engine.add(0x4d8).readPointer();
 if(manager.isNull())throw Error('Native title option manager absent');
 const head=manager.readPointer();let node=head.add(8).readPointer(),found=head,steps=0;
 while(node.add(25).readU8()===0){
  if(++steps>64)throw Error('Native title option tree bound');
  if(node.add(32).readS32()<12360)node=node.add(16).readPointer();
  else{found=node;node=node.readPointer();}
 }
 if(found.equals(head)||found.add(32).readS32()!==12360)throw Error('Native newlywed title absent');
 const start=found.add(0xe0).readPointer(),end=found.add(0xe8).readPointer();
 if(end.sub(start).toInt32()!==8||start.readS32()!==87017)throw Error('Native newlywed option vector changed');
 const old=start.add(4).readS32();
 if(old!==87018&&old!==100003019)throw Error('Native newlywed drop option changed');
 if(old===87018){
  const app=module.base.add(0x4816400).readPointer();
  if(app.isNull())throw Error('Native title integrity app absent');
  const registry=app.add(0x320).readPointer();
  if(registry.isNull())throw Error('Native title integrity registry absent');
  // Title data was registered before this adjustment. Reuse the same native
  // refresh operation used after native object updates; it finds the record
  // by its object pointer and recomputes the registered callback checksum.
  const refresh=new NativeFunction(module.base.add(0x36d720),'uint8',['pointer','pointer'],{exceptions:'propagate'});
  start.add(4).writeS32(100003019);
  if(refresh(registry,found.add(32))!==1){
   start.add(4).writeS32(old);
   throw Error('Native title integrity refresh rejected');
  }
 }
 send({event:'native_title_option_data',title:12360,old_option:old,option:100003019,applied:old===87018,
  native_integrity_refreshed:old===87018,thread:Process.getCurrentThreadId(),existing_native_value:0.2,new_Hook:false});
}
