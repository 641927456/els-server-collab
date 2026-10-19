// Local scene compatibility: restore an owned Master spirit once after scene ready.
// D9 restores its data; 59F is advancement and must not be replayed on login.
const arM=Process.getModuleByName('x2_dx11.exe');
const arHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
for(const [r,h] of Object.entries(__ARTIFACT_PREFIXES__))if(arHex(arM.base.add(+r),8)!==h)throw Error('Artifact restore build mismatch '+r);
const arSpawn=new NativeFunction(arM.base.add(0x1310150),'void',['pointer','uint64','uint64','pointer','int'],{exceptions:'propagate'});
let arPending=0,arLast=0;
function arFind(manager,uid){
 const head=manager.add(0x70).readPointer();let node=head.add(8).readPointer();
 for(let i=0;i<64;i++){
  if(node.equals(head)||node.add(0x19).readU8())return ptr(0);
  const compare=node.add(0x20).readU64().compare(uid);
  if(compare===0)return node.add(0x28).readPointer();
  node=node.add(compare<0?16:0).readPointer();
 }
 throw Error('Artifact registry bounds');
}
Interceptor.attach(arM.base.add(0x682d80),{onEnter(a){
 const event=a[1];if(event.add(16).readU32()===0x202&&event.add(0x34).readU16()===0x227)arPending=Date.now();
}});
Interceptor.attach(arM.base.add(0x30d0660),{onEnter(a){this.state=a[0];},onLeave(){
 if(!arPending)return;const now=Date.now();if(now-arPending<2000||now-arLast<250)return;arLast=now;
 if(now-arPending>15000){arPending=0;send({event:'local_artifact_restore_timeout'});return;}
 try{
  const state=this.state;
  if(state.isNull()||!state.readPointer().add(0x188).readPointer().equals(arM.base.add(0x311c030)))return;
  const manager=arM.base.add(0x4817e70).readPointer(),game=manager.add(0xc8).readPointer();if(game.isNull())return;
  const unit=game.add(0xa0).readPointer();if(unit.isNull())return;
  const uid=unit.add(0x48).readU64(),artifact=manager.add(0x5f0).readPointer();
  if(uid.compare(1001)<0||uid.compare(1016)>0||artifact.isNull())return;
  if(unit.add(0x5c).readS32()!==2){arPending=0;return;}
  const role=unit.add(0x29c0).readPointer();if(role.isNull())return;
  const template=unit.add(0x2e30).readS32(),evolution=unit.add(0x2e34).readS32(),level=unit.add(0x2e38).readS32();
  if(template!==role.readS32()||template<1||template>15||evolution<1||evolution>5||level<1||level>99)return;
  arPending=0;let actor=arFind(artifact,uid);const existed=!actor.isNull();
  if(!existed){arSpawn(artifact,uid,0,unit.add(0x2e30),role.add(4).readS32());actor=arFind(artifact,uid);}
  send({event:'local_artifact_scene_restored',uid:uid.toString(),unit_class:role.add(4).readS32(),template,evolution,existing:existed,registered:!actor.isNull(),model:actor.isNull()?null:actor.add(0x678).readPointer().toString(),visible:actor.isNull()?null:actor.add(0x223).readU8(),original_creation:true});
 }catch(e){arPending=0;send({event:'local_artifact_restore_error',error:String(e)});}
}});
send({event:'local_artifact_restore_ready',original_creation:true});
