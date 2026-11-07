// Prototype only. No production signature, installation or hot unload.
function installElsNativeCryptoLock(module) {
 'use strict';
 if(globalThis.elsNativeCryptoLockLifetime)throw Error('Native crypto lock already attempted');
 const kernel=Process.getModuleByName('kernel32.dll'),nt=Process.getModuleByName('ntdll.dll');
 const api=(name,result,args)=>new NativeFunction(kernel.getExportByName(name),result,args);
 const lock=Memory.alloc(40),refs=Memory.alloc(16),tls=Memory.alloc(4),eventCell=Memory.alloc(8),heap=Memory.alloc(8),metrics=Memory.alloc(16);
 const initialize=api('InitializeCriticalSectionEx','int',['pointer','uint','uint']);
 if(!initialize(lock,0,0))throw Error('Native crypto lock initialization');
 const index=api('TlsAlloc','uint',[])();if(index===0xffffffff)throw Error('Native crypto TLS allocation');tls.writeU32(index);
 const event=api('CreateEventW','pointer',['pointer','int','int','pointer'])(ptr(0),1,0,ptr(0));
 if(event.isNull())throw Error('Native crypto startup event');eventCell.writePointer(event);
 heap.writePointer(api('GetProcessHeap','pointer',[])());
 const callbacks=new CModule(`
  typedef unsigned int U32;
  typedef unsigned long long U64;
  typedef unsigned char (*Encrypt)(void *,void *);
  typedef void (*Destroy)(void *);
  typedef struct Held { void *ctx; struct Held *previous; } Held;
  extern unsigned char crypto_lock[], original_refs[], tls_slot[], ready_event[], native_heap[];
  extern volatile U32 metrics[];
  extern void EnterCriticalSection(void *);
  extern void LeaveCriticalSection(void *);
  extern U32 WaitForSingleObject(void *,U32);
  extern void *TlsGetValue(U32);
  extern int TlsSetValue(U32,void *);
  extern void *HeapAlloc(void *,U32,U64);
  extern int HeapFree(void *,U32,void *);
  extern U32 GetLastError(void);
  extern void SetLastError(U32);
  unsigned char locked_encrypt(void *ctx,void *packet) {
   U32 saved_error=GetLastError();
   WaitForSingleObject(*(void **)ready_event,0xffffffffu);
   Held *held=(Held *)HeapAlloc(*(void **)native_heap,0,sizeof(Held));
   if(!held){metrics[3]=1;return 0;}
   EnterCriticalSection(crypto_lock);
   held->ctx=ctx;held->previous=(Held *)TlsGetValue(*(U32 *)tls_slot);
   if(!TlsSetValue(*(U32 *)tls_slot,held)){
    metrics[3]=1;LeaveCriticalSection(crypto_lock);HeapFree(*(void **)native_heap,0,held);return 0;
   }
   metrics[0]++;metrics[2]++;
   SetLastError(saved_error);
   return ((Encrypt)*(void **)original_refs)(ctx,packet);
  }
  void release_destroy(void *ctx) {
   U32 saved_error=GetLastError();
   WaitForSingleObject(*(void **)ready_event,0xffffffffu);
   Held *held=(Held *)TlsGetValue(*(U32 *)tls_slot);
   if(held&&held->ctx==ctx){
    TlsSetValue(*(U32 *)tls_slot,held->previous);metrics[1]++;metrics[2]--;
    LeaveCriticalSection(crypto_lock);HeapFree(*(void **)native_heap,0,held);
   }
   SetLastError(saved_error);((Destroy)*((void **)original_refs+1))(ctx);
  }
  void read_stats(U32 *out) {
   U32 saved_error=GetLastError();
   EnterCriticalSection(crypto_lock);
   for(U32 i=0;i<4;i++)out[i]=metrics[i];
   LeaveCriticalSection(crypto_lock);
   SetLastError(saved_error);
  }
  void end_marker(void) {}
 `,{crypto_lock:lock,original_refs:refs,tls_slot:tls,ready_event:eventCell,native_heap:heap,metrics,
 EnterCriticalSection:kernel.getExportByName('EnterCriticalSection'),LeaveCriticalSection:kernel.getExportByName('LeaveCriticalSection'),
 WaitForSingleObject:kernel.getExportByName('WaitForSingleObject'),TlsGetValue:kernel.getExportByName('TlsGetValue'),TlsSetValue:kernel.getExportByName('TlsSetValue'),
 HeapAlloc:kernel.getExportByName('HeapAlloc'),HeapFree:kernel.getExportByName('HeapFree'),GetLastError:kernel.getExportByName('GetLastError'),SetLastError:kernel.getExportByName('SetLastError')});
 // Keep generated code, its unwind tables and original-reference cells alive
 // even when a later startup step fails. The owner exits before detach.
 const lifetime={callbacks,lock,refs,tls,event,heap,metrics,installed:false,failed:null};
 globalThis.elsNativeCryptoLockLifetime=lifetime;
 const lookup=new NativeFunction(nt.getExportByName('RtlLookupFunctionEntry'),'pointer',['uint64','pointer','pointer']);
 const imageBase=Memory.alloc(8),unwind=[];
 for(const [start,end]of [[callbacks.locked_encrypt,callbacks.release_destroy],[callbacks.release_destroy,callbacks.read_stats],[callbacks.read_stats,callbacks.end_marker]]){
  const size=end.sub(start).toInt32();if(size<=0||size>8192)throw Error('Native wrapper range');
  for(let address=start;address.compare(end)<0;){
   const instruction=Instruction.parse(address);address=instruction.next;if(instruction.mnemonic!=='call')continue;
   const pc=address.sub(1),entry=lookup(uint64(pc.toString()),imageBase,ptr(0));
   if(entry.isNull())throw Error('Native wrapper has no unwind table at '+pc);
   const base=imageBase.readPointer(),begin=base.add(entry.readU32()),finish=base.add(entry.add(4).readU32());
   if(pc.compare(begin)<0||pc.compare(finish)>=0)throw Error('Native wrapper unwind range');
   unwind.push({call_return_pc:address.toString(),begin:begin.toString(),end:finish.toString(),unwind:base.add(entry.add(8).readU32()).toString()});
  }
 }
 const setReady=api('SetEvent','int',['pointer']);let releaseInstalled=false;
 try {
  refs.add(8).writePointer(Interceptor.replaceFast(module.base.add(0x3b7d620),callbacks.release_destroy));releaseInstalled=true;
  refs.writePointer(Interceptor.replaceFast(module.base.add(0x3b7d860),callbacks.locked_encrypt));
  lifetime.installed=true;
 }catch(error){lifetime.failed=String(error);throw error;}
 finally {
  // Release-only startup failure must remain a valid destructor passthrough.
  if(releaseInstalled&&!setReady(event))throw Error('Native crypto startup event signal');
 }
 const snapshot=new NativeFunction(callbacks.read_stats,'void',['pointer']);
 return Object.freeze({lock,callbacks,lifetime,unwind,
  stats(){const out=Memory.alloc(16);snapshot(out);return{encryptions:out.readU32(),cleanups:out.add(4).readU32(),active:out.add(8).readU32(),failed:out.add(12).readU32()};}
 });
}
