// Feed the two original source tables to the original contiguous stage parser.
let elsSparseStagesSupport=null;
function installElsSparseStages(){
 'use strict';
 if(elsSparseStagesSupport)return elsSparseStagesSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__SPARSE_STAGE_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Sparse stage native identity '+r);
 const frames=new Map(),hooks=[],keys={STAGE1:Memory.allocUtf8String('STAGE2'),STAGE2:Memory.allocUtf8String('STAGE3')};let active=true;
 function stop(reason){
  if(!active)return;active=false;hooks.forEach(h=>h.detach());frames.clear();
  send({event:'native_sparse_stages_stopped',reason:String(reason)});
 }
 try{
  hooks.push(Interceptor.attach(module.base.add(0x1034ba0),{
   onEnter(args){
    this.tid=null;if(!active)return;
    try{
     const source=args[1].readUtf16String().toLowerCase(),tid=Process.getCurrentThreadId(),stack=frames.get(tid)||[];
     this.qualified=source==='dungeon_lithia_memory6_1.lua';this.definition=args[0];
     stack.push(this.qualified);frames.set(tid,stack);this.tid=tid;
    }catch(error){stop(error);}
   },
   onLeave(){
    const stack=frames.get(this.tid);if(stack){stack.pop();if(!stack.length)frames.delete(this.tid);}
    if(active&&this.qualified)try{
     const begin=this.definition.add(0x20).readPointer(),end=this.definition.add(0x28).readPointer();
     send({event:'native_sparse_stage_load_complete',source:'Dungeon_LITHIA_MEMORY6_1.lua',stage_count:end.sub(begin).toInt32()/8});
    }catch(error){stop(error);}
   }
  }));
  hooks.push(Interceptor.attach(module.base.add(0x393a010),{
   onEnter(args){
    if(!active)return;
    const stack=frames.get(Process.getCurrentThreadId());
    if(!stack||!stack[stack.length-1]||!this.returnAddress.equals(module.base.add(0x103611f)))return;
    try{
     const key=args[1].readUtf8String(),replacement=keys[key];
     if(replacement){args[1]=replacement;send({event:'native_sparse_stage_key',source:'Dungeon_LITHIA_MEMORY6_1.lua',ordinal_key:key,source_key:key==='STAGE1'?'STAGE2':'STAGE3',original_parser:true});}
    }catch(error){stop(error);}
   }
  }));
 }catch(error){stop(error);throw error;}
 elsSparseStagesSupport={keys,stop,active:()=>active};
 send({event:'native_sparse_stages_ready',source:'Dungeon_LITHIA_MEMORY6_1.lua',original_file_modified:false});
 return elsSparseStagesSupport;
}
