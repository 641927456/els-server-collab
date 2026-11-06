const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const H=__dirname, base=0x140000000, app=0x1000, manager=0x2000, begin=0x100000;
function replay(file,defs,allowed,requests,options={}){
 let reads=0,writes=0;const changed=[],events=[],callbacks=new Map(),n=defs.length,bytes=16+n*236,rows=begin+16+n*4;
 const caps=new Map(defs.map((r,i)=>[rows+i*232+16,r[1]]));
 const idAt=p=>defs[(p-(begin+16))/4]?.[0];
 class P{
  constructor(v){this.v=Number(v);} add(v){return new P(this.v+v);} sub(v){return new P(this.v-(v instanceof P?v.v:v));}
  isNull(){return this.v===0;} equals(p){return this.v===p.v;} compare(p){return Math.sign(this.v-p.v);} toString(){return this.v<0?String(this.v):'0x'+this.v.toString(16);} toUInt32(){return this.v>>>0;}
  readPointer(){reads++;if(this.v===base+0x4817e70)return new P(app);if(this.v===app+0x58)return new P(options.foreign?manager+1:manager);if(this.v===manager+0x30)return new P(begin);if(this.v===manager+0x38)return new P(begin+bytes);throw Error('Unexpected pointer read '+this);}
  readU32(){reads++;if(this.v===begin+8)return options.badCount?250001:n;if(this.v>=begin+16&&this.v<rows)return idAt(this.v);if(this.v>=rows&&(this.v-rows)%232===0)return defs[(this.v-rows)/232]?.[0];throw Error('Unexpected U32 read '+this);}
  readS32(){reads++;assert(caps.has(this.v));return caps.get(this.v);}
  writeS32(v){writes++;assert(caps.has(this.v));changed.push(this.v);caps.set(this.v,v);}
  readByteArray(n){reads++;assert.equal(this.v,base+0x6d56c0);return new Uint8Array(n).buffer;}
 }
 const code=fs.readFileSync(file,'utf8').replace('__STACK_IDS__',JSON.stringify(allowed)).replace('__LOOKUP_PREFIX__',JSON.stringify('00'.repeat(16)));
 vm.runInNewContext(code,{Set,Map,Number,Date,Error,Array,Uint8Array,Process:{getModuleByName:()=>({base:new P(base)}),findRangeByAddress:()=>({base:new P(begin),size:bytes,protection:options.readonly?'r--':'rw-'})},Interceptor:{attach(p,c){callbacks.set(p.v,c);}},send(v){events.push(v);},setInterval(){throw Error('Unexpected prefix wait');},clearInterval(){}},{timeout:2000});
 const hook=callbacks.get(base+0x6d56c0),out=[];
 for(const id of requests){let lo=0,hi=n;while(lo<hi){let m=(lo+hi)>>1;if(defs[m][0]<id)lo=m+1;else hi=m;}
  const row=lo<n&&defs[lo][0]===id?new P(rows+lo*232):new P(0),call={};hook.onEnter.call(call,[new P(manager),new P(id)]);
  if(hook.onLeave)hook.onLeave.call(call,options.badRow?row.add(1):row);
  out.push(row.isNull()?null:caps.get(row.v+16));
 }
 return{out,reads,writes,changed,events,caps};
}
const parent=path.join(H,'client-parent/tools/local_stack_limits.js'),candidate=path.join(H,'candidate/tools/local_stack_limits.js');
const defs=[[10,1],[20,10],[30,1000],[40,50],[50,0],[60,-1]],allowed=[10,20,30,50,60,999],requests=[20,10,40,999,30,50,60,20];
let a=replay(parent,defs,allowed,requests),b=replay(candidate,defs,allowed,requests);
assert.deepEqual(b.out,a.out);assert.equal(b.writes,1);assert(b.changed.every(p=>p===begin+16+defs.length*4+232+16));
const tests=['native_lookup_results_keep_same_stack_limits','singleton_zero_negative_and_existing_higher_caps_unchanged','unapproved_template_unchanged','missing_native_template_stays_missing','repeat_lookup_does_not_rewrite'];
assert.equal(replay(candidate,defs,allowed,[20],{foreign:true}).writes,0);tests.push('foreign_manager_is_not_modified');
for(const mode of ['badCount','readonly','badRow']){const r=replay(candidate,defs,allowed,[20,20],{[mode]:true});assert.equal(r.writes,0);assert.equal(r.events.filter(x=>x.status==='guard-rejected').length,1);}tests.push('invalid_table_row_or_protection_rejects_without_partial_write_or_retry');
const count=181836,large=Array.from({length:count},(_,i)=>[1000000+i,i%5===0?1:99]),ids=large.filter((r,i)=>i%16===1).map(r=>r[0]);
let t=performance.now();a=replay(parent,large,ids,[ids[0]]);const parent_ms=performance.now()-t;
t=performance.now();b=replay(candidate,large,ids,[ids[0]]);const candidate_ms=performance.now()-t;
assert.deepEqual(a.out,b.out);assert(b.reads<30&&a.reads>count*3);assert.equal(b.writes,1);tests.push('first_lookup_does_not_sweep_other_181835_templates');
const result={ok:true,tests,first_lookup:{templates:count,eligible:ids.length,parent_reads:a.reads,candidate_reads:b.reads,parent_writes:a.writes,candidate_writes:b.writes,parent_node_ms:parent_ms,candidate_node_ms:candidate_ms},native_arithmetic_mocked:false,native_lookup_mocked_in_host_test:true,game_process_access:false};
fs.writeFileSync(path.join(H,'stack-adapter-tests.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
