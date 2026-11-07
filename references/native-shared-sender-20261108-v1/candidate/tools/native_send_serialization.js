// One native lock listener and one JS listener share this original sender.
// Frida 17.23.3 has only two invocation-state slots per function.
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
  const observers=[],scopes=Symbol('sender observer scopes');
  function invoke(callback,context,value) {
   if(!callback)return;
   try{callback.call(context,value);}catch(error){setImmediate(()=>{throw error;});}
  }
  function observerContext(native) {
   return new Proxy(Object.create(null),{
    get(state,key){return Object.hasOwn(state,key)?state[key]:Reflect.get(native,key,native);},
    set(state,key,value){if(key==='errno'||key==='lastError')return Reflect.set(native,key,value,native);state[key]=value;return true;}
   });
  }
  const observerListener=Interceptor.attach(module.base.add(0x682d80),{
   onEnter(args){
    const calls=[];this[scopes]=calls;
    for(const observer of observers.slice()){
     if(!observer.active)continue;
     const context=observerContext(this);calls.push({observer,context});
     invoke(observer.callbacks.onEnter,context,args);
    }
   },
   onLeave(result){
    for(const {observer,context}of this[scopes])if(observer.active)invoke(observer.callbacks.onLeave,context,result);
   }
  });
  const controller=Object.freeze({active:()=>true,lock,callbacks,listener,observerListener,
   observe(callbacks){
    const observer={callbacks,active:true};observers.push(observer);
    return{detach(){observer.active=false;const index=observers.indexOf(observer);if(index>=0)observers.splice(index,1);}};
   },observerCount:()=>observers.length});
  globalThis.elsNativeSendSerialization=controller;
  return controller;
 };
}
function elsObserveNativeSend(callbacks) {
 return globalThis.elsNativeSendSerialization.observe(callbacks);
}
