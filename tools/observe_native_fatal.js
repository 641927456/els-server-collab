// Read the exception supplied to the game's own crash filter. No exception
// handler installation, stack unwind, native calls, or altered return values.
const fatalM=Process.getModuleByName('x2_dx11.exe');
const fatalSeen=new Set();
Process.attachModuleObserver({onAdded(m){
 if(m.name.toLowerCase()!=='bugtrapu-x64.dll')return;
 for(const name of ['BT_SehFilter','BT_CppFilter']){
  const f=m.findExportByName(name);if(!f||fatalSeen.has(f.toString()))continue;fatalSeen.add(f.toString());
  Interceptor.attach(f,{onEnter(a){try{
   const rec=a[0].readPointer(),ctx=a[0].add(8).readPointer();
   const out={event:'original_fatal_exception',timestamp:Date.now(),filter:name,thread:this.threadId,code:'0x'+rec.readU32().toString(16),address:rec.add(16).readPointer().toString(),parameters:[],registers:{}};
   for(let i=0;i<Math.min(rec.add(24).readU32(),15);i++)out.parameters.push(rec.add(32+i*8).readPointer().toString());
   for(const [k,o] of [['rax',0x78],['rcx',0x80],['rdx',0x88],['rbx',0x90],['rsp',0x98],['rbp',0xa0],['rsi',0xa8],['rdi',0xb0],['r8',0xb8],['r9',0xc0],['r10',0xc8],['r11',0xd0],['r12',0xd8],['r13',0xe0],['r14',0xe8],['r15',0xf0],['rip',0xf8]])out.registers[k]=ctx.add(o).readPointer().toString();
   send(out);
   try{send({event:'original_fatal_stack',timestamp:Date.now(),address:out.registers.rsp,hex:Array.from(new Uint8Array(ptr(out.registers.rsp).readByteArray(2048)),x=>x.toString(16).padStart(2,'0')).join('')});}catch(e){}
  }catch(e){send({event:'original_fatal_read_error',error:String(e)});}}});
 }
 send({event:'original_fatal_observer_ready',timestamp:Date.now()});
}});
