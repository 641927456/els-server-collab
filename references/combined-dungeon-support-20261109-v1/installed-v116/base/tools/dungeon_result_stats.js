// Send the original cumulative9E before BB/471; never change combat values.
function prepareElsDungeonResultStats(){
 'use strict';
 if(prepareElsDungeonResultStats.prepared)return prepareElsDungeonResultStats.prepared;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__DUNGEON_RESULT_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Dungeon result native identity '+r);
 const call=(r,t,a)=>new NativeFunction(module.base.add(r),t,a,{exceptions:'propagate'});
 const currentGame=call(0x159670,'pointer',['pointer']),actorOf=call(0x8571d0,'pointer',['pointer']);
 const report=call(0x1ab7ac0,'uint8',['pointer']);
 const writeInt=call(0x3b6dbd0,'bool',['pointer','int']),writeUID=call(0x3b6dda0,'bool',['pointer','uint64']),writeFloat=call(0x3b6dcc0,'bool',['pointer','float']);
 const writer=prepareElsReportWriter();
 function install(onGameThread){
 if(globalThis.elsDungeonResultStats)return globalThis.elsDungeonResultStats;
 if(typeof onGameThread!=='function')throw Error('Dungeon result original frame thread required');
 let active=true,busy=false,reports=0,epoch='',removeWriter=null;
 const hooks=[],stacks=new Map(),senders=new Map(),cooldown=new Map();
 const reference=module.base.add(0x478cb88);
 function owner(){
  if(!active||!onGameThread())return null;
  const ref=reference.readU64().toString(),game=currentGame(reference);
  if(game.isNull()||!game.readPointer().equals(module.base.add(0x41bfd28))||game.add(0x2d0).readS32()!==2)return null;
  const actor=actorOf(game),engine=module.base.add(0x4817e70).readPointer();
  if(actor.isNull()||engine.isNull())return null;
  const manager=engine.add(0xc8).readPointer();if(manager.isNull())return null;
  const unit=manager.add(0xa0).readPointer(),actorUnit=actor.add(0x1a3e0).readPointer();
  if(unit.isNull()||actorUnit.isNull())return null;
  const uid=unit.add(0x48).readU64().toString();
  if(uid!==actorUnit.add(0x48).readU64().toString()||ref!==reference.readU64().toString())throw Error('Dungeon statistics owner changed');
  return{ref,game,actor,unit,actorUnit,uid,tree:actorUnit.add(0x7c8),key:[ref,game,actor,actorUnit,uid].join(':')};
 }
 function generation(bound){if(epoch!==bound.key){epoch=bound.key;cooldown.clear();}}
 function parent(rva,kind){
  hooks.push(Interceptor.attach(module.base.add(rva),{onEnter(args){
   if(!active)return;
   this.thread=Process.getCurrentThreadId();const stack=stacks.get(this.thread)||[];
   // Every invocation is represented: nested remote trees mask local parents.
   this.frame={kind,bound:null,accelerationCommit:false};
   stack.push(this.frame);stacks.set(this.thread,stack);
   const bound=owner();if(!bound||!args[0].equals(bound.tree))return;
   if(kind==='discrete'){
    const index=args[3].toInt32();
    if(index<0||index>=22||!args[1].equals(bound.tree.add(0xc0+index*0x148)))return;
   }
   this.frame.bound=bound;
  },onLeave(){if(!active)return;const stack=stacks.get(this.thread);if(!stack||stack.pop()!==this.frame)throw Error('Dungeon cooldown native scope');if(!stack.length)stacks.delete(this.thread);}}));
 }
 function committed(rva,kind,register){
  hooks.push(Interceptor.attach(module.base.add(rva),{onEnter(){
   const stack=stacks.get(Process.getCurrentThreadId()),frame=stack&&stack[stack.length-1];
   if(!active||!frame||frame.kind!==kind||!frame.bound)return;
   // The acceleration join is also reached when native code skips the update.
   if(kind==='acceleration'){
    if(!frame.accelerationCommit)return;
    frame.accelerationCommit=false;
   }
   const bound=frame.bound,now=owner();if(!now||now.key!==bound.key)return;
   const pair=this.context[register].add(0x20),source=pair.readU64().toString(),delta=pair.add(8).readFloat();
   const node=this.context[register].add(0x30).readPointer();
   if(node.isNull()||node.add(0x20).readU64().toString()!==source)throw Error('Dungeon cooldown native commit owner');
   if(!Number.isFinite(delta)||delta<0)throw Error('Dungeon cooldown native delta');
   if(source==='0'||source===bound.uid||delta===0)return;
   generation(bound);cooldown.set(source,Math.fround((cooldown.get(source)||0)+delta));
  }}));
 }
 try{
 parent(0x8fe730,'discrete');parent(0x8f4830,'acceleration');
 hooks.push(Interceptor.attach(module.base.add(0x8f4c19),{onEnter(){
  const stack=stacks.get(Process.getCurrentThreadId()),frame=stack&&stack[stack.length-1];
  // This instruction follows the original insert/find call; skip branches bypass it.
  if(active&&frame&&frame.kind==='acceleration'&&frame.bound)frame.accelerationCommit=true;
 }}));
 committed(0x18ddeb3,'discrete','rsp');committed(0x8f4c2d,'acceleration','rbp');
 hooks.push(Interceptor.attach(module.base.add(0x1ab7ac0),{onEnter(args){
  if(!active)return;
  this.thread=Process.getCurrentThreadId();this.previous=senders.get(this.thread);
  const bound=owner();this.bound=bound&&args[0].equals(bound.game)?bound:null;
  senders.set(this.thread,this.bound);
 },onLeave(){if(!active)return;if(this.previous===undefined)senders.delete(this.thread);else senders.set(this.thread,this.previous);}}));
 removeWriter=writer.register('dungeon',function(stream){
  const expected=senders.get(Process.getCurrentThreadId());if(!active||!expected)return;
  const bound=owner();if(!bound||bound.key!==expected.key)throw Error('Dungeon cooldown report generation');
  generation(bound);const rows=[...cooldown].sort((a,b)=>uint64(a[0]).compare(uint64(b[0])));
  if(!writeInt(stream,0x50564531)||!writeInt(stream,rows.length))throw Error('Dungeon cooldown report header');
  for(const[uid,value]of rows)if(!writeUID(stream,uint64(uid))||!writeFloat(stream,value))throw Error('Dungeon cooldown report entry');
 });
 hooks.push(Interceptor.attach(module.base.add(0x682d80),{onEnter(args){
  if(!active||busy)return;
  const message=args[1];if(message.add(0x10).readU32()!==0x202)return;
  const kind=message.add(0x34).readU16();if(kind!==0xbb&&kind!==0x471)return;
    if(!onGameThread())throw Error('Dungeon result sender outside original game thread');
    const bound=owner();
    if(bound){
     const thread=Process.getCurrentThreadId(),previous=senders.get(thread);
     // Gum suppresses sender listeners during this nested original call.
     // Supply the same verified scope directly to the shared fast writer.
     senders.set(thread,bound);
     busy=true;
     try{if(report(bound.game)!==1)throw Error('Original dungeon report rejected');reports++;}
     finally{busy=false;if(previous===undefined)senders.delete(thread);else senders.set(thread,previous);}
    }
 }}));
 }catch(error){if(removeWriter)removeWriter();for(const hook of hooks)hook.detach();throw error;}
 const controller={reports:()=>reports,dispose(){if(!active)return;active=false;removeWriter();for(const hook of hooks)hook.detach();stacks.clear();senders.clear();cooldown.clear();delete globalThis.elsDungeonResultStats;}};
 globalThis.elsDungeonResultStats=controller;
 send({event:'dungeon_result_stats_ready',original_report:true,EXE_KOM_modified:false});
 return controller;
 }
 prepareElsDungeonResultStats.prepared=install;
 return install;
}
function installElsDungeonResultStats(onGameThread){
 return prepareElsDungeonResultStats()(onGameThread);
}
