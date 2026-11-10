// MyBuff removes its current map node through the original virtual RemoveBuff.
// Resume from the live head; never retain a native object or node in JavaScript.
let elsMyBuffCleanupSupport=null,elsMyBuffCleanupAttempted=false;
function installElsMyBuffCleanup(){
 'use strict';
 if(elsMyBuffCleanupSupport){elsMyBuffCleanupSupport.start();return elsMyBuffCleanupSupport;}
 const module=Process.getModuleByName('x2_dx11.exe'),profile=__MY_BUFF_CLEANUP_PROFILE__;
 const site=module.base.add(profile.site),resume=module.base.add(profile.resume);
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 function original(){
  if(Process.arch!=='x64'||Process.pointerSize!==8)throw Error('MyBuff architecture identity');
  for(const [r,h]of Object.entries(profile.bodies))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('MyBuff native body identity '+r);
  if(!module.base.add(profile.vtable+0x1e0).readPointer().equals(module.base.add(profile.remove)))throw Error('MyBuff RemoveBuff virtual identity');
 }
 original(); // No allocation or code mutation before every live identity check.
 const stub=Memory.alloc(Process.pageSize,{near:site,maxDistance:0x7fffffff});
 const distance=BigInt(stub.toString())-BigInt(site.add(5).toString());
 if(distance < -0x80000000n || distance > 0x7fffffffn)throw Error('MyBuff near stub distance');
 const writer=new X86Writer(stub);
 writer.putBytes([0x48,0x8b,0x47,0x50,0x48,0x8b,0x18]); // RAX=[RDI+50]; RBX=[RAX].
 writer.putJmpAddress(resume);
 writer.flush();
 if(!Memory.protect(stub,Process.pageSize,'r-x'))throw Error('MyBuff private stub protection');
 let state='stopped',lastReportError=null;
 function report(event){
  try{send({event,timestamp:Date.now(),thread:Process.getCurrentThreadId(),site:profile.site,resume:profile.resume,original_remove_and_erase_retained:true,original_file_modified:false});}
  catch(error){lastReportError=String(error);} // A diagnostic failure cannot undo a committed repair.
 }
 function redirected(){
  if(site.readU8()!==0xe9||!site.add(5).add(site.add(1).readS32()).equals(stub))throw Error('MyBuff direct redirect identity');
  // Pinned Gum FAST reserves 16 bytes and consumes whole instructions: this
  // site requires 18 (4+4+2+4+4). Its near E9 leaves exactly 13 bytes of NOPs.
  if(hex(site.add(5),profile.overwrite_size-5)!==profile.redirect_padding)throw Error('MyBuff redirect padding identity');
  const body=profile.bodies[profile.cleanup],offset=profile.site-profile.cleanup;
  if(hex(module.base.add(profile.cleanup),offset)!==body.slice(0,offset*2)||hex(site.add(profile.overwrite_size),body.length/2-offset-profile.overwrite_size)!==body.slice((offset+profile.overwrite_size)*2))throw Error('MyBuff unaffected cleanup identity');
  if(hex(module.base.add(profile.remove),profile.bodies[profile.remove].length/2)!==profile.bodies[profile.remove])throw Error('MyBuff RemoveBuff changed');
 }
 const api={stub,active:()=>state==='active',status:()=>({state,last_report_error:lastReportError}),
  start(){
   if(state==='active')return api;
   if(state==='failed')throw Error('MyBuff restoration failed; new owner lifecycle required');
   original();let installed=false;
   try{
    Interceptor.replaceFast(site,stub);installed=true;
    Interceptor.flush();redirected();state='active';
   }catch(error){
    if(installed){
     try{Interceptor.revert(site);Interceptor.flush();original();state='stopped';}
     catch(rollbackError){state='failed';installElsMyBuffCleanup.failedInstallation={reason:String(error),rollback_error:String(rollbackError)};throw error;}
    }
    throw error;
   }
   report('my_buff_cleanup_ready');return api;
  },
  // Owner-only, quiescent lifecycle operation: no Cleanup/native caller may be
  // in flight. Production has no hot-toggle entry. Keep stub alive through
  // stop/re-enable and until normal host shutdown after the game has exited.
  stop(){
   if(state==='stopped')return api;
   if(state==='failed')throw Error('MyBuff restoration state is unknown');
   try{Interceptor.revert(site);Interceptor.flush();original();state='stopped';}
   catch(error){state='failed';throw error;}
   report('my_buff_cleanup_stopped');return api;
  }
 };
 // Retain executable storage before publishing its native redirect, including
 // rollback failures. No process-lifetime native pointer is cached here.
 elsMyBuffCleanupSupport=api;
 return api.start();
}
function installElsMyBuffCleanupOnce(){
 if(elsMyBuffCleanupAttempted)return elsMyBuffCleanupSupport;
 elsMyBuffCleanupAttempted=true;
 try{return installElsMyBuffCleanup();}
 catch(error){
  const failure=installElsMyBuffCleanup.failedInstallation||{reason:String(error)};
  installElsMyBuffCleanup.failedInstallation=failure;
  try{send({event:'my_buff_cleanup_disabled',timestamp:Date.now(),...failure,original_file_modified:false});}
  catch(reportError){failure.report_error=String(reportError);}
  return null; // This optional repair must not disable existing cache/support work.
 }
}
