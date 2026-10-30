// Restore two resource-proven room markers through the original UI consumer.
let elsDungeonMapMarkerSupport=null;
function installElsDungeonMapMarkers(){
 'use strict';
 if(elsDungeonMapMarkerSupport)return elsDungeonMapMarkerSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__DUNGEON_MAP_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Dungeon map native identity '+r);
 const validUI=new NativeFunction(module.base.add(0x4ab640),'bool',['pointer']);
 const getUI=new NativeFunction(module.base.add(0x4ab6d0),'pointer',['pointer']);
 const marker=new NativeFunction(module.base.add(0x3556210),'void',['pointer','pointer','pointer','pointer','pointer','pointer']);
 const aliases={33232:{stage:4,part:0,toStage:3,toPart:0,nodes:8,x:424,y:14},35301:{stage:2,part:0,toStage:1,toPart:0,nodes:4,x:282,y:37}};
 const contexts=new Map(),hooks=[];let stopped=false;
 function node(parent,stage,part){
  const head=parent.add(0x38).readPointer();let item=head.add(8).readPointer();
  while(item.add(0x19).readU8()===0){
   const s=item.add(0x1c).readS32(),p=item.add(0x20).readS32();
   if(s===stage&&p===part)return item;
   item=item.add(s<stage||(s===stage&&p<part)?16:0).readPointer();
  }
  return null;
 }
 function selected(){
  const engine=module.base.add(0x4817e70).readPointer();if(engine.isNull())return null;
  const party=engine.add(0xc8).readPointer();if(party.isNull())return null;
  const member=party.add(0xa0).readPointer();if(member.isNull())return null;
  const job=member.add(0x29c0).readPointer();
  return{member,uid:member.add(0x48).readU32(),job:job.isNull()?0:job.readU32()};
 }
 function stop(reason){
  if(stopped)return;stopped=true;
  hooks.forEach(h=>h.detach());contexts.clear();
  send({event:'dungeon_map_markers_stopped',reason:String(reason),native_data_modified:false});
 }
 hooks.push(Interceptor.attach(module.base.add(0x1070c20),{
  onEnter(args){
   this.scope=null;
   if(stopped)return;
   try{
    const wrapper=args[0];if(!validUI(wrapper))return;
    const parent=wrapper.add(0x20).readPointer();if(parent.isNull())return;
    const definition=parent.readPointer();if(definition.isNull())return;
    const id=definition.add(0x18).readS32(),a=aliases[id];if(!a)return;
    const stage=parent.add(0x10).readS32(),partObject=parent.add(8).readPointer();if(partObject.isNull())return;
    const part=partObject.add(0x10).readS32();if(stage!==a.stage||part!==a.part||node(parent,stage,part))return;
    const target=node(parent,a.toStage,a.toPart);
    if(!target||parent.add(0x40).readU64().toNumber()!==a.nodes||target.add(0x24).readFloat()!==a.x||target.add(0x28).readFloat()!==a.y)throw Error('Dungeon map original resource identity '+id);
    const ui=getUI(wrapper);if(ui.isNull()||ui.add(0xa0).readU8()!==1)return;
    const owner=selected();if(!owner)return;
    const tid=Process.getCurrentThreadId(),stack=contexts.get(tid)||[];
    const scope={wrapper,parent,definition,id,stage,part,partObject,ui,owner,a,done:false,tid};
    stack.push(scope);contexts.set(tid,stack);this.scope=scope;
   }catch(error){stop(error);}
  },
  onLeave(){
   const c=this.scope;if(!c||stopped)return;
   const stack=contexts.get(c.tid);if(!stack||stack.pop()!==c){stop('Dungeon map callback scope');return;}
   if(!stack.length)contexts.delete(c.tid);
  }
 }));
 hooks.push(Interceptor.attach(module.base.add(0x3554020),{
  onEnter(args){
   if(stopped||!this.returnAddress.equals(module.base.add(0x10710da)))return;
   try{
    const stack=contexts.get(Process.getCurrentThreadId()),c=stack&&stack[stack.length-1];
    if(!c||c.done||!args[0].equals(c.ui))return;
    if(!c.wrapper.add(0x20).readPointer().equals(c.parent)||!c.parent.readPointer().equals(c.definition)||!c.parent.add(8).readPointer().equals(c.partObject)||c.definition.add(0x18).readS32()!==c.id||c.parent.add(0x10).readS32()!==c.stage||c.partObject.add(0x10).readS32()!==c.part||c.ui.add(0xa0).readU8()!==1)return;
    const owner=selected();if(!owner||!owner.member.equals(c.owner.member)||owner.uid!==c.owner.uid||owner.job!==c.owner.job)return;
    c.done=true;
    const job=Memory.alloc(4),uid=Memory.alloc(4),stage=Memory.alloc(4),part=Memory.alloc(4),color=Memory.alloc(8);
    job.writeU32(owner.job);uid.writeU32(owner.uid);stage.writeS32(c.a.toStage);part.writeS32(c.a.toPart);color.writeFloat(1);color.add(4).writeFloat(1);
    marker(c.ui,job,uid,stage,part,color);
   }catch(error){stop(error);}
  }
 }));
 elsDungeonMapMarkerSupport={stop,active:()=>!stopped};
 send({event:'dungeon_map_markers_ready',maps:[33232,35301],native_data_modified:false});
 return elsDungeonMapMarkerSupport;
}
