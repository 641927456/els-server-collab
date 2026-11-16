// Diagnostic callbacks only. All native fields are borrowed within the call.
(function(){
'use strict';
const profile=__CLIENT_DELIVERY_PROFILE__,image=Process.getModuleByName('x2_dx11.exe');
const tracked=new Set(profile.observed_kinds);
const receivers=new Map(),dispatches=new Map(),pending=new Map(),hooks=[];
let sequence=0,identity=0,attempts=0,omitted=0,active=true,windowAt=Date.now(),emitted=0;
function emit(phase,fields){
 const now=Date.now();if(now-windowAt>=1000){windowAt=now;emitted=0;}
 if(emitted++>=96){omitted++;return;}
 send({event:'client_delivery_trace',phase,sequence:++sequence,timestamp:now,dropped:omitted,...fields});
}
function readable(p,n){if(p.isNull()||n<0)return false;const r=Process.findRangeByAddress(p);return !!r&&r.protection.includes('r')&&p.add(n).compare(r.base.add(r.size))<=0;}
function bytes(p,n){if(n===0)return new Uint8Array(0);if(!readable(p,n))throw Error('unreadable_borrowed_range');return new Uint8Array(p.readByteArray(n));}
function hex(data){return Array.from(data,b=>b.toString(16).padStart(2,'0')).join('');}
function sha256(data){
 const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],n=(data.length+9+63)&~63,b=new Uint8Array(n),v=new DataView(b.buffer),w=new Uint32Array(64);
 b.set(data);b[data.length]=128;v.setUint32(n-4,data.length*8,false);
 const r=(x,n)=>(x>>>n)|(x<<(32-n));
 for(let offset=0;offset<n;offset+=64){
  for(let i=0;i<16;i++)w[i]=v.getUint32(offset+i*4,false);
  for(let i=16;i<64;i++){const x=w[i-15],y=w[i-2];w[i]=(w[i-16]+(r(x,7)^r(x,18)^(x>>>3))+w[i-7]+(r(y,17)^r(y,19)^(y>>>10)))>>>0;}
  let[a,c,d,e,f,g,j,l]=h;
  for(let i=0;i<64;i++){const t=(l+(r(f,6)^r(f,11)^r(f,25))+((f&g)^(~f&j))+k[i]+w[i])>>>0,u=((r(a,2)^r(a,13)^r(a,22))+((a&c)^(a&d)^(c&d)))>>>0;l=j;j=g;g=f;f=(e+t)>>>0;e=d;d=c;c=a;a=(t+u)>>>0;}
  for(const[i,x]of[a,c,d,e,f,g,j,l].entries())h[i]=(h[i]+x)>>>0;
 }
 return h.map(x=>x.toString(16).padStart(8,'0')).join('');
}
function buffer(p){
 if(!readable(p,40))throw Error('buffer_header');const begin=p.add(8).readPointer(),end=p.add(16).readPointer(),cap=p.add(24).readPointer();
 if(end.compare(begin)<0||cap.compare(end)<0||end.compare(begin.add(65536))>0)throw Error('buffer_order');
 const n=end.sub(begin).toInt32(),cursor=p.add(32).readU32();
 if(n<0||n>65536||cursor>n)throw Error('buffer_bound');return{begin,length:n,cursor};
}
function key(v){return[v.event_id,v.kind,v.uid,v.target_uid,v.payload_bytes,v.payload_sha256].join(':');}
function eventView(p){
 if(!readable(p,0x66))throw Error('event_header');const event_id=p.add(16).readU32(),kind=p.add(0x34).readU16();
 if(event_id!==0x201||!tracked.has(kind))return null;
 const b=buffer(p.add(0x36));
 const value={event_id,kind,uid:p.add(0x24).readU64().toString(),target_uid:p.add(0x2c).readU64().toString(),
   payload_bytes:b.length,payload_sha256:sha256(bytes(b.begin,b.length)),payload_mode:p.add(0x36).readU8()};
 const offset=profile.result_offsets[kind];if(offset!==undefined&&b.length>=4){const raw=bytes(b.begin.add(offset<0?b.length+offset:offset),4);value.response_result=new DataView(raw.buffer).getInt32(0,false);}
 return value;
}
function frameView(origin){origin.hash||=sha256(bytes(origin.pointer,origin.length));return{frame_sha256:origin.hash,frame_bytes:origin.length,receive_scope:true};}
function push(map,thread,item){let rows=map.get(thread);if(!rows){if(map.size>=16)throw Error('thread_bound');map.set(thread,rows=[]);}if(rows.length>=8)throw Error('nesting_bound');rows.push(item);}
function pop(map,thread,item){const rows=map.get(thread);if(!rows||rows[rows.length-1]!==item){omitted++;return;}rows.pop();if(!rows.length)map.delete(thread);}
function current(map,thread){const rows=map.get(thread);return rows&&rows[rows.length-1];}
function prune(){const now=Date.now();for(const[k,rows]of pending){const live=rows.filter(r=>now-r.created<10000);omitted+=rows.length-live.length;if(live.length)pending.set(k,live);else pending.delete(k);}while(pending.size>128){pending.delete(pending.keys().next().value);omitted++;}}
function queue(v){prune();const k=key(v),rows=pending.get(k)||[];if(rows.length>=4){rows.shift();omitted++;}rows.push(v);pending.set(k,rows);}
function take(v){prune();const k=key(v),rows=pending.get(k)||[];pending.delete(k);if(rows.length!==1){if(rows.length)omitted+=rows.length;return null;}return rows[0];}
function state(s){
 if(!readable(s.add(0x908),8))return null;
 const index=s.add(0x908).readS32(),generation=s.add(0x90c).readU32();if(index<0||!generation)return null;
 const table=image.base.add(profile.handle_table_global).readPointer();if(!readable(table,16))return null;
 const begin=table.readPointer(),end=table.add(8).readPointer();if(end.compare(begin.add((index+1)*32))<0)return null;
 const cell=begin.add(index*32);if(!readable(cell,24)||!(cell.add(12).readU8()&1)||cell.add(16).readU32()!==generation)return null;
 const g=cell.readPointer();if(!readable(g,0x1450)||!g.readPointer().equals(image.base.add(profile.dungeon_vtable)))return null;
 const parent=g.add(0x1440).readPointer();if(!readable(parent,24))return null;const part=parent.add(8).readPointer();
 return{handle_index:index,handle_generation:generation,stage:parent.add(16).readS32(),
   part:readable(part,20)?part.add(16).readS32():null,suspended:g.add(0x620).readU8()};
}
function stateSnapshot(s){try{return state(s);}catch(error){return null;}}
function guarded(fn){return function(...args){if(!active)return;try{return fn.apply(this,args);}catch(error){emit('observer_error',{reason:'observation_read_failed',thread:Process.getCurrentThreadId()});}};}
__CLIENT_EFFECTS_SOURCE__
__CLIENT_LIFECYCLE_SOURCE__
function install(){
 for(const site of [...profile.sites,...profile.effect_sites,...profile.reader_sites,...profile.lifecycle_sites]){if(sha256(bytes(image.base.add(site.rva),site.size))!==site.body_sha256)throw Error('native_body_mismatch:'+site.role);}
 hooks.push(Interceptor.attach(image.base.add(0x6817e0),{
  onEnter:guarded(function(a){const n=a[2].toUInt32();if(!a[3].isNull()||n<14||n>65536)return;this.receive={pointer:a[1],length:n,hash:null,parsers:0};push(receivers,this.threadId,this.receive);}),
  onLeave:guarded(function(){if(this.receive){try{if(!this.receive.parsers)emit('frame_without_event',{...frameView(this.receive),thread:this.threadId});}finally{pop(receivers,this.threadId,this.receive);}}})}));
 hooks.push(Interceptor.attach(image.base.add(0x680ca0),{
  onEnter:guarded(function(a){this.output=a[1];this.origin=current(receivers,this.threadId);}),
  onLeave:guarded(function(r){if(this.origin)this.origin.parsers++;
   if((r.toUInt32()&255)!==1){if(this.origin)emit('event_decode_failed',{...frameView(this.origin),thread:this.threadId});return;}
   const v=eventView(this.output);if(!v)return;
   const parsed=buffer(this.output.add(0x36));try{v.targets=effectTargets(v,bytes(parsed.begin,parsed.length));}catch(error){v.targets={};omitted++;}
   v.trace_id=++identity;v.created=Date.now();v.thread=this.threadId;
   if(this.origin)Object.assign(v,frameView(this.origin));
   v.receive_scope=!!this.origin;queue(v);emit('event_decoded',v);})}));
 for(const site of profile.sites.filter(s=>s.role.endsWith('dispatch'))){hooks.push(Interceptor.attach(image.base.add(site.rva),{
  onEnter:guarded(function(a){if(a[2].toUInt32()!==0x201||!tracked.has(a[3].toUInt32()))return;
   const b=buffer(a[4]),v={event_id:0x201,kind:a[3].toUInt32(),payload_bytes:b.length,payload_sha256:sha256(bytes(b.begin,b.length))};
   const parent=current(dispatches,this.threadId);let matched=null;
   if(parent&&parent.kind===v.kind&&parent.payload_sha256===v.payload_sha256){this.nested=true;return;}
   else{prune();const candidates=[];for(const rows of pending.values())for(const row of rows)if(row.kind===v.kind&&row.payload_sha256===v.payload_sha256&&row.payload_bytes===v.payload_bytes)candidates.push(row);
    if(candidates.length===1&&candidates[0].receive_scope)matched=take(candidates[0]);}
   if(!matched){emit('dispatch_unmatched',{kind:v.kind,site_rva:site.rva,thread:this.threadId});return;}
   this.dispatch={...matched,thread:this.threadId,site_rva:site.rva,role:site.role,before:stateSnapshot(a[0]),owner:a[0],buffer:a[4],start:b.cursor};
   push(dispatches,this.threadId,this.dispatch);emit('dispatch_enter',{trace_id:matched.trace_id,kind:v.kind,site_rva:site.rva,role:site.role,thread:this.threadId,before:this.dispatch.before});beginEffects(this.dispatch);}),
  onLeave:guarded(function(r){const row=this.dispatch;if(!row)return;try{const after=stateSnapshot(row.owner);let cursor=null;try{cursor=buffer(row.buffer).cursor;}catch(error){}
   emit('dispatch_return',{trace_id:row.trace_id,kind:row.kind,site_rva:row.site_rva,role:row.role,thread:this.threadId,result:r.toUInt32()&255,
    cursor_before:row.start,cursor_after:cursor,payload_bytes:row.payload_bytes,before:row.before,after});finishEffects(row);}finally{pop(dispatches,this.threadId,row);}})}));}
 installEffects();installLifecycles();
 emit('ready',{profile_sha256:__PROFILE_SHA__,client_sha256:profile.client_sha256,read_only:true,hooks:hooks.length});
}
const timer=setInterval(()=>{if(++attempts>1200){clearInterval(timer);emit('disabled',{reason:'native_prefix_timeout'});return;}
 try{if(![...profile.sites,...profile.effect_sites,...profile.reader_sites,...profile.lifecycle_sites].every(s=>hex(bytes(image.base.add(s.rva),24))===s.prefix))return;
  clearInterval(timer);install();
 }catch(error){clearInterval(timer);for(const hook of hooks)hook.detach();active=false;send({event:'client_delivery_trace',phase:'disabled',reason:String(error).includes('native_body_mismatch')?'native_body_mismatch':'observer_install_failed',sequence:++sequence,timestamp:Date.now(),dropped:omitted});}
},25);
})();
