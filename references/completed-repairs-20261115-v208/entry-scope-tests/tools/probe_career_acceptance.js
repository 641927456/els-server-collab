// Owned disposable-save test. Send original item confirmation callbacks in order.
// NATIVE_USE_TEST_SCOPE: confirmation_only
// Starts at 2260FD0; does not prove inventory right-click dispatch or natural UI.
const m=Process.getModuleByName('x2_dx11.exe'),items=__ITEMS__;
const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
for(const [r,h] of Object.entries(__PREFIXES__))if(hex(m.base.add(+r),8)!==h)throw Error('Career acceptance build mismatch '+r);
let index=0,waiting=false,started=0,last=0,done=false,artifactSpawns=0;
const spawn=Interceptor.attach(m.base.add(0x1310150),{onEnter(a){artifactSpawns++;send({event:'career_artifact_spawn',template:a[3].readS32(),evolution:a[3].add(4).readS32()});}});
const hook=Interceptor.attach(m.base.add(0x30d0660),{onLeave(){if(done)return;try{
 const now=Date.now();if(now-last<500)return;last=now;
 const manager=m.base.add(0x4817e70).readPointer(),u=manager.add(0xc8).readPointer().add(0xa0).readPointer();
 if(u.isNull()||u.add(0x48).readU64().toString()!=='1001')return;
 if(!started)started=now;
 const cls=u.add(0x58).readU16(),stage=u.add(0x5c).readS32();
 if(waiting){
  const item=items[index];if(cls!==item.expected_class||stage!==item.expected_stage){if(now-started>20000)throw Error('Career callback did not update state '+index+' class='+cls+' stage='+stage);return;}
  send({event:'career_native_transition',index,unit_class:cls,stage,artifact:u.add(0x2e30).readS32(),artifact_evolution:u.add(0x2e34).readS32(),artifact_level:u.add(0x2e38).readS32(),artifact_spawns:artifactSpawns});
  waiting=false;index++;started=now;
 }
 if(index===items.length){done=true;hook.detach();spawn.detach();send({event:'career_acceptance_complete',transitions:index,artifact_spawns:artifactSpawns});return;}
 if(now-started<2000)return;
 const item=items[index],container=u.add(0x440);
 const p=new NativeFunction(m.base.add(0x197f500),'pointer',['pointer','uint64','uint8'])(container,item.uid,0);
 if(p.isNull()||p.readU64().toString()!==String(item.uid)||p.add(8).readU32()!==item.template)throw Error('Test item identity');
 const text=Memory.alloc(32);text.writeByteArray(Array(32).fill(0));text.add(24).writeU64(7);
 const controller=manager.add(0x558).readPointer().add(0x18).readPointer();
 waiting=true;started=now;
 new NativeFunction(m.base.add(0x2260fd0),'void',['pointer','uint64','uint64','uint64','uint8','pointer'])(controller,item.uid,0,0,0,text);
 send({event:'career_native_use_sent',index,item,callback:'0x2260fd0'});
}catch(e){done=true;hook.detach();spawn.detach();send({event:'career_acceptance_error',error:String(e)});}}});
setTimeout(()=>{hook.detach();spawn.detach();},120000);
