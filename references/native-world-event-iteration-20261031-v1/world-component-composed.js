// Resume the original outer loop after its own event-node destruction.
let elsWorldEventIterationSupport=null;
function installElsWorldEventIteration(){
 'use strict';
 if(elsWorldEventIterationSupport)return elsWorldEventIterationSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),pins={"9625616": "48895c2408488974241048897c24204c89442418554154415541564157488d6c", "9562652": "4c8d45af48", "9625758": "e88de9ffff", "9625763": "488b37488b4708488930488b0f488b47084889410849ff8eb0020000488d4f10e8285fffffba70000000488bcfe8cb5fbcff488bfe488b431080781900742648", "9625800": "ba70000000488bcfe8cb5fbcff488bfe", "9625816": "488b4310807819007426488b430880781900", "9625916": "488b3f4c8bff493bbea80200000f8511ffffff", "9626043": "e8c0eeffff", "9626048": "488b37488b4708488930488b0f488b47084889410849ff8ec0020000488d4f10e80b5effffba70000000488bcfe8ae5ebcff488bfe488b431080781900742948", "9626085": "ba70000000488bcfe8ae5ebcff488bfe", "9626101": "488b4310807819007429488b430880781900", "9626204": "488b3f4c8bff493bbeb80200000f8511ffffff", "9584624": "48895c2408574883ec20488bf94c8b41504d8b4008488d51504883c150e86ed8"};
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('World event native identity '+r);
 const rules=[[0x92e0a3,0x92e13f],[0x92e1c0,0x92e25f]],stubs=[],installed=[];
 try{
  for(const[site,resume]of rules){
   const stub=Memory.alloc(Process.pageSize,{near:module.base.add(site),maxDistance:0x7fffffff});
   const distance=BigInt(stub.toString())-BigInt(module.base.add(site).toString());
   if(distance < -0x7fffffffn || distance > 0x7fffffffn)throw Error('World event near stub distance');
   const writer=new X86Writer(stub);
   writer.putBytes(Array.from(new Uint8Array(module.base.add(site).readByteArray(32))));
   writer.putCallAddress(module.base.add(0x923ff0));
   writer.putMovRegU32('edx',0x70);
   writer.putMovRegReg('rcx','rdi');
   writer.putCallAddress(module.base.add(0x4f40a0));
   writer.putMovRegReg('rdi','rsi');
   writer.putJmpAddress(module.base.add(resume));
   writer.flush();
   if(!Memory.protect(stub,Process.pageSize,'r-x'))throw Error('World event private stub protection');
   stubs.push(stub);
  }
  for(let i=0;i<rules.length;i++){
   Interceptor.replaceFast(module.base.add(rules[i][0]),stubs[i]);
   installed.push(rules[i][0]);
  }
  Interceptor.flush();
  for(const site of [0x92e0d8,0x92e1f5]){const h=pins[site];if(hex(module.base.add(site),h.length/2)!==h)throw Error('World non-deletion branch changed');}
 }catch(error){
  installed.forEach(site=>Interceptor.revert(module.base.add(site)));Interceptor.flush();throw error;
 }
 let active=true;
 elsWorldEventIterationSupport={stubs,active:()=>active,stop(){
  if(!active)return;active=false;
  installed.forEach(site=>Interceptor.revert(module.base.add(site)));Interceptor.flush();
  send({event:'world_event_iteration_stopped',original_file_modified:false});
 }};
 send({event:'world_event_iteration_ready',sites:rules.map(([site,resume])=>({site,resume})),original_condition_actions_and_timers:true,original_file_modified:false});
 return elsWorldEventIterationSupport;
}
