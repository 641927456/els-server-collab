'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(process.argv[2],'utf8');
function harness(badPin=false){
 const memory=new Map(),events=[],hooks=[];let next=0x1000000n;
 class P{
  constructor(value){this.v=BigInt(value);}
  add(n){return new P(this.v+BigInt(n));}
  equals(p){return this.v===p.v;}
  isNull(){return this.v===0n;}
  readPointer(){return memory.get(this.v)||new P(0);}
  readU32(){return memory.get(this.v)||0;}
  readU16(){return this.readU32();}
  readU8(){return this.readU32();}
  readUtf16String(n){const s=memory.get(this.v)||'';return n===undefined?s:s.slice(0,n);}
  readByteArray(n){const b=new Uint8Array(n);if(badPin)b[0]=1;return b.buffer;}
 }
 const base=new P(0x140000000n),pointer=value=>new P(value),string=value=>{const p=pointer(next);next+=0x1000n;memory.set(p.v,value);return p;};
 const context=vm.createContext({Process:{getModuleByName:()=>({base})},Memory:{allocUtf16String:string},
  Interceptor:{attach:(address,callbacks)=>{const hook={address,callbacks,detached:false};hooks.push(hook);return{detach(){hook.detached=true;}};}},send:event=>events.push(event)});
 vm.runInContext(source,context);const install=()=>vm.runInContext('installElsGroundModels()',context);
 function invoke(original,type=3,position=24,ground=true,nullOutput=false,mismatch=false){
  const object=pointer(0x10000),definition=pointer(0x20000),pool=pointer(0x30000),output=pointer(0x40000);
  memory.set(object.add(0x88).v,definition);memory.set(definition.v,77010);memory.set(definition.add(8).v,type<<3);memory.set(definition.add(213).v,position);
  memory.set(base.add(0x478ae30).v,pool);memory.set(definition.add(0x9c).v,original?64:0);
  memory.set(pool.add(64).v,original.length);memory.set(pool.add(66).v,original);
  memory.set(output.v,pointer(nullOutput?0:0x50000));
  const input=string(mismatch?'wrong':original),args=[pointer(0),output,pointer(0),input];
  const invocation={returnAddress:base.add(ground?0x1032390:0x1234),context:{r14:object}};
  const hook=hooks[hooks.length-1];assert(!hook.detached);hook.callbacks.onEnter.call(invocation,args);hook.callbacks.onLeave.call(invocation);
  assert.equal(definition.readU32(),77010);assert.equal(definition.add(0x9c).readU32(),original?64:0);
  return args[3].readUtf16String();
 }
 return{install,invoke,hooks,events};
}
const h=harness(),state=h.install();assert.equal(h.install(),state);assert.equal(h.hooks.length,1);
assert.equal(h.invoke('DropItemApple',3,24,false),'DropItemApple');assert.equal(state.applied,0);
assert.equal(h.invoke('DropItemPouch'),'DropItemPouch');assert.equal(state.applied,0);
assert.equal(h.invoke('UnrelatedNativeEffect'),'UnrelatedNativeEffect');
assert.equal(h.invoke('DropItemApple'),'DroptItemApple');
assert.equal(h.invoke('DropItemDrop_Weapon_Add',1,2),'DropItemDrop_Weapon_ADD');
assert.equal(h.invoke('DropItemDrop_Weapon_Rose',1,2),'DropItemDrop_Weapon_Common');
const parts={Upbody:8,Lowbody:9,Hand:10,Foot:11},seen=new Set();
for(const[part,slot]of Object.entries(parts))for(const role of ['ADD','Add','Ara','EL']){
 const expected='DropItemDrop_'+part+'_Common';assert.equal(h.invoke('DropItemDrop_'+part+'_'+role,2,slot),expected);seen.add(expected);
}
assert.equal(seen.size,4);
for(const name of ['HQ_Shop_Item_160950.dds','HQ_Shop_INT_Event_AC_Upbody_100000151.dds','HQ_Shop_INT_Event_AC_Upbody_100000152.dds'])assert.equal(h.invoke(name),'DropItemPouch');
assert.equal(h.invoke('',1,2),'DropItemDrop_Weapon_Common');
assert.equal(h.invoke('',2,8),'DropItemDrop_Upbody_Common');
assert.equal(h.invoke('',2,6),'DropItemPouch');assert.equal(h.invoke('',3,24),'DropItemPouch');
assert.equal(state.disabled,false);
const rejected=harness(true);assert.throws(()=>rejected.install(),/native pin/);assert.equal(rejected.hooks.length,0);
for(const failure of ['null','mismatch','position']){
 const t=harness(),s=t.install();
 if(failure==='null')t.invoke('DropItemApple',3,24,true,true);
 if(failure==='mismatch')t.invoke('DropItemApple',3,24,true,false,true);
 if(failure==='position')t.invoke('',2,99);
 assert.equal(s.disabled,true);assert.equal(t.hooks[0].detached,true);
 assert(t.events.some(e=>e.event==='native_ground_models_guard_rejected'));
 assert(!t.events.some(e=>e.event==='native_ground_models_applied'));
}
console.log('PASS native ground adapter: caller scope, model-only changes,22 aliases, category differences, duplicate install and explicit failure disable.');
