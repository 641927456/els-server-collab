'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path'),crypto=require('crypto');
const candidate=path.resolve(__dirname,'../source/tools/my_buff_cleanup.js');
// Arbitrary non-executable bytes model complete method bodies. No game image,
// original native bytes, player state or private-path input is distributed.
const synthetic=n=>Buffer.from(Array.from({length:n},(_,i)=>(19+i*73)&255)).toString('hex');
const profile={cleanup:0x3586460,remove:0x3586c00,vtable:0x4334648,site:0x358653f,resume:0x358658f,
 overwrite_size:18,redirect_padding:'660f1f8400000000000f1f4000',
 bodies:{[0x3586460]:synthetic(325),[0x3586c00]:synthetic(111)}};
const raw=fs.readFileSync(candidate,'utf8');assert.equal(raw.split('__MY_BUFF_CLEANUP_PROFILE__').length,2);
const source=raw.replace('__MY_BUFF_CLEANUP_PROFILE__',JSON.stringify(profile));
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function run(name,options={}){
 const bytes=new Map(),events=[],counts={alloc:0,replace:0,revert:0,flush:0},base=0x140000000,site=base+profile.site;
 let saved=null,continuations=0;
 class Pointer{
  constructor(v){this.v=Number(v instanceof Pointer?v.v:v);}
  add(v){return new Pointer(this.v+Number(v));}toString(){return '0x'+this.v.toString(16);}equals(v){return this.v===v.v;}
  readByteArray(n){return Uint8Array.from({length:n},(_,i)=>bytes.get(this.v+i)||0).buffer;}
  readU8(){return bytes.get(this.v)||0;}readS32(){return Buffer.from(this.readByteArray(4)).readInt32LE();}
  readPointer(){return new Pointer(Number(Buffer.from(this.readByteArray(8)).readBigUInt64LE()));}
 }
 const ptr=v=>new Pointer(v),put=(address,data)=>Array.from(data).forEach((v,i)=>bytes.set(address+i,v));
 for(const [r,h]of Object.entries(profile.bodies))put(base+Number(r),Buffer.from(h,'hex'));
 const pointer=Buffer.alloc(8);pointer.writeBigUInt64LE(BigInt(base+profile.remove));put(base+profile.vtable+0x1e0,pointer);
 const original=Buffer.from(ptr(site).readByteArray(18));
 if(options.bodyMismatch)bytes.set(base+profile.cleanup+100,bytes.get(base+profile.cleanup+100)^1);
 if(options.removeMismatch)bytes.set(base+profile.remove+100,bytes.get(base+profile.remove+100)^1);
 if(options.virtualMismatch)bytes.set(base+profile.vtable+0x1e0,0xff);
 const replacementError=new Error('injected replacement failure');
 const context=vm.createContext({BigInt,Uint8Array,Date,Process:{arch:options.arch||'x64',pointerSize:8,pageSize:4096,getModuleByName:()=>({base:ptr(base)}),getCurrentThreadId:()=>1},
  Memory:{alloc(n,o){counts.alloc++;assert.equal(n,4096);assert.equal(o.near.v,site);if(options.allocFailure)throw Error('allocation failure');return ptr(options.far?site+0x90000000:site+0x100000);},protect(){return !options.protectFailure;}},
  X86Writer:function(p){let offset=0;this.putBytes=b=>{if(options.writerFailure)throw Error('writer failure');put(p.v+offset,b);offset+=b.length;};this.putJmpAddress=t=>{assert.equal(t.v,base+profile.resume);this.putBytes([0xe9,...Buffer.from(Int32Array.of(t.v-(p.v+offset+5)).buffer)]);};this.flush=()=>{};},
  Interceptor:{replaceFast(p,stub){counts.replace++;if(options.replaceFailure)throw replacementError;assert.equal(saved,null);saved=Buffer.from(p.readByteArray(18));const jump=Buffer.alloc(18);jump[0]=options.badRedirect?0xcc:0xe9;jump.writeInt32LE(stub.v-(p.v+5),1);Buffer.from('660f1f8400000000000f1f4000','hex').copy(jump,5);put(p.v,jump);return ptr(p.v+0x200000);},
   flush(){counts.flush++;if(options.flushFailure&&counts.flush===1)throw Error('flush failure');},
   revert(p){counts.revert++;if(saved){put(p.v,saved);saved=null;}}},
  send(event){if(options.reportFailure)throw Error('diagnostic failure');events.push(event);}
 });
 vm.runInContext(source,context);
 const get=expression=>vm.runInContext(expression,context);
 let api=get('installElsMyBuffCleanupOnce()');continuations++;
 const failure=Object.keys(options).some(k=>k!=='reportFailure');
 if(failure){
  assert.equal(api,null);assert.equal(get('!!installElsMyBuffCleanup.failedInstallation'),true);
  assert.equal(saved,null);assert.deepEqual(Buffer.from(ptr(site).readByteArray(18)),original);
  const first={...counts};get('installElsMyBuffCleanupOnce()');continuations++;assert.deepEqual(counts,first);
  assert.equal(events.filter(e=>e.event==='my_buff_cleanup_ready').length,0);
  assert.equal(events.filter(e=>e.event==='my_buff_cleanup_disabled').length,1);
  if(options.bodyMismatch||options.removeMismatch||options.virtualMismatch||options.arch)assert.equal(counts.alloc,0);
 }else{
  assert(api.active());const stub=api.stub,first={...counts};assert.equal(get('installElsMyBuffCleanupOnce()'),api);assert.equal(get('installElsMyBuffCleanup()'),api);assert.deepEqual(counts,first);
  api.stop();assert(!api.active());assert.deepEqual(Buffer.from(ptr(site).readByteArray(18)),original);const stopped={...counts};api.stop();assert.deepEqual(counts,stopped);
  api.start();assert(api.active());assert.equal(api.stub,stub);assert.equal(counts.alloc,1);
  api.stop();assert.equal(saved,null);assert.deepEqual(Buffer.from(ptr(site).readByteArray(18)),original);
  if(options.reportFailure)assert(api.status().last_report_error.includes('diagnostic failure'));
 }
 assert(continuations>=1,'Optional support failure must leave enclosing cache path runnable');
 return {name,ok:true,counts,code_restored:true,continuation_executed:continuations};
}
const cases=[run('install/idempotence/quiescent-stop/re-enable'),run('diagnostic failure preserves committed repair',{reportFailure:true})];
for(const [name,key]of [['wrong cleanup body','bodyMismatch'],['wrong RemoveBuff body','removeMismatch'],['wrong virtual target','virtualMismatch'],['allocation failure','allocFailure'],['out-of-range stub','far'],['writer failure','writerFailure'],['protection failure','protectFailure'],['replacement failure','replaceFailure'],['flush failure rolls back','flushFailure'],['wrong redirect rolls back','badRedirect']])cases.push(run(name,{[key]:true}));
cases.push(run('wrong architecture',{arch:'ia32'}));
const result={ok:true,cases,test_sha256:sha(__filename),candidate_source_sha256:sha(candidate),execution:'Actual candidate JavaScript with synthetic full-body pins and inert Process/Memory/Interceptor APIs.',native_execution:false,limits:'This does not validate the proprietary image, actual native encoding, the full composed parent or concurrent teardown. Private matched-image and real owned-host evidence are recorded separately.'};
console.log(JSON.stringify(result));
