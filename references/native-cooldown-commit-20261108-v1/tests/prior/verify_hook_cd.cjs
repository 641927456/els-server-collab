// Frida API fixtures. Original CD instructions are independently replayed elsewhere.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const out=__dirname,source=fs.readFileSync(path.join(out,'candidate/tools/dungeon_result_stats.js'),'utf8');
const pins=JSON.parse(fs.readFileSync(path.join(out,'hook-pins.json'),'utf8'));
const pvpSource=fs.readFileSync(path.join(out,'candidate/tools/pvp_hp_source.js'),'utf8'),pvpPins=JSON.parse(fs.readFileSync(path.join(out,'pvp-writer-pins.json'),'utf8'));
function fixture(badPin=false){
 const mem=new Map(),bytes=new Map(),events=[],hooks=[],writes=[],replacements=new Map(),sent=[],nativeCallbacks=[];
 class U64{constructor(n){this.n=BigInt(n instanceof U64?n.n:n);}toString(){return String(this.n);}compare(b){const n=BigInt(b.toString());return this.n<n?-1:this.n>n?1:0;}}
 class Ptr{
  constructor(n){this.n=Number(n instanceof Ptr?n.n:n);}add(n){return new Ptr(this.n+Number(n));}
  isNull(){return this.n===0;}equals(p){return this.n===p.n;}toString(){return '0x'+this.n.toString(16);}toInt32(){return this.n|0;}
  readPointer(){return new Ptr(mem.get(this.n)||0);}readU32(){return mem.get(this.n)||0;}readS32(){return this.readU32();}readU16(){return this.readU32();}
  readU64(){return new U64(mem.get(this.n)||0);}readFloat(){return mem.has(this.n)?mem.get(this.n):0;}
  readByteArray(n){return Uint8Array.from(bytes.get(this.n)||Array(n).fill(0)).buffer;}
  writeByteArray(value){bytes.set(this.n,[...value]);}
 }
 const base=0x140000000,game=0x20000000,actor=0x30000000,engine=0x40000000,manager=0x41000000,unit=0x42000000,actorUnit=0x43000000,message=0x50000000;
 for(const[r,h]of Object.entries({...pins,...pvpPins}))bytes.set(base+Number(r),[...Buffer.from(h,'hex')]);
 if(badPin)bytes.set(base+0x682da0,Array(16).fill(0));
 mem.set(game,base+0x41bfd28);mem.set(game+0x2d0,2);mem.set(base+0x4817e70,engine);mem.set(engine+0xc8,manager);
 mem.set(manager+0xa0,unit);mem.set(actor+0x1a3e0,actorUnit);mem.set(unit+0x48,1001);mem.set(actorUnit+0x48,1001);
 let originalReturn=1;
 function enter(rva,args=[],extra={}){
  const selected=hooks.filter(h=>h.rva===rva&&!h.detached),states=selected.map(()=>({context:{},returnAddress:new Ptr(0),...extra}));
  const leave=(value=1)=>selected.forEach((h,i)=>h.callback.onLeave?.call(states[i],new Ptr(value)));
  try{selected.forEach((h,i)=>h.callback.onEnter?.call(states[i],args));}catch(error){error.nativeLeave=leave;throw error;}
  return leave;
 }
 function fire(kind,event=0x202){mem.set(message+0x10,event);mem.set(message+0x34,kind);try{enter(0x682d80,[new Ptr(1),new Ptr(message)])();}finally{sent.push(kind);}}
 function sendReport(){
  const leave=enter(0x1ab7ac0,[new Ptr(game)]);
  if(originalReturn===1){events.push('9E');mem.set(0x65001000,1000);nativeCallbacks[0](new Ptr(0x65000000),new Ptr(0x65001000),new Ptr(base+0xc690a1));const previous=mem.get(message+0x34);fire(0x9e);mem.set(message+0x34,previous);}
  leave(originalReturn);return originalReturn;
 }
 function NativeFunction(address){
  if(address.n===base+0x159670)return()=>new Ptr(game);
  if(address.n===base+0x8571d0)return()=>new Ptr(actor);
  if(address.n===base+0x1ab7ac0)return sendReport;
  if(address.n===base+0x7d8b00)return()=>1000;
  if(address.n===base+0x7d57a0)return()=>2000;
  if(address.n===0x74000000)return()=>1;
  if(address.n===base+0x682d80)return(receiver,message)=>sent.push(message.add(0x34).readU16());
  if([0x3b6dbd0,0x3b6dda0,0x3b6dcc0].includes(address.n-base))return(stream,value)=>{writes.push([address.n-base,value.toString()]);return true;};
  throw Error('Unexpected original call');
 }
 function NativeCallback(callback){nativeCallbacks.push(callback);callback.toString=()=>'0x72000000';return callback;}
 const context=vm.createContext({Process:{pageSize:4096,getCurrentThreadId:()=>7,getModuleByName:n=>{assert.equal(n,'x2_dx11.exe');return{base:new Ptr(base)};}},Memory:{alloc:()=>new Ptr(0x73000000),protect:()=>true},NativeFunction,NativeCallback,
  Interceptor:{attach(address,callback){const h={rva:address.n-base,callback,detached:false,detach(){this.detached=true;}};hooks.push(h);return h;},replaceFast(address,pointer){assert.equal(address.n-base,0xda2f50);assert(!replacements.has(address.n-base));replacements.set(address.n-base,pointer);bytes.set(address.n,Array(16).fill(0xcc));return new Ptr(0x74000000);}},
  send:m=>events.push(m.event),uint64:n=>new U64(n),Uint8Array});
 vm.runInContext(pvpSource.replace('__PVP_HP_PINS__',JSON.stringify(pvpPins))+'\n'+source.replace('__DUNGEON_RESULT_PINS__',JSON.stringify(pins)),context);
 function scope(kind,local=true){const tree=actorUnit+(local?0x7c8:0x1700);return enter(kind==='discrete'?0x8fe730:0x8f4830,[new Ptr(tree),new Ptr(tree+0xc0),new Ptr(0),new Ptr(0)]);}
 function commit(kind,uid,delta){const frame=0x70000000,node=0x71000000;
  mem.set(frame+0x20,uid);mem.set(frame+0x28,delta);mem.set(frame+0x30,node);mem.set(node+0x20,uid);mem.set(node+0x28,100+delta);
  enter(kind==='discrete'?0x18ddeb3:0x8f4c2d,[],{context:{[kind==='discrete'?'rsp':'rbp']:new Ptr(frame)}});
 }
 function reportRows(){writes.length=0;sendReport();assert.deepEqual(writes.slice(0,2),[[0x3b6dbd0,String(0x50564531)],[0x3b6dbd0,String((writes.length-2)/2)]]);
  const rows={};for(let i=2;i<writes.length;i+=2){assert.equal(writes[i][0],0x3b6dda0);assert.equal(writes[i+1][0],0x3b6dcc0);rows[writes[i][1]]=Number(writes[i+1][1]);}return rows;}
 return{context,events,hooks,writes,replacements,sent,fire,sendReport,enter,scope,commit,reportRows,mem,bytes,game,actorUnit,base,setReturn:r=>originalReturn=r};
}
let checks=[],main=true;const thread=()=>main,f=fixture(),c=f.context.installElsDungeonResultStats(thread),count=f.hooks.length;
assert.equal(count,6);assert.equal(f.replacements.size,1);assert.equal(f.context.installElsDungeonResultStats(),c);assert.equal(f.hooks.length,count);
f.fire(0xbb);f.events.push('BB');f.fire(0x471);f.events.push('471');assert.deepEqual(f.events,['dungeon_result_stats_ready','9E','BB','9E','471']);assert.equal(c.reports(),2);
assert.deepEqual(f.sent,[0x9e,0xbb,0x9e,0x471]);
checks.push('One install; original9E precedes terminal requests through the original generic sender; recursive send cannot loop');
main=false;let sends=f.sent.length;assert.throws(()=>f.fire(0xbb),/outside original game thread/);assert.deepEqual(f.sent.slice(sends),[0xbb]);main=true;
f.fire(0xad);f.mem.set(f.game,f.base+0x4183dd0);f.fire(0xbb);assert.equal(c.reports(),2);f.mem.set(f.game,f.base+0x41bfd28);
f.mem.set(f.actorUnit+0x48,2002);assert.throws(()=>f.fire(0xbb),/owner changed/);f.mem.set(f.actorUnit+0x48,1001);
f.setReturn(0);sends=f.sent.length;assert.throws(()=>f.fire(0xbb),/report rejected/);assert.deepEqual(f.sent.slice(sends),[0xbb]);f.setReturn(1);f.fire(0xbb);assert.equal(c.reports(),3);
checks.push('Non-game thread, different mode and changed owner cannot invoke the owned original report');
let leave=f.scope('discrete');f.commit('discrete',1002,3);leave();
leave=f.scope('acceleration');f.commit('acceleration',1002,1.5);f.commit('acceleration',9999,2);leave();
assert.deepEqual(f.reportRows(),{'1002':4.5,'9999':2});
checks.push('PVE1 serializes the original committed discrete and acceleration deltas, sorted by source UID');
const outer=f.scope('acceleration'),remote=f.scope('discrete',false);f.commit('discrete',1002,90);remote();f.commit('acceleration',1002,.5);outer();
assert.deepEqual(f.reportRows(),{'1002':5,'9999':2});
checks.push('Innermost remote tree cannot borrow a local outer scope; resumed local commit counted once');
const survived=f.scope('acceleration');f.mem.set(f.actorUnit+0x48,2002);let ownerError;
try{f.scope('discrete');}catch(error){ownerError=error;}
assert(ownerError);f.mem.set(f.actorUnit+0x48,1001);ownerError.nativeLeave();f.commit('acceleration',1002,.25);survived();
assert.deepEqual(f.reportRows(),{'1002':5.25,'9999':2});
checks.push('An exception during nested ownership resolution unwinds only that invocation, preserving its local parent');
const obsolete=f.scope('discrete');f.mem.set(f.base+0x478cb88,1);f.commit('discrete',1002,99);obsolete();assert.deepEqual(f.reportRows(),{});
checks.push('Changed native Game reference discards a pending old commit and clears previous-run CD values');
const inFlight=f.scope('discrete');c.dispose();inFlight();c.dispose();assert(f.hooks.every(h=>h.detached));assert.equal(f.replacements.size,1);f.fire(0xbb);assert.equal(c.reports(),3);
const c2=f.context.installElsDungeonResultStats(thread);assert.notEqual(c,c2);assert.equal(f.hooks.length,2*count);c2.dispose();
checks.push('Dispose and reload remove all owned hooks and thread scopes');
const bad=fixture(true);assert.throws(()=>bad.context.installElsDungeonResultStats(thread),/identity/);assert.equal(bad.hooks.length,0);
const staged=fixture();staged.context.prepareElsDungeonResultStats();assert.equal(staged.hooks.length,0);staged.bytes.set(staged.base+0x1ab7ac0,Array(16).fill(0xcc));
const stagedController=staged.context.installElsDungeonResultStats(thread);staged.fire(0xbb);assert.equal(stagedController.reports(),1);stagedController.dispose();
checks.push('Original pins verified before existing PvP Interceptors; successful cache install receives only its own thread predicate');
const both=fixture();both.context.prepareElsDungeonResultStats();const pc=both.context.installElsPvpHpSource(),dc=both.context.installElsDungeonResultStats(thread);
both.writes.length=0;both.fire(0xbb);assert.deepEqual(both.writes,[[0x3b6dbd0,String(0x50564531)],[0x3b6dbd0,'0']]);
both.mem.set(both.game,both.base+0x4183dd0);both.writes.length=0;both.sendReport();assert.deepEqual(both.writes,[[0x3b6dbd0,String(0x50565031)],[0x3b6dcc0,'2000']]);
dc.dispose();both.writes.length=0;both.sendReport();assert.equal(both.writes.length,2);pc.dispose();both.writes.length=0;both.sendReport();assert.equal(both.writes.length,0);
checks.push('Shared original serializer appends exactly PVE1 or PVP1 by original mode; independent disposal preserves the remaining consumer');
const standalone=fixture();const firstPvp=standalone.context.installElsPvpHpSource();firstPvp.dispose();const reloadedPvp=standalone.context.installElsPvpHpSource();assert.notEqual(firstPvp,reloadedPvp);reloadedPvp.dispose();
checks.push('Standalone PvP reload reuses the verified shared writer without repinning its installed fast entry as original code');
const result={passed:true,checks,Frida_APIs:'explicit fixtures',game_process:false,natural_GUI:false,natural_battle:false};
fs.writeFileSync(path.join(out,'shared-writer-entry.json'),JSON.stringify({code:Buffer.from(f.bytes.get(0x73000000)).toString('hex'),callback:'0x72000000',target:'0x140da2f50'},null,2)+'\n');
fs.writeFileSync(path.join(out,'hook-verification.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
