// Read the exception supplied to the game's own crash filter. No exception
// handler installation, stack unwind, native calls, or altered return values.
const fatalM=Process.getModuleByName('x2_dx11.exe');
const fatalSeen=new Set();
let fatalEventSequence=0;
let fatalModuleMessagesDropped=0;
function reportFatalModule(event,m){
 try{send({event,timestamp:Date.now(),name:m.name,base:m.base.toString(),size:m.size,module_messages_dropped:fatalModuleMessagesDropped});}
 catch(error){fatalModuleMessagesDropped++;}
}
Process.attachModuleObserver({onAdded(m){
 reportFatalModule('module_loaded',m);
 if(m.name.toLowerCase()!=='bugtrapu-x64.dll')return;
 for(const name of ['BT_SehFilter','BT_CppFilter']){
  const f=m.findExportByName(name);if(!f||fatalSeen.has(f.toString()))continue;fatalSeen.add(f.toString());
  Interceptor.attach(f,{onEnter(a){const faultId=++fatalEventSequence;try{
   const rec=a[0].readPointer(),ctx=a[0].add(8).readPointer();
   const out={event:'original_fatal_exception',timestamp:Date.now(),fault_id:faultId,capture_stage:'game_crash_filter',filter:name,filter_address:f.toString(),thread:this.threadId,code:'0x'+rec.readU32().toString(16),address:rec.add(16).readPointer().toString(),parameters:[],registers:{},register_read_errors:[]};
   for(let i=0;i<Math.min(rec.add(24).readU32(),15);i++)out.parameters.push(rec.add(32+i*8).readPointer().toString());
   for(const [k,o] of [['rax',0x78],['rcx',0x80],['rdx',0x88],['rbx',0x90],['rsp',0x98],['rbp',0xa0],['rsi',0xa8],['rdi',0xb0],['r8',0xb8],['r9',0xc0],['r10',0xc8],['r11',0xd0],['r12',0xd8],['r13',0xe0],['r14',0xe8],['r15',0xf0],['rip',0xf8]]){
    try{out.registers[k]=ctx.add(o).readPointer().toString();}
    catch(error){out.register_read_errors.push({register:k,error:String(error)});}
   }
   send(out);
   try{
    if(out.registers.rsp===undefined)throw Error('RSP was not captured');
    send({event:'original_fatal_stack',timestamp:Date.now(),fault_id:faultId,thread:this.threadId,address:out.registers.rsp,requested_bytes:2048,unwound:false,hex:Array.from(new Uint8Array(ptr(out.registers.rsp).readByteArray(2048)),x=>x.toString(16).padStart(2,'0')).join('')});
   }catch(error){send({event:'original_fatal_stack_unavailable',timestamp:Date.now(),fault_id:faultId,thread:this.threadId,address:out.registers.rsp||null,requested_bytes:2048,error:String(error)});}
  }catch(e){send({event:'original_fatal_read_error',timestamp:Date.now(),fault_id:faultId,filter:name,thread:this.threadId,error:String(e)});}}});
 }
 send({event:'original_fatal_observer_ready',timestamp:Date.now(),capture_stage:'game_crash_filter',module_inventory:true,module_messages_dropped:fatalModuleMessagesDropped,stack_requested_bytes:2048});
},onRemoved(m){
 reportFatalModule('module_unloaded',m);
}});
