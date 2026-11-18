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
    // Internal formatter argument site: a probe must not trap a function return.
    Interceptor.attach(image.base.add(0x3475934),function(){
      const stack=stacks.get(Process.getCurrentThreadId()),s=stack&&stack[stack.length-1];
      if(!s||!s.ordinary||s.total<=999||s.total>=0x7fffffff)return;
      if(this.context.rsi.toInt32()!==s.total||this.context.rdx.toInt32()!==999)return;
      // Only the argument used to format the label changes. Item limits,
      // counts, bindings, cooldowns and network packets remain native.
      this.context.rdx=ptr(0x7fffffff);
    });
    installed=true;emit({status:'installed',scope:'local-ordinary-six-slot-HUD',counts_modified:false});return true;
  }
  if(!install()){
    const timer=setInterval(()=>{
      if(install())clearInterval(timer);
      else if(++attempts>=1200){clearInterval(timer);emit({status:'prefix-timeout'});}
    },100);
  }
})();

// STXItemSlot::SetCount, immediately before its Lua argument construction.
// Change formatting registers only; never change the shared template or slot.
(() => {
  const image = Process.getModuleByName('x2_dx11.exe');
  const prefixes = __ICON_PREFIXES__;
  const stackable = new Set(__ICON_STACK_IDS__);
  const singletons = new Set(__ICON_SINGLETON_IDS__);
  const hex = p => Array.from(new Uint8Array(p.readByteArray(16)),
    v => v.toString(16).padStart(2, '0')).join('');
  // Reuse the existing launcher's adapter failure handling.
  const emit = v => send({event: 'local_shortcut_exact_total', at: Date.now(),
    scope: 'item-icon-count', ...v});
  let installed = false, disabled = false, attempts = 0, changed = 0;

  function install() {
    if (installed) return true;
    if (!Object.entries(prefixes).every(([r, h]) => hex(image.base.add(+r)) === h)) return false;
    // This is an instruction probe, not a function entry/return hook.
    Interceptor.attach(image.base.add(0x675229), function() {
      if (disabled) return;
      const context = this.context, count = context.rdi.toInt32();
      const maximum = context.rdx.toInt32(), visible = context.rbx.toInt32();
      if (count <= 0 || maximum < 0 || (visible !== 0 && visible !== 1) ||
          (visible === 1 && maximum >= count)) return;
      try {
        const slot = context.rsi, vtable = slot.readPointer();
        if (!vtable.add(0x230).readPointer().equals(image.base.add(0x6751b0)) ||
            !vtable.add(0x270).readPointer().equals(image.base.add(0x679800))) return;
        const id = slot.add(0x12b8).readS32();
        if (!stackable.has(id) || (count === 1 && singletons.has(id))) return;
        if (slot.add(0x12c0).readS32() !== count || slot.add(0x12c4).readS32() !== maximum)
          throw Error('Item icon count argument mismatch');
        context.rdx = ptr(Math.max(maximum, count));
        context.rbx = ptr(1);
        if (++changed === 1) emit({status: 'applied', first_template: id,
          item_counts_modified: false, template_caps_modified: false});
      } catch (error) {
        disabled = true;
        emit({status: 'guard-rejected', error: String(error)});
      }
    });
    installed = true;
    emit({status: 'installed', item_counts_modified: false, template_caps_modified: false});
    return true;
  }
  if (!install()) {
    const timer = setInterval(() => {
      if (install()) clearInterval(timer);
      else if (++attempts >= 1200) {
        clearInterval(timer); emit({status: 'prefix-timeout'});
      }
    }, 100);
  }
})();
