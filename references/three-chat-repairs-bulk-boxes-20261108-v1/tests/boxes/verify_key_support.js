// Execute the exact support script in an owned Node VM / private pointer graph.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const out=__dirname,spec=JSON.parse(fs.readFileSync(path.join(out,'source/tools/owned_box_key_aliases.json')));
const code=fs.readFileSync(path.join(out,'source/tools/owned_box_key_aliases.js'),'utf8').replace('__OWNED_BOX_KEY_SPEC__',JSON.stringify(spec));
const base=0x140000000n,heap=0x200000000n,mem=new Map();let next=heap+0x1000n;
class P {
 constructor(x){this.x=BigInt(x instanceof P?x.x:x);}
 add(n){return new P(this.x+BigInt(n));}sub(p){return new P(this.x-p.x);}equals(p){return this.x===p.x;}compare(p){return this.x<p.x?-1:this.x>p.x?1:0;}isNull(){return this.x===0n;}
 toString(){return '0x'+this.x.toString(16);}toInt32(){return Number(BigInt.asIntN(32,this.x));}toUInt32(){return Number(BigInt.asUintN(32,this.x));}
 readByteArray(n){return Uint8Array.from(Array.from({length:n},(_,i)=>mem.get(this.x+BigInt(i))||0)).buffer;}
 writeByteArray(bytes){Buffer.from(bytes).forEach((v,i)=>mem.set(this.x+BigInt(i),v));}
 readPointer(){return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE());}writePointer(v){const b=Buffer.alloc(8);b.writeBigUInt64LE(new P(v).x);this.writeByteArray(b);}
 readS32(){return Buffer.from(this.readByteArray(4)).readInt32LE();}readU8(){return mem.get(this.x)||0;}writeS32(v){const b=Buffer.alloc(4);b.writeInt32LE(v);this.writeByteArray(b);}writeU8(v){mem.set(this.x,v);}
}
const ptr=x=>new P(x),allocate=n=>{let p=ptr(next);next+=BigInt(n+16);return p;};
let hooks=[],events=[],timers=[];
const context={Process:{getModuleByName:()=>({base:ptr(base)}),findRangeByAddress:p=>({base:ptr(heap),size:Number(next-heap)+4096,protection:'rw-'})},Interceptor:{attach:(p,callbacks)=>{let h={p,callbacks,active:true,detach(){this.active=false;}};hooks.push(h);return h;}},ptr,send:v=>events.push(v),setInterval:f=>{timers.push(f);return f;},clearInterval:f=>{timers=timers.filter(g=>g!==f);},Uint8Array,Map,Set,Number,Error};vm.createContext(context);
for(const [rva,prefix]of Object.entries(spec.entry_prefixes))ptr(base+BigInt(rva)).writeByteArray(Buffer.from(prefix,'hex'));
function graph(){
 let world=allocate(0x600),manager=allocate(0xa00),head=allocate(0x40);ptr(base+0x4817e70n).writePointer(world);world.add(0x58).writePointer(manager);manager.add(0xb8).writePointer(head);head.add(0x19).writeU8(1);
 const data=[];
 for(const r of spec.rules)for(const [old,replacement]of Object.entries(r.aliases))data.push({template:r.template,old:Number(old),replacement});
 data.push({template:136186,old:0,replacement:0},{template:108902,old:69423,replacement:69423});data.sort((a,b)=>a.template-b.template);
 const nodes=data.map(()=>allocate(0x40));head.add(8).writePointer(nodes[0]);head.writePointer(nodes[0]);head.add(16).writePointer(nodes.at(-1));
 data.forEach((r,i)=>{let n=nodes[i],value=allocate(64);n.writePointer(head);n.add(8).writePointer(i?nodes[i-1]:head);n.add(16).writePointer(nodes[i+1]||head);n.add(0x20).writeS32(r.template);n.add(0x28).writePointer(value);value.writeS32(r.template);value.add(4).writeS32(r.old);value.add(8).writeS32(1);value.add(12).writeS32(-1);r.value=value;});
 return{world,manager,head,data};
}
function trigger(g,entry=0x6ac800){for(const r of spec.rules){const args=entry===0x6ac800?[g.manager,ptr(0),ptr(r.template)]:[ptr(0),(()=>{let item=allocate(24);item.add(8).writeS32(r.template);return item;})()];for(const h of hooks)if(h.active&&h.p.equals(ptr(base+BigInt(entry))))h.callbacks.onEnter.call({},args);}}
let g=graph();vm.runInContext(code,context);assert.equal(hooks.length,2);trigger(g);for(const r of g.data)assert.equal(r.value.add(4).readS32(),r.replacement);
const rows=g.data.map(({template,old,replacement,value})=>({template,old,replacement,actual:value.add(4).readS32(),required:value.add(8).readS32(),give:value.add(12).readS32()}));
vm.runInContext(code,context);assert.equal(hooks.length,2);trigger(g,0x2231a40);for(const r of g.data)assert.equal(r.value.add(4).readS32(),r.replacement);
// A fresh manager/head is resolved without dereferencing the old generation.
let second=graph();trigger(second,0x2231a40);for(const r of second.data)assert.equal(r.value.add(4).readS32(),r.replacement);
context.elsOwnedBoxKeyAliasesV1.dispose();for(const r of second.data)assert.equal(r.value.add(4).readS32(),r.old);assert(hooks.every(h=>!h.active));
// A foreign manager does not mutate the graph or current source map.
vm.runInContext(code,context);let foreign=allocate(0xa00),h=hooks.findLast(h=>h.active&&h.p.equals(ptr(base+0x6ac800n)));h.callbacks.onEnter([foreign,ptr(0),ptr(108902)]);assert.equal(second.data.find(r=>r.template===108902).value.add(4).readS32(),235140);context.elsOwnedBoxKeyAliasesV1.dispose();
// Mismatched native entry bytes cannot install a hook.
ptr(base+0x6ac800n).writeU8(0);let before=hooks.length;vm.runInContext(code,context);assert.equal(hooks.length,before);context.elsOwnedBoxKeyAliasesV1.dispose();assert.equal(timers.length,0);
assert(!events.some(e=>e.status==='rejected'));
const report={ok:true,exact_support_script_executed:true,own_node_process:true,game_process_access:false,rows,repeated_load:true,current_generation:true,unrelated_source_preserved:true,dispose_restored:true,prefix_mismatch_rejected:true,events};fs.writeFileSync(path.join(out,'client-key-support-node.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({ok:true,aliases:rows.filter(r=>r.old!==r.replacement).length,checks:7}));
