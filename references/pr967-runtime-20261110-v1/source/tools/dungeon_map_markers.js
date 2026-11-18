// Refresh after selection and draw missing Boss-room markers on original nodes.
let elsDungeonMapMarkerSupport=null;
function installElsDungeonMapMarkers(){
 'use strict';
 if(elsDungeonMapMarkerSupport)return elsDungeonMapMarkerSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__DUNGEON_MAP_PINS__,aliases=__DUNGEON_MAP_ALIASES__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Dungeon map native identity '+r);
 const validUI=new NativeFunction(module.base.add(0x4ab640),'bool',['pointer']);
 const getUI=new NativeFunction(module.base.add(0x4ab6d0),'pointer',['pointer']);
 const refresh=new NativeFunction(module.base.add(0x1070c20),'void',['pointer'],{exceptions:'propagate'});
 const marker=new NativeFunction(module.base.add(0x3556210),'void',['pointer','pointer','pointer','pointer','pointer','pointer'],{exceptions:'propagate'});
 const layout=new NativeFunction(module.base.add(0x3554020),'void',['pointer'],{exceptions:'propagate'});
 let stopped=false;const hooks=[];
 function stop(reason){
  if(stopped)return;stopped=true;hooks.forEach(h=>h.detach());
  send({event:'dungeon_map_markers_stopped',reason:String(reason),native_data_modified:false});
 }
 function current(game){
  const engine=module.base.add(0x4817e80).readPointer();if(engine.isNull())return null;
  const scene=engine.add(0x168).readPointer();if(scene.isNull())return null;
  const wrapper=scene.add(0x7e8).readPointer();if(wrapper.isNull()||!validUI(wrapper))return null;
  const parent=wrapper.add(0x20).readPointer();if(parent.isNull()||(game&&!game.add(0x1440).readPointer().equals(parent)))return null;
  const definition=parent.readPointer(),ui=getUI(wrapper);if(definition.isNull()||ui.isNull())return null;
  const roster=module.base.add(0x4817e70).readPointer();if(roster.isNull())return null;
  const party=roster.add(0xc8).readPointer();if(party.isNull())return null;
  const member=party.add(0xa0).readPointer();if(member.isNull())return null;
  const job=member.add(0x29c0).readPointer();if(job.isNull())return null;
  return{engine,scene,wrapper,parent,definition,ui,roster,party,member,job,
   uid:member.add(0x48).readU32(),unitType:job.readU32(),stage:parent.add(0x10).readS32(),
   part:parent.add(8).readPointer(),map:definition.add(0x18).readS32()};
 }
 function same(a,b){
  if(!b)return false;
  for(const key of ['engine','scene','wrapper','parent','definition','ui','roster','party','member','job'])if(!a[key].equals(b[key]))return false;
  return a.uid===b.uid&&a.unitType===b.unitType&&a.map===b.map&&a.stage===b.stage;
 }
 function node(parent,stage,part){
  const head=parent.add(0x38).readPointer();let item=head.add(8).readPointer();
  while(item.add(0x19).readU8()===0){
   const s=item.add(0x1c).readS32(),p=item.add(0x20).readS32();
   if(s===stage&&p===part)return item;
   item=item.add(s<stage||(s===stage&&p<part)?16:0).readPointer();
  }
  return null;
 }
 try{
 hooks.push(Interceptor.attach(module.base.add(0x1040980),{
  onEnter(args){
   this.scope=null;if(stopped)return;
   try{const requested=args[1].toInt32();if(requested<0)return;
    const game=args[0],c=current(game);if(c)this.scope={game,requested,c};
   }catch(error){stop(error);}
  },
  onLeave(){
   const scope=this.scope;if(!scope||stopped)return;
   try{
    const a=scope.c,b=current(scope.game);
    if(!same(a,b)||b.part.isNull()||b.part.add(0x10).readS32()!==scope.requested)return;
    refresh(b.wrapper);
    const c=current(scope.game);
    if(!same(b,c)||c.part.isNull()||!c.part.equals(b.part)||c.part.add(0x10).readS32()!==scope.requested)return;
    const alias=aliases[c.map];
    if(alias&&c.stage===alias.stage&&scope.requested===alias.part&&!node(c.parent,c.stage,scope.requested)){
     const target=node(c.parent,alias.toStage,alias.toPart);
     if(!target||c.parent.add(0x40).readU64().toNumber()!==alias.nodes||target.add(0x24).readFloat()!==alias.x||target.add(0x28).readFloat()!==alias.y)throw Error('Dungeon map source node identity '+c.map);
     const unit=Memory.alloc(4),uid=Memory.alloc(4),stage=Memory.alloc(4),part=Memory.alloc(4),color=Memory.alloc(8);
     unit.writeU32(c.unitType);uid.writeU32(c.uid);stage.writeS32(alias.toStage);part.writeS32(alias.toPart);color.writeFloat(1);color.add(4).writeFloat(1);
     marker(c.ui,unit,uid,stage,part,color);layout(c.ui);
     send({event:'dungeon_map_source_boss_marker',map:c.map,stage:c.stage,part:scope.requested,node_stage:alias.toStage,node_part:alias.toPart,uid:c.uid,native_renderer:true});
    }
    send({event:'dungeon_map_current_part_refreshed',map:b.map,stage:b.stage,part:scope.requested,uid:b.uid,native_renderer:true});
   }catch(error){stop(error);}
  }
 }));
 }catch(error){stop(error);throw error;}
 elsDungeonMapMarkerSupport={stop,active:()=>!stopped};
 send({event:'dungeon_map_markers_ready',trigger:'original-current-part-selection-return',source_boss_nodes:Object.keys(aliases),native_data_modified:false});
 return elsDungeonMapMarkerSupport;
}
