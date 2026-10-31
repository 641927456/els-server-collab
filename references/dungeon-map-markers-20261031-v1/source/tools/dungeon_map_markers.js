// Refresh the original map after the original current-part selection completes.
let elsDungeonMapMarkerSupport=null;
function installElsDungeonMapMarkers(){
 'use strict';
 if(elsDungeonMapMarkerSupport)return elsDungeonMapMarkerSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__DUNGEON_MAP_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Dungeon map native identity '+r);
 const validUI=new NativeFunction(module.base.add(0x4ab640),'bool',['pointer']);
 const getUI=new NativeFunction(module.base.add(0x4ab6d0),'pointer',['pointer']);
 const refresh=new NativeFunction(module.base.add(0x1070c20),'void',['pointer'],{exceptions:'propagate'});
 let stopped=false,hook;
 function stop(reason){
  if(stopped)return;stopped=true;hook.detach();
  send({event:'dungeon_map_markers_stopped',reason:String(reason),native_data_modified:false});
 }
 function current(game){
  const engine=module.base.add(0x4817e80).readPointer();if(engine.isNull())return null;
  const scene=engine.add(0x168).readPointer();if(scene.isNull())return null;
  const wrapper=scene.add(0x7e8).readPointer();if(wrapper.isNull()||!validUI(wrapper))return null;
  const parent=game.add(0x1440).readPointer();if(parent.isNull()||!wrapper.add(0x20).readPointer().equals(parent))return null;
  const definition=parent.readPointer(),ui=getUI(wrapper);if(definition.isNull()||ui.isNull())return null;
  const roster=module.base.add(0x4817e70).readPointer();if(roster.isNull())return null;
  const party=roster.add(0xc8).readPointer();if(party.isNull())return null;
  const member=party.add(0xa0).readPointer();if(member.isNull())return null;
  const job=member.add(0x29c0).readPointer();if(job.isNull())return null;
  return{engine,scene,wrapper,parent,definition,ui,roster,party,member,job,
   uid:member.add(0x48).readU32(),unitType:job.readU32(),stage:parent.add(0x10).readS32(),
   part:parent.add(8).readPointer(),map:definition.add(0x18).readS32()};
 }
 hook=Interceptor.attach(module.base.add(0x1040980),{
  onEnter(args){
   this.scope=null;if(stopped)return;
   try{const requested=args[1].toInt32();if(requested<0)return;
    const game=args[0],c=current(game);if(c)this.scope={game,requested,c};
   }catch(error){stop(error);}
  },
  onLeave(){
   const scope=this.scope;if(!scope||stopped)return;
   try{
    const a=scope.c,b=current(scope.game);if(!b)return;
    for(const key of ['engine','scene','wrapper','parent','definition','ui','roster','party','member','job'])if(!a[key].equals(b[key]))return;
    if(a.uid!==b.uid||a.unitType!==b.unitType||a.map!==b.map||a.stage!==b.stage||b.part.isNull()||b.part.add(0x10).readS32()!==scope.requested)return;
    refresh(b.wrapper);
    send({event:'dungeon_map_current_part_refreshed',map:b.map,stage:b.stage,part:scope.requested,uid:b.uid,native_renderer:true});
   }catch(error){stop(error);}
  }
 });
 elsDungeonMapMarkerSupport={stop,active:()=>!stopped};
 send({event:'dungeon_map_markers_ready',trigger:'original-current-part-selection-return',native_data_modified:false});
 return elsDungeonMapMarkerSupport;
}
