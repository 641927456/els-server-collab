// Startup-owned compatibility; all equipment and economy operations stay native/server-side.
function installElsEnhancementCap(){
 'use strict';
 if(globalThis.elsEnhancementCapSupport)return globalThis.elsEnhancementCapSupport;
 const module=Process.getModuleByName('x2_dx11.exe'),sites=__ENHANCEMENT_CAP_SITES__,mithrilPin=__ENHANCEMENT_MITHRIL_PIN__;
 const hex=(site,n)=>Array.from(new Uint8Array(site.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 const bytes=h=>h.match(/../g).map(x=>parseInt(x,16));
 function write(row,value){const p=module.base.add(row.rva);Memory.patchCode(p,value.length/2,w=>w.writeByteArray(bytes(value)));if(hex(p,value.length/2)!==value)throw Error('Enhancement cap write verification '+row.rva);}
 for(const row of sites)if(hex(module.base.add(row.rva),row.original.length/2)!==row.original)throw Error('Enhancement cap native identity '+row.rva);
 if(hex(module.base.add(mithrilPin.rva),mithrilPin.original.length/2)!==mithrilPin.original)throw Error('Enhancement mithril native identity');
 const installed=[];
 let mithrilHook=null;
 function restore(){
  for(const row of installed)if(hex(module.base.add(row.rva),row.updated.length/2)!==row.updated)throw Error('Enhancement cap changed by another component '+row.rva);
  if(mithrilHook){mithrilHook.detach();mithrilHook=null;Interceptor.flush();}
  for(const row of installed.slice().reverse())write(row,row.original);
 }
 try{
  for(const row of sites){installed.push(row);write(row,row.updated);}
  // The native getter looks up abs(level)+1 and the current smith profession.
  // Reuse the existing target-13 row for added levels; leave the item untouched.
  mithrilHook=Interceptor.attach(module.base.add(mithrilPin.rva),{onEnter(args){
   const level=args[1].toInt32(),absolute=Math.abs(level);
   if(absolute>=13&&absolute<20)args[1]=ptr(level<0?-12:12);
  }});
  Interceptor.flush();
 }
 catch(error){
  if(mithrilHook){mithrilHook.detach();mithrilHook=null;Interceptor.flush();}
  // A write may have thrown before committing. Restore only bytes owned here.
  for(const row of installed.slice().reverse()){
   const actual=hex(module.base.add(row.rva),row.original.length/2);
   if(actual===row.updated)write(row,row.original);
   else if(actual!==row.original)throw Error('Enhancement cap incomplete write '+row.rva+': '+error);
  }
  throw error;
 }
 const support={active:true,stop(){if(!this.active)return;restore();this.active=false;delete globalThis.elsEnhancementCapSupport;}};
 globalThis.elsEnhancementCapSupport=support;
 Script.bindWeak(support,()=>{if(support.active)restore();});
 send({event:'enhancement_cap_ready',maximum:20,fee_profile:12,mithril_target_profile:13,sites:sites.length,original_files_modified:false});
 return support;
}
