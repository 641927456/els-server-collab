// Fixed-build native guide lifecycle. Original Lua remains the geometry producer.
const elsActivityGuideConfig=__ACTIVITY_GUIDE_CONFIG__;
let elsActivityGuideLifecycle=null;
function installElsActivityGuideLifecycle(){
 if(elsActivityGuideLifecycle!==null)return;
 for(const [rva,prefix]of Object.entries(elsActivityGuideConfig.pins)){
  const actual=Array.from(new Uint8Array(game.base.add(Number(rva)).readByteArray(prefix.length/2)),x=>x.toString(16).padStart(2,'0')).join('');
  if(actual!==prefix)throw Error('Activity guide native identity mismatch: '+rva);
 }
 const listeners=[],rectScopes=new Map();
 let geometry=null,suppressed=null,internal=false,lastDecision='';
 // Original4AB6D0 registry semantics, including the whole generation-bearing token.
 function resolve(handle){
  if(handle.isNull())return ptr(0);
  const registry=game.base.add(0x4817068).readPointer();if(registry.isNull())return ptr(0);
  const buckets=registry.add(0x48).readPointer(),count=registry.add(0x58).readU32();
  if(buckets.isNull()||count===0)return ptr(0);
  let node=buckets.add(handle.toUInt32()%count*8).readPointer();
  while(!node.isNull()){
   if(node.add(0x18).readU32()===handle.toUInt32()&&node.readPointer().equals(handle))return node.add(8).readPointer();
   node=node.add(0x10).readPointer();
  }
  return ptr(0);
 }
 function shown(widget){
  if(widget.isNull())return false;
  const rva=widget.readPointer().add(0x3a0).readPointer().sub(game.base).toUInt32();
  return nativeCall(rva,'uint8',['pointer'])(widget)!==0;
 }
 function current(){
  const app=game.base.add(0x4817e80).readPointer(),engine=game.base.add(0x4817e70).readPointer();
  if(app.isNull()||engine.isNull()||app.add(0x160).readS32()!==14)return null;
  const chars=engine.add(0xc8).readPointer();if(chars.isNull())return null;
  const actor=chars.add(0xa0).readPointer();if(actor.isNull())return null;
  const service=game.base.add(0x4817e98).readPointer();if(service.isNull())return null;
  const manager=nativeCall(0x7b2f20,'pointer',['pointer'])(service);
  if(manager.isNull()||!manager.readPointer().equals(game.base.add(0x42df918)))return null;
  const state=nativeCall(0x7e7050,'pointer',['pointer'])(manager),uid=actor.add(0x48).readU64().toString();
  if(state.add(0x10).readU64().toString()!==uid||state.add(0x1d).readU8()!==0)return null;
  const handle=manager.add(0x18).readPointer(),view=resolve(handle);if(view.isNull())return null;
  const stage=state.add(8).readS32();
  return {manager,view,stage,key:uid+':'+manager.toString()+':'+handle.toString()+':'+stage};
 }
 function validRect(rect){return rect.every(Number.isFinite)&&rect[2]>rect[0]&&rect[3]>rect[1];}
 function readRect(widget){
  const output=Memory.alloc(16);
  nativeCall(0x4fed20,'pointer',['pointer','pointer'])(widget,output);
  return [0,4,8,12].map(offset=>output.add(offset).readFloat());
 }
 function guarded(selected){return selected!==null&&elsActivityGuideConfig.requirements[selected.stage]!==undefined;}
 function allowed(selected){
  if(geometry===null||geometry.key!==selected.key)return false;
  return elsActivityGuideConfig.requirements[selected.stage].every(method=>{
   const result=geometry.methods.get(method);
   if(result===undefined||!result.valid||!result.handles.every(handle=>shown(resolve(ptr(handle)))))return false;
   const rect=readRect(resolve(ptr(result.handles[0])));
   // Original Lua still owns the hole and arrow. Defer if its saved geometry
   // no longer describes the target; a new original callback replaces it.
   if(!validRect(rect)||!rect.every((value,index)=>value===result.rect[index]))return false;
   if(result.canvasHandle===null)return true;
   const canvas=readRect(resolve(ptr(result.canvasHandle)));
   return validRect(canvas)&&rect[0]>=canvas[0]&&rect[1]>=canvas[1]&&rect[2]<=canvas[2]&&rect[3]<=canvas[3];
  });
 }
 function display(selected,value){
  internal=true;
  try{nativeCall(0x2f98010,'void',['pointer','uint8'])(selected.view,value?1:0);}
  finally{internal=false;}
 }
 function apply(selected){
  if(!guarded(selected)){suppressed=null;return;}
  const allow=allowed(selected),root=resolve(selected.view.add(0x40).readPointer());
  if(!allow&&shown(root)){display(selected,false);suppressed=selected.key;}
  else if(allow&&suppressed===selected.key){if(!shown(root))display(selected,true);suppressed=null;}
  const decision=selected.key+':'+allow;
  if(decision!==lastDecision){lastDecision=decision;note({event:'activity_guide_visibility',stage:selected.stage,shown:allow});}
 }
 const enterRect=new NativeCallback((widget,thread,method)=>{
  let scope=rectScopes.get(thread);
  if(scope===undefined){
   const selected=current();if(!guarded(selected))return 0;
   scope={key:selected.key,method,handles:[],canvas:null,canvasHandle:null};rectScopes.set(thread,scope);
  }
  scope.handles.push(widget.add(8).readPointer().toString());
  return 1;
 },'uint',['pointer','uint','uint']);
 const leaveRect=new NativeCallback((widget,output,thread,outermost)=>{
  const rect=[0,4,8,12].map(offset=>output.add(offset).readFloat()),scope=rectScopes.get(thread);
  if(widget.readPointer().equals(game.base.add(0x4135238))){scope.canvas=rect;scope.canvasHandle=widget.add(8).readPointer().toString();}
  if(!outermost)return;
  rectScopes.delete(thread);
  const selected=current();if(selected===null||selected.key!==scope.key)return;
  if(geometry===null||geometry.key!==scope.key)geometry={key:scope.key,methods:new Map()};
  const canvas=scope.canvas;
  geometry.methods.set(scope.method,{handles:scope.handles,rect,canvasHandle:scope.canvasHandle,valid:validRect(rect)&&
   (canvas===null||(rect[0]>=canvas[0]&&rect[1]>=canvas[1]&&rect[2]<=canvas[2]&&rect[3]<=canvas[3]))});
 },'void',['pointer','pointer','uint','uint']);
 const ranges=elsActivityGuideConfig.ranges.map(([start,end,method])=>
  `{${game.base.add(start)}ULL,${game.base.add(end)}ULL,${method}}`).join(',');
 // The shared rectangle getter is also used by scrolling and hit testing.
 // Ordinary calls stay native. Nested calls are captured only inside a guide query.
 const rectListener=new CModule(`
  #include <gum/guminterceptor.h>
  typedef struct { guint64 start, end; guint method; } GuideRange;
  typedef struct { gpointer widget, output; } RectCall;
  static const GuideRange ranges[] = {${ranges}};
  extern guint enter_rect (gpointer widget, guint thread, guint method);
  extern void leave_rect (gpointer widget, gpointer output, guint thread, guint outermost);

  void on_enter (GumInvocationContext *ic) {
   RectCall *call = gum_invocation_context_get_listener_invocation_data (ic, sizeof (RectCall));
   call->widget = NULL;
   guint *depth = gum_invocation_context_get_listener_thread_data (ic, sizeof (guint));
   guint method = 0;
   if (*depth == 0) {
    guint64 caller = (guint64) gum_invocation_context_get_return_address (ic);
    for (guint i = 0; i < sizeof (ranges) / sizeof (ranges[0]); i++) {
     if (caller >= ranges[i].start && caller < ranges[i].end) {
      method = ranges[i].method;
      break;
     }
    }
    if (method == 0) return;
   }
   gpointer widget = gum_invocation_context_get_nth_argument (ic, 0);
   gpointer output = gum_invocation_context_get_nth_argument (ic, 1);
   if (enter_rect (widget, gum_invocation_context_get_thread_id (ic), method) == 0) return;
   // JS can call other instrumented functions, which may grow Gum's storage.
   call = gum_invocation_context_get_listener_invocation_data (ic, sizeof (RectCall));
   call->widget = widget;
   call->output = output;
   depth = gum_invocation_context_get_listener_thread_data (ic, sizeof (guint));
   ++*depth;
  }

  void on_leave (GumInvocationContext *ic) {
   RectCall *call = gum_invocation_context_get_listener_invocation_data (ic, sizeof (RectCall));
   if (call->widget == NULL) return;
   guint *depth = gum_invocation_context_get_listener_thread_data (ic, sizeof (guint));
   --*depth;
   leave_rect (call->widget, call->output, gum_invocation_context_get_thread_id (ic), *depth == 0);
  }
 `,{enter_rect:enterRect,leave_rect:leaveRect});
 listeners.push(Interceptor.attach(game.base.add(0x4fed20),{onEnter:rectListener.on_enter,onLeave:rectListener.on_leave}));
 listeners.push(Interceptor.attach(game.base.add(0x2f98010),{
  onEnter(args){
   // Native callers write DL; upper register bits are not a bool contract.
   if(internal)return;
   const selected=current();if(!guarded(selected)||!selected.view.equals(args[0]))return;
   if((args[1].toUInt32()&255)!==1){suppressed=null;return;}
   if(!allowed(selected)){args[1]=ptr(0);suppressed=selected.key;}
  }
 }));
 listeners.push(Interceptor.attach(game.base.add(0x2f926a0),{
  onLeave(){apply(current());}
 }));
 elsActivityGuideLifecycle={rectListener,enterRect,leaveRect,dispose(){
  for(const listener of listeners)listener.detach();rectScopes.clear();geometry=null;suppressed=null;elsActivityGuideLifecycle=null;
 }};
 note({event:'activity_guide_lifecycle_ready',scope:'native-578-guide-only',audited_geometry_methods:19,guarded_geometry_methods:18});
}
