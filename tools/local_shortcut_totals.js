// 34756F0 passes (maximum=999,total,valid) to original Lua SetCount.
// Keep its original total and update flow; remove only ordinary HUD "999+".
(() => {
  const image=Process.getModuleByName('x2_dx11.exe'),prefixes=__PREFIXES__;
  const hex=p=>Array.from(new Uint8Array(p.readByteArray(16)),v=>v.toString(16).padStart(2,'0')).join('');
  const stacks=new Map();let attempts=0,installed=false;
  const emit=v=>send({event:'local_shortcut_exact_total',at:Date.now(),...v});
  function install(){
    if(installed)return true;
    if(!Object.entries(prefixes).every(([r,h])=>hex(image.base.add(+r))===h))return false;
    Interceptor.attach(image.base.add(0x34756f0),{
      onEnter(a){
        this.id=Process.getCurrentThreadId();
        const frame=a[0],slot=a[1].toInt32(),total=a[2].toInt32();let ordinary=false;
        try{ordinary=slot>=0&&slot<6&&frame.add(0x40).readS32()===0&&
          frame.add(0x58).readPointer().sub(frame.add(0x50).readPointer()).toInt32()===48;}catch(_){}
        const stack=stacks.get(this.id)||[];stack.push({ordinary,total,slot});stacks.set(this.id,stack);
      },
      onLeave(){const stack=stacks.get(this.id);if(stack){stack.pop();if(!stack.length)stacks.delete(this.id);}}
    });
    Interceptor.attach(image.base.add(0x3475934),{onEnter(){
      const stack=stacks.get(Process.getCurrentThreadId()),s=stack&&stack[stack.length-1];
      if(!s||!s.ordinary||s.total<=999||s.total>=0x7fffffff)return;
      if(this.context.rsi.toInt32()!==s.total||this.context.rdx.toInt32()!==999)return;
      // Only the argument used to format the label changes. Item limits,
      // counts, bindings, cooldowns and network packets remain native.
      this.context.rdx=ptr(0x7fffffff);
    }});
    installed=true;emit({status:'installed',scope:'local-ordinary-six-slot-HUD',counts_modified:false});return true;
  }
  if(!install()){
    const timer=setInterval(()=>{
      if(install())clearInterval(timer);
      else if(++attempts>=1200){clearInterval(timer);emit({status:'prefix-timeout'});}
    },100);
  }
})();
