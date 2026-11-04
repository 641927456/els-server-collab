// Runs the exact production adapter with modeled Frida pointers/calls.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),root=__dirname;
const source=fs.readFileSync(path.join(root,'adapter-generated.js'),'utf8');
const pins=JSON.parse(source.match(/pins=(\{[^;]+\});/)[1]);
let checked=0;
function environment(corrupt=false){
 const memory=new Map(),hooks=new Map(),deltas=[],messages=[];let replacements=0,reverts=0,thread=11;
 class Pointer{
  constructor(n){this.n=BigInt(n);}
  add(n){return new Pointer(this.n+BigInt(n));} sub(p){return new Pointer(this.n-p.n);}
  equals(p){return !!p&&this.n===p.n;}isNull(){return this.n===0n;}
  toString(){return '0x'+this.n.toString(16);}toInt32(){return Number(this.n);}
  readPointer(){return new Pointer(memory.get(this.n)||0n);}readS32(){return Number(memory.get(this.n)||0);}
  readU64(){const v=this.readS32();return{toString:()=>String(v)};}
  readByteArray(n){const r=Number(this.n-base.n),h=pins[r];assert(h);return Uint8Array.from(Buffer.from(corrupt?'00'.repeat(n):h,'hex')).buffer;}
 }
 const ptr=n=>new Pointer(n),base=ptr(0x140000000n),actor=ptr(0x200000000n),other=ptr(0x210000000n),game=ptr(0x220000000n),parent=ptr(0x230000000n),def=ptr(0x240000000n),script=ptr(0x250000000n),begin=ptr(0x260000000n);
 const set=(p,v)=>memory.set(p.n,v instanceof Pointer?v.n:v);
 set(actor,base.add(0x41ea620));set(actor.add(0x19e20),script);set(script,8184);
 set(game,base.add(0x41bfd28));set(game.add(0x2d0),2);set(game.add(0x1440),parent);set(parent.add(0x10),1);set(parent,def);set(def.add(0x18),34720);
 set(actor.add(0x3d0),18);set(actor.add(0x3c8),4);set(game.add(0x378),begin);set(game.add(0x380),begin.add(80*8));set(begin.add(32),actor);
 let currentGame=game,lookup=actor,count=0,hp=120835;
 const originals={
  [0x159670]:p=>{assert(p.equals(base.add(0x478cb88)));return currentGame;},
  [0x1aa4a40]:(g,k)=>{assert(g.equals(game));assert([18,63].includes(k));return lookup;},
  [0x7d5560]:(p,k)=>{assert(p.equals(actor));assert.equal(k,0);return count;},
  [0x7d8b00]:p=>{assert(p.equals(actor));return hp;},
  [0x7000000]:(p,d,m)=>{deltas.push([p,d,m]);}
 };
 let replacement;
 const context=vm.createContext({Process:{getModuleByName:name=>{assert.equal(name,'x2_dx11.exe');return{base};},getCurrentThreadId:()=>thread},
  NativeFunction:function(p,ret,args){const r=Number(p.n-base.n);assert(originals[r],r.toString(16));return originals[r];},
  NativeCallback:function(fn,ret,args){assert.equal(ret,'void');assert.deepEqual(Array.from(args),['pointer','float','float']);return fn;},
  Interceptor:{replaceFast(p,f){assert(p.equals(base.add(0x16e3a00)));replacement=f;replacements++;return base.add(0x7000000);},attach(p,h){hooks.set(Number(p.n-base.n),h);return{detach:()=>hooks.delete(Number(p.n-base.n))};},revert(p){assert(p.equals(base.add(0x16e3a00)));reverts++;}},send:v=>messages.push(v),Uint8Array,Map,Array,Number,Error});
 const load=()=>vm.runInContext(source,context);
 const hit=(p=actor,d=-999999,min=0)=>{const h=hooks.get(0x1695250),inv={};h.onEnter.call(inv,[p]);replacement(p,d,min);h.onLeave.call(inv);return deltas.at(-1);};
 return{load,context,set,actor,other,base,game,parent,def,script,begin,hit,hooks,deltas,messages,
  get replacement(){return replacement;},get replacements(){return replacements;},get reverts(){return reverts;},set count(v){count=v;},set hp(v){hp=v;},set lookup(v){lookup=v;},set currentGame(v){currentGame=v;},set thread(v){thread=v;}};
}
function test(name,f){f();checked++;}
test('identity mismatch installs no hooks',()=>{const e=environment(true);assert.throws(e.load,/native identity/);assert.equal(e.replacements,0);assert.equal(e.hooks.size,0);});
test('only negative scoped original hits raise minimum',()=>{
 const e=environment();e.load();assert.equal(e.hit()[2],1);assert.equal(e.hit(e.actor,-5,2)[2],2);assert.equal(e.hit(e.actor,5,0)[2],0);
 e.replacement(e.actor,-9,0);assert.equal(e.deltas.at(-1)[2],0);assert.equal(e.hit(e.other)[2],0);
 e.count=49;assert.equal(e.hit()[2],1);e.count=50;assert.equal(e.hit()[2],0);e.count=51;assert.equal(e.hit()[2],0);e.count=-1;assert.equal(e.hit()[2],0);
 e.count=0;e.hp=0;assert.equal(e.hit()[2],0);
});
for(const [name,alter]of[
 ['actor vtable',e=>e.set(e.actor,e.base)],['template',e=>e.set(e.script,8188)],['game vtable',e=>e.set(e.game,e.base)],
 ['game mode',e=>e.set(e.game.add(0x2d0),1)],['stage',e=>e.set(e.parent.add(0x10),2)],['map',e=>e.set(e.def.add(0x18),34710)],
 ['UID',e=>e.set(e.actor.add(0x3d0),19)],['slot negative',e=>e.set(e.actor.add(0x3c8),-1)],['slot end',e=>e.set(e.actor.add(0x3c8),80)],
 ['vector size',e=>e.set(e.game.add(0x380),e.begin.add(79*8))],['slot ownership',e=>e.set(e.begin.add(32),e.other)],['UID lookup',e=>{e.lookup=e.other;}],
 ['missing script',e=>e.set(e.actor.add(0x19e20),0)],['missing parent',e=>e.set(e.game.add(0x1440),0)]
])test('reject '+name,()=>{const e=environment();e.load();alter(e);assert.equal(e.hit()[2],0);});
test('second verified source is supported',()=>{const e=environment();e.load();e.set(e.actor.add(0x3d0),63);assert.equal(e.hit()[2],1);});
test('nested other actor masks scope and unwind restores it',()=>{
 const e=environment();e.load();const h=e.hooks.get(0x1695250),a={},b={};h.onEnter.call(a,[e.actor]);h.onEnter.call(b,[e.other]);
 e.replacement(e.actor,-100,0);assert.equal(e.deltas.at(-1)[2],0);h.onLeave.call(b);e.replacement(e.actor,-100,0);assert.equal(e.deltas.at(-1)[2],1);
 e.thread=12;e.replacement(e.actor,-100,0);assert.equal(e.deltas.at(-1)[2],0);e.thread=11;h.onLeave.call(a);
 e.replacement(e.actor,-100,0);assert.equal(e.deltas.at(-1)[2],0);
});
test('singleton and detach keep original arguments',()=>{
 const e=environment();e.load();vm.runInContext('installElsHitCountObstacles()',e.context);assert.equal(e.replacements,1);assert.equal(e.messages.length,1);
 vm.runInContext('elsHitCountObstacles.stop();elsHitCountObstacles.stop()',e.context);assert.equal(e.reverts,1);assert.equal(e.hooks.size,0);
 e.replacement(e.actor,-100,0);assert.equal(e.deltas.at(-1)[2],0);
});
fs.writeFileSync(path.join(root,'adapter-tests.json'),JSON.stringify({ok:true,tests:checked,kind:'production JS modeled Frida contract; original HP arithmetic verified separately'},null,2)+'\n');
process.stdout.write(JSON.stringify({ok:true,tests:checked})+'\n');
