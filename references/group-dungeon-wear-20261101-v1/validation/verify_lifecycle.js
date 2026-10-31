'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert');
const W=__dirname,source=fs.readFileSync(path.join(W,'../support/common/tools/group_wear_sync.js'),'utf8'),cacheSource=fs.readFileSync(path.join(W,'../support/common/tools/native_cache_sync.js'),'utf8');
const failure=source.slice(source.indexOf(' function fail(error){'),source.indexOf(' function frame(game){'));
const frame=source.slice(source.indexOf(' function frame(game){'),source.indexOf(' const replacement=new NativeCallback'));
const generation=source.slice(source.indexOf(' function generation('),source.indexOf(' function remember('));
const encoder=source.slice(source.indexOf(' hooks.push(Interceptor.attach(M.base.add(0x680b50)'),source.indexOf(' Interceptor.flush();'));
const getter=cacheSource.match(/failed\(\)\{return disabled;\}/g);assert(getter&&getter.length===1);
const makeCache=new Function('disabled','return {'+getter[0]+'};');
let nextAddress=0x10000n;
class Pointer {
 constructor(size,buffer=null,offset=0,address=null){this.buffer=buffer||new ArrayBuffer(size);this.offset=offset;this.address=address===null?(nextAddress+=0x1000n):address;}
 add(n){return new Pointer(0,this.buffer,this.offset+n,this.address+BigInt(n));}
 readU32(){return new DataView(this.buffer).getUint32(this.offset,true);}
 readU16(){return new DataView(this.buffer).getUint16(this.offset,true);}
 writeU16(n){new DataView(this.buffer).setUint16(this.offset,n,true);}
 writeU8(n){new DataView(this.buffer).setUint8(this.offset,n);}
 writePointer(p){new DataView(this.buffer).setBigUint64(this.offset,p.address,true);}
 readByteArray(n){return this.buffer.slice(this.offset,this.offset+n);}
 writeByteArray(bytes){new Uint8Array(this.buffer,this.offset).set(new Uint8Array(bytes));}
}
const execute=new Function('name','makeCache','Pointer',`
 let disabled=false,advertisedAt=12345,pending=[{key:'game',bytes:new ArrayBuffer(4)}],pendingBytes=4,applied=4,flushing=false,gameKey='game',epoch=null;
 let ownerRequest=name.includes('request')||name==='temporary-not-ready'?{}:null;
 let ownerReport=name.includes('report')||name.startsWith('borrow-')?{key:'game',bytes:new ArrayBuffer(101)}:null;
 const cache=makeCache(name.startsWith('cache-'));cache.peerReady=()=>false;
 const initializedPeers=new Map(),events=[],emit=(event,row)=>events.push({event,...row}),hooks=[],M={base:{add:r=>r}},Interceptor={attach:(r,callbacks)=>callbacks};
 const Memory={alloc:n=>new Pointer(n)};let gameReads=0;
 const currentGame=()=>{gameReads++;return {key:'game',g:{equals:()=>true}};};
 ${failure}
 ${generation}
 ${frame}
 ${encoder}
 if(name.startsWith('group-'))fail(Error('Owned group failure'));
 if(name==='cache-frame-request'||name==='temporary-not-ready')frame(null);
 const readsAfterFrame=gameReads;
 const event=new Pointer(160);new DataView(event.buffer).setUint32(0x10,0x202,true);event.add(0x34).writeU16(0x7d0);
 const oldPayload=Uint8Array.from({length:32},(_,i)=>i+0x80).buffer;event.add(0x36).writeByteArray(oldPayload);
 const context={};hooks[0].onEnter.call(context,[null,event]);const outbound=event.add(0x34).readU16();
 const borrowed=!!context.saved;
 if(name==='borrow-report-retired')fail(Error('Owned failure between encoder callbacks'));
 hooks[0].onLeave.call(context,{toInt32:()=>name==='borrow-encoder-failure'?0:1});
 const restoredKind=event.add(0x34).readU16(),restoredPayload=Array.from(new Uint8Array(event.add(0x36).readByteArray(32)));
 let nextOutbound=null;
 if(name.startsWith('borrow-')){const next={};hooks[0].onEnter.call(next,[null,event]);nextOutbound=event.add(0x34).readU16();hooks[0].onLeave.call(next,{toInt32:()=>1});}
 return {name,disabled,pending:pending.length,pendingBytes,requestPending:ownerRequest!==null,reportPending:ownerReport!==null,outbound,borrowed,restoredKind,restoredPayload,oldPayload:Array.from(new Uint8Array(oldPayload)),nextOutbound,readsAfterFrame,events};
`);
const names=['group-request','group-report','cache-frame-request','cache-encoder-report','temporary-not-ready','borrow-report-success','borrow-report-retired','borrow-encoder-failure'];
const cases=names.map(name=>{
 const r=execute(name,makeCache,Pointer);assert.strictEqual(r.restoredKind,0x7d0);assert.deepStrictEqual(r.restoredPayload,r.oldPayload);
 if(name==='temporary-not-ready'){
  assert(!r.disabled&&r.pending===1&&r.requestPending&&!r.reportPending);assert.strictEqual(r.outbound,0xff20);
 }else if(name==='borrow-report-success'){
  assert(!r.disabled&&r.borrowed&&!r.reportPending);assert.strictEqual(r.outbound,0xff22);assert(r.events.some(x=>x.event==='owner_report_encoded'));
 }else{
  assert(r.disabled&&r.pending===0&&r.pendingBytes===0&&!r.requestPending&&!r.reportPending);
  if(name.startsWith('borrow-')){assert.strictEqual(r.outbound,0xff22);assert.strictEqual(r.nextOutbound,0xff21);assert(!r.events.some(x=>x.event==='owner_report_encoded'));}
  else assert.strictEqual(r.outbound,0xff21);
 }
 if(name==='cache-frame-request')assert.strictEqual(r.readsAfterFrame,0);
 return {case:name,passed:true,borrowed_payload_and_kind_restored:true,permanent_failure_retired:r.disabled,temporary_not_ready_preserved:name==='temporary-not-ready',actual_final_function_bodies:true};
});
const result={ok:true,cases,cache_failed_getter_from_actual_generated_API:true,actual_frame_fail_and_encoder_callbacks:true,pointer_representation:'JavaScript byte-buffer model; no game/native API execution',native_thread_race_claimed:false};
fs.writeFileSync(path.join(W,'review-lifecycle-verification.json'),JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result)+'\n');
