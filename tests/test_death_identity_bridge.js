// Execute the actual bridge callback against the independently captured roster.
// In particular, UID8 occupies slot9 and sentry UID16 occupies slot8.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('tools/trace_dx11_login.js','utf8');
const begin=source.indexOf('   if(gateIdentityTest)Interceptor.attach');
const end=source.indexOf('   // Per-key diagnostic',begin);
assert(begin>=0&&end>begin);
const roster=JSON.parse(fs.readFileSync('analysis/skills-clear-20261015/blocked-roster.json')).rows;
let callback,memory,events,hp,lookup;
class Pointer {
 constructor(n){this.n=Number(n);}
 add(n){return new Pointer(this.n+n);} sub(p){return new Pointer(this.n-p.n);}
 equals(p){return this.n===p.n;} isNull(){return this.n===0;}
 toInt32(){return this.n|0;} toString(){return '0x'+this.n.toString(16);}
 readS32(){assert(memory.has(this.n));return memory.get(this.n);}
 readU64(){const n=this.readS32();return {toNumber:()=>n};}
 readPointer(){return new Pointer(this.readS32());}
 writeS32(n){memory.set(this.n,n);}
}
const g=new Pointer(0x100000),base=new Pointer(0x140000000),dto=new Pointer(0x200000),vector=0x300000;
const context={gateIdentityTest:true,populationTest:true,game:{base},dungeonGame:g,
 Interceptor:{attach:(_p,c)=>{callback=c.onEnter;}},
 nativeCall:r=>r===0x1aa4a40?(_g,id)=>new Pointer(lookup.get(id)||0):()=>hp,
 note:e=>events.push(e)};
vm.runInNewContext(source.slice(begin,end),context);
function setup(row){
 memory=new Map();events=[];hp=0;lookup=new Map(roster.map(r=>[r.uid,Number(r.actor)]));
 memory.set(g.n,base.n+0x41bfd28);memory.set(g.n+0x2d0,2);
 memory.set(g.n+0x1440,0x400000);memory.set(0x400010,1);
 memory.set(g.n+0x378,vector);memory.set(g.n+0x380,vector+80*8);
 for(const r of roster){const a=Number(r.actor);memory.set(vector+r.slot*8,a);memory.set(a+0x3c8,r.slot);memory.set(a+0x3d0,r.uid);memory.set(a+0x19e20,a+0x30000);memory.set(a+0x30000,r.template);}
 memory.set(dto.n,0);return new Pointer(Number(row.actor));
}
for(const uid of [8,9,10,16,17,18]){
 const row=roster.find(r=>r.uid===uid),actor=setup(row);
 callback([actor,dto]);assert.equal(dto.readS32(),uid);assert.equal(events.length,1);
 assert.equal(events[0].instance_index,row.slot);
 for(const failure of ['lookup','slot','hp','mode','bounds','nonzero']){
  const a=setup(row);
  if(failure==='lookup')lookup.set(uid,0);
  if(failure==='slot')memory.set(vector+row.slot*8,0);
  if(failure==='hp')hp=1;
  if(failure==='mode')memory.set(g.n+0x2d0,1);
  if(failure==='bounds')memory.set(g.n+0x380,vector+79*8);
  if(failure==='nonzero')memory.set(dto.n,99);
  const before=dto.readS32();callback([a,dto]);assert.equal(dto.readS32(),before);assert.equal(events.length,0);
 }
}
console.log('PASS: actual bridge, captured divergent slots/UIDs, independent lookup/membership and negative controls.');
