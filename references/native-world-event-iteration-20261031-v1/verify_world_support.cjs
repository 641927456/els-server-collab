const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'world-component-composed.js'),'utf8');
const pins=JSON.parse(code.match(/pins=(\{[^;]+\});/)[1]),base=0x140000000;
function setup({badPin=false,failSecond=false,badJoin=false}={}){
 const memory=new Map(),replaced=[],reverted=[],writers=[],events=[];let next=0x500000000;
 class P{constructor(n){this.n=Number(n);}add(n){return new P(this.n+Number(n));}toString(){return '0x'+this.n.toString(16);}readByteArray(n){return Uint8Array.from({length:n},(_,i)=>memory.get(this.n+i)||0).buffer;}}
 for(const[r,h]of Object.entries(pins))Buffer.from(h,'hex').forEach((v,i)=>memory.set(base+Number(r)+i,v));
 if(badPin)memory.set(base+0x92e010,0);
 class Writer{
  constructor(p){this.ops=[];writers.push(this.ops);}
  putBytes(a){this.ops.push(['bytes',Array.from(a)]);}putMovRegU32(...a){this.ops.push(['movU32',...a]);}putMovRegReg(...a){this.ops.push(['mov',...a]);}
  putCallAddress(p){this.ops.push(['call',p.n]);}putJmpAddress(p){this.ops.push(['jmp',p.n]);}flush(){}
 }
 const api={Process:{getModuleByName:()=>({base:new P(base)}),pageSize:4096},Memory:{alloc(n,options){const p=options.near.add(0x100000+writers.length*4096);return p;},protect:()=>true},X86Writer:Writer,
 Interceptor:{replaceFast(site,stub){if(failSecond&&replaced.length===1)throw Error('test installation failure');replaced.push(site.n);if(badJoin)memory.set(base+0x92e0d8,0);},revert:p=>reverted.push(p.n),flush(){}},send:r=>events.push(r)};
 const c=vm.createContext(api);vm.runInContext(code,c);
 return{c,replaced,reverted,writers,events};
}
const positive=setup();vm.runInContext('installElsWorldEventIteration();installElsWorldEventIteration();',positive.c);
assert.equal(positive.replaced.length,2);assert.deepEqual(positive.writers[0],[['bytes',Array.from(Buffer.from(pins[0x92e0a3],'hex').subarray(0,32))],['call',base+0x923ff0],['movU32','edx',112],['mov','rcx','rdi'],['call',base+0x4f40a0],['mov','rdi','rsi'],['jmp',base+0x92e13f]]);
vm.runInContext('elsWorldEventIterationSupport.stop();elsWorldEventIterationSupport.stop();',positive.c);assert.equal(positive.reverted.length,2);
const bad=setup({badPin:true});assert.throws(()=>vm.runInContext('installElsWorldEventIteration()',bad.c),/identity/);assert.equal(bad.replaced.length,0);
const partial=setup({failSecond:true});assert.throws(()=>vm.runInContext('installElsWorldEventIteration()',partial.c),/installation failure/);assert.deepEqual(partial.reverted,[base+0x92e0a3]);
const join=setup({badJoin:true});assert.throws(()=>vm.runInContext('installElsWorldEventIteration()',join.c),/non-deletion branch/);assert.equal(join.reverted.length,2);
const report={ok:true,model_cases:5,scope:'Own Node model with explicit emitter/Interceptor shims; no real game or native execution.',repeat_install_and_stop:true,pin_mismatch_before_mutation:true,partial_install_rollback:true,non_deletion_entry_preserved:true,original_free_call_and_arguments_retained:true};
fs.writeFileSync(path.join(__dirname,'world-support-model-qualification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
