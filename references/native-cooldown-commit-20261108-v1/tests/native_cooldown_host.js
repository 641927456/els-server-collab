// Private native-instruction fixture, loaded only into a newly owned Python helper.
const realProcess=Process,RealNativeFunction=NativeFunction;
const image=Memory.alloc(0x4820000),at=r=>image.add(r),hooks=[];
Memory.protect(image,0x4820000,'rwx');
function put(r,bytes){at(r).writeByteArray(bytes);}
function jump(from,to){let d=to-from-5;return[0xe9,d&255,(d>>8)&255,(d>>16)&255,(d>>24)&255];}
// The parent shim supplies a private frame and preserves Windows nonvolatile state.
let entry=[0x55,0x53,0x48,0x83,0xec,0x38,0x0f,0x11,0x74,0x24,0x20,0x48,0x89,0xd5,0x4c,0x89,0xc3];
for(let mode=0;mode<5;mode++){
 entry.push(0x41,0x83,0xf9,mode);
 let from=0x8f4830+entry.length,d=(0x8f4900+mode*0x20)-(from+6);
 entry.push(0x0f,0x84,d&255,(d>>8)&255,(d>>16)&255,(d>>24)&255);
}
entry.push(...jump(0x8f4830+entry.length,0x8f4c60));put(0x8f4830,entry);
const skipBranches=[0x8f4b63,0x8f4b88,0x8f4bca];
for(let mode=0;mode<5;mode++){
 const start=0x8f4900+mode*0x20;
 const prefix=mode<3?[0x31,0xc0]:[0xf3,0x0f,0x10,0x75,0x28];
 put(start,[...prefix,...jump(start+prefix.length,mode<3?skipBranches[mode]:0x8f4c19)]);
}
// These branch, insertion/existing-key and continuation bytes are original image bytes.
for(const [r,hex]of Object.entries(__ORIGINAL_WINDOWS__))put(+r,Array.from(hex.match(/../g),h=>parseInt(h,16)));
put(0x8f4c60,[0x0f,0x10,0x74,0x24,0x20,0x48,0x83,0xc4,0x38,0x5b,0x5d,0xc3]);
for(const r of [0x8fe730,0x18ddeb3,0x682d80])put(r,[...Array(16).fill(0x90),0xc3]);
put(0x1ab7ac0,[0xb0,1,...Array(14).fill(0x90),0xc3]);
const game=Memory.alloc(0x700),actor=Memory.alloc(0x1a400),unit=Memory.alloc(0x900),manager=Memory.alloc(0x200),engine=Memory.alloc(0x200);
at(0x478cb88).writeU64(uint64('4294967296'));at(0x4817e70).writePointer(engine);
engine.add(0xc8).writePointer(manager);manager.add(0xa0).writePointer(unit);
unit.add(0x48).writeU64(1001);actor.add(0x1a3e0).writePointer(unit);
game.writePointer(at(0x41bfd28));game.add(0x2d0).writeS32(2);
const frame=Memory.alloc(0x80),node=Memory.alloc(0x40),iteration=Memory.alloc(0x40),child=Memory.alloc(0x40);
iteration.add(0x10).writePointer(child);child.add(0x19).writeU8(0);
let append=null,encoded=[];
function prepareElsReportWriter(){return{register(name,fn){append=fn;return()=>{append=null;};}};}
const fakeProcess={getModuleByName(name){if(name!=='x2_dx11.exe')throw Error('fixture module');return{base:image};},getCurrentThreadId:()=>realProcess.getCurrentThreadId()};
function FixtureNativeFunction(p,t,a){
 const r=Number(p.sub(image));
 if(r===0x159670)return()=>game;
 if(r===0x8571d0)return()=>actor;
 if(r===0x3b6dbd0||r===0x3b6dda0||r===0x3b6dcc0)return(stream,value)=>{encoded.push([r,String(value)]);return true;};
 return new RealNativeFunction(p,t,a);
}
((Process,NativeFunction)=>{
__PRODUCT_SOURCE__
const ctl=installElsDungeonResultStats(()=>true);
hooks.push(Interceptor.attach(at(0x1ab7ac0),{onEnter(){encoded=[];append(ptr(1));}}));
const runNative=new RealNativeFunction(at(0x8f4830),'void',['pointer','pointer','pointer','int']);
const reportNative=new RealNativeFunction(at(0x1ab7ac0),'uint8',['pointer']);
Interceptor.flush();
function invoke(mode,delta=0){
 frame.add(0x20).writeU64(2002);frame.add(0x28).writeFloat(delta);
 frame.add(0x30).writePointer(mode<3?ptr('0xffffffffffffffdf'):node);frame.add(0x38).writeU8(mode===3?1:0);
 node.add(0x20).writeU64(2002);node.add(0x28).writeFloat(mode===3?delta:100);
 runNative(unit.add(0x7c8),frame,iteration,mode);
 return node.add(0x28).readFloat();
}
function rows(){reportNative(game);const result={};for(let i=2;i<encoded.length;i+=2)result[encoded[i][1]]=Number(encoded[i+1][1]);return result;}
rpc.exports={run(){
 for(let mode=0;mode<3;mode++)invoke(mode);
 const skipped=rows();
 const insertedValue=invoke(3,1.5),afterInsert=rows();
 invoke(0);const afterSkippedIteration=rows();
 const existingValue=invoke(4,.25),afterExisting=rows();
 return{skipped,insertedValue,afterInsert,afterSkippedIteration,existingValue,afterExisting};
},cleanup(){ctl.dispose();for(const h of hooks)h.detach();}};
})(fakeProcess,FixtureNativeFunction);
