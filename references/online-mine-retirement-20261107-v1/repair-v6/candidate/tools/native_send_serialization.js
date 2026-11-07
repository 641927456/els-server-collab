// Own the complete original encode/encrypt/enqueue call, without changing it.
// Retained for this process/script lifetime; unload only after process exit.
function prepareElsNativeSendSerialization() {
 'use strict';
 const module=Process.getModuleByName('x2_dx11.exe'),pins=__SEND_SERIALIZATION_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(module.base.add(+r),h.length/2)!==h)throw Error('Native send serialization identity '+r);
 return function installElsNativeSendSerialization() {
  if(globalThis.elsNativeSendSerialization)return globalThis.elsNativeSendSerialization;
  const kernel=Process.getModuleByName('kernel32.dll'),lock=Memory.alloc(40);
  const initialize=new NativeFunction(kernel.getExportByName('InitializeCriticalSection'),'void',['pointer']);
  initialize(lock);
  const callbacks=new CModule(`
   #include <gum/guminterceptor.h>
   extern unsigned char send_lock[];
   extern void enter_lock(void *);
   extern void leave_lock(void *);
   void on_enter(GumInvocationContext *context) { enter_lock(send_lock); }
   void on_leave(GumInvocationContext *context) { leave_lock(send_lock); }
  `,{send_lock:lock,enter_lock:kernel.getExportByName('EnterCriticalSection'),leave_lock:kernel.getExportByName('LeaveCriticalSection')});
  const listener=Interceptor.attach(module.base.add(0x682d80),{onEnter:callbacks.on_enter,onLeave:callbacks.on_leave});
  const controller=Object.freeze({active:()=>true,lock,callbacks,listener});
  globalThis.elsNativeSendSerialization=controller;
  return controller;
 };
}
