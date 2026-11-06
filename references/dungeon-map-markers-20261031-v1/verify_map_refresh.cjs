// Own Node process. The original refresh stub consumes current native state;
// no game attachment, renderer or natural lifecycle acceptance is implied.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=__dirname,code=fs.readFileSync(process.argv[2]||path.join(root,'map-refresh-composed.js'),'utf8');
const pins=JSON.parse(code.match(/pins=(\{[^;]+\});/)[1]),base=0x140000000;
function environment(){
 const memory=new Map(),hooks=new Map(),calls=[],events=[];let cursor=0x600000000,valid=true;
 const bytes=(a,n)=>Buffer.from(Array.from({length:n},(_,i)=>memory.get(a+i)||0));
 class Pointer{
  constructor(a){this.address=Number(a);} add(n){return new Pointer(this.address+Number(n));}
  equals(p){return this.address===p.address;} isNull(){return this.address===0;} toInt32(){return this.address|0;}
  readByteArray(n){return bytes(this.address,n);} writeByteArray(v){Array.from(v).forEach((b,i)=>memory.set(this.address+i,b));return this;}
  readPointer(){return new Pointer(Number(bytes(this.address,8).readBigUInt64LE()));}
  writePointer(v){const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(v.address));return this.writeByteArray(b);}
  readS32(){return bytes(this.address,4).readInt32LE();} readU32(){return bytes(this.address,4).readUInt32LE();}
  writeS32(v){const b=Buffer.alloc(4);b.writeInt32LE(v);return this.writeByteArray(b);}
 }
 const ptr=n=>new Pointer(n),alloc=n=>{const p=ptr(cursor);cursor+=n+32;return p;};
 for(const [r,h]of Object.entries(pins))ptr(base+Number(r)).writeByteArray(Buffer.from(h,'hex'));
 const game=alloc(0x1450),engine=alloc(0x170),scene=alloc(0x800),wrapper=alloc(0x30),manager=alloc(0x60),definition=alloc(0x30),part=alloc(0x20),ui=alloc(0xb0),roster=alloc(0x100),party=alloc(0x100),member=alloc(0x29d0),job=alloc(4);
 ptr(base+0x4817e80).writePointer(engine);engine.add(0x168).writePointer(scene);scene.add(0x7e8).writePointer(wrapper);
 game.add(0x1440).writePointer(manager);wrapper.add(0x20).writePointer(manager);manager.writePointer(definition);manager.add(8).writePointer(part);manager.add(0x10).writeS32(1);part.add(0x10).writeS32(0);definition.add(0x18).writeS32(35300);
 ptr(base+0x4817e70).writePointer(roster);roster.add(0xc8).writePointer(party);party.add(0xa0).writePointer(member);member.add(0x48).writeS32(1001);member.add(0x29c0).writePointer(job);job.writeS32(5);
 const originalRefresh=w=>{assert.ok(w.equals(wrapper));calls.push({stage:manager.add(0x10).readS32(),part:manager.add(8).readPointer().add(0x10).readS32()});};
 const context={Uint8Array,Process:{getModuleByName:()=>({base:ptr(base)})},send:e=>events.push(e),
  Interceptor:{attach(p,cb){hooks.set(p.address,cb);return{detach(){hooks.delete(p.address);}};}},
  NativeFunction:function(p){if(p.address===base+0x4ab640)return()=>valid;if(p.address===base+0x4ab6d0)return()=>ui;if(p.address===base+0x1070c20)return originalRefresh;throw Error('Unexpected native call');}};
 vm.createContext(context);vm.runInContext(code,context);
 const install=()=>vm.runInContext('installElsDungeonMapMarkers()',context);
 function select(requested=1,change=()=>{},succeed=true){
  const h=hooks.get(base+0x1040980),scope={};if(h)h.onEnter.call(scope,[game,ptr(requested)]);
  if(succeed){const p=alloc(0x20);p.add(0x10).writeS32(requested);manager.add(8).writePointer(p);}
  change();if(h)h.onLeave.call(scope);
 }
 return{install,select,calls,events,hooks,originalRefresh,ptr,alloc,bytes,game,engine,scene,wrapper,manager,definition,part,ui,roster,party,member,job,setValid:v=>valid=v};
}
const results=[];
{const e=environment();e.originalRefresh(e.wrapper);e.select();assert.equal(e.calls.at(-1).part,0);results.push('baseline reproduces one-room lag');}
{const e=environment(),h=e.install();assert.equal(e.install(),h);assert.equal(e.hooks.size,1);e.originalRefresh(e.wrapper);e.select();assert.equal(e.calls.at(-1).part,1);e.select(2);assert.equal(e.calls.at(-1).part,2);assert.equal(e.calls.length,3);h.stop('end');assert.equal(e.hooks.size,0);e.select(3);assert.equal(e.calls.length,3);results.push('native refresh reads new part, consecutive rooms, one installation, stop');}
for(const [name,change]of [
 ['scene',e=>e.engine.add(0x168).writePointer(e.alloc(0x800))],
 ['wrapper',e=>e.scene.add(0x7e8).writePointer(e.alloc(0x30))],
 ['manager',e=>e.game.add(0x1440).writePointer(e.alloc(0x60))],
 ['definition',e=>e.manager.writePointer(e.alloc(0x30))],
 ['map',e=>e.definition.add(0x18).writeS32(34320)],
 ['stage',e=>e.manager.add(0x10).writeS32(2)],
 ['member',e=>e.party.add(0xa0).writePointer(e.alloc(0x29d0))],
 ['uid',e=>e.member.add(0x48).writeS32(1002)],
 ['unit family',e=>e.job.writeS32(1)],
 ['weak UI invalidated',e=>e.setValid(false)],
 ['selection differs',e=>e.manager.add(8).readPointer().add(0x10).writeS32(2)],
]){const e=environment();e.install();e.select(1,()=>change(e));assert.equal(e.calls.length,0);results.push(name+' prevents stale refresh');}
{const e=environment();e.install();e.select(1,()=>{},false);assert.equal(e.calls.length,0);results.push('rejected selection untouched');}
{const e=environment();e.install();e.select(1,()=>e.part.add(0x10).writeS32(1),false);assert.equal(e.calls.at(-1).part,1);e.select(1,()=>{},false);assert.equal(e.calls.at(-1).part,1);results.push('native allocator may reuse part address; same-part refresh is valid');}
{const e=environment();e.install();e.setValid(false);e.select();assert.equal(e.calls.length,0);results.push('initialization without UI untouched');}
{const e=environment();e.install();e.select(-1);assert.equal(e.calls.length,0);results.push('negative request untouched');}
{const e=environment();e.ptr(base+0x1040980).writeByteArray([0]);assert.throws(()=>e.install(),/native identity/);assert.equal(e.hooks.size,0);results.push('instruction mismatch prevents installation');}
const result={ok:true,cases:results.length,results,scope:'Callback model only; native natural room transitions and signed delivery pending.'};
console.log(JSON.stringify(result));
