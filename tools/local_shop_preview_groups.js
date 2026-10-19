// Exact-build native correction: cycle an ordinal through the filtered group
// keys, exactly as the random-preview branch does at RVA 6A5F68. The original
// ordinal-as-key path could dereference map::end() for keys such as {1}.
(function () {
  const m=Process.getModuleByName('x2_dx11.exe'),prefixes=__PREVIEW_GROUP_PREFIXES__;
  const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
  for(const [r,h] of Object.entries(prefixes))if(hex(m.base.add(Number(r)),h.length/2)!==h)throw Error('Preview build guard '+r);
  const site=m.base.add(0x6a5e5f),back=site.add(5);
  const thunk=Memory.alloc(Process.pageSize,{near:site,maxDistance:0x7fffffff});
  function jump(from,to){
    const delta=to.sub(from.add(5)).toInt32();
    if(!from.add(5).add(delta).equals(to))throw Error('Preview branch distance');
    return [0xe9,...Array.from({length:4},(_,i)=>(delta>>>(i*8))&255)];
  }
  // mov rdx,[rsp+78]; movsxd rax,ebx; mov ebx,[rdx+rax*4];
  // mov rcx,[rsp+28] (displaced original instruction); jmp original+5.
  const bytes=[0x48,0x8b,0x54,0x24,0x78,0x48,0x63,0xc3,0x8b,0x1c,0x82,0x48,0x8b,0x4c,0x24,0x28];
  bytes.push(...jump(thunk.add(bytes.length),back));
  thunk.writeByteArray(bytes);Memory.protect(thunk,Process.pageSize,'r-x');
  const branch=jump(site,thunk);
  Memory.patchCode(site,5,p=>p.writeByteArray(branch));
  // Native cycle bound originally used the unfiltered map size. EDI is the
  // filtered key count, already checked nonzero immediately before this path.
  Memory.patchCode(m.base.add(0x6a5e11),4,p=>p.writeByteArray([0x89,0xf8,0x90,0x90]));
  if(hex(site,5)!==branch.map(v=>v.toString(16).padStart(2,'0')).join('')||hex(m.base.add(0x6a5e11),4)!=='89f89090')throw Error('Preview patch verification');
  // Startup-owned script stays loaded for the lifetime of the client.
  globalThis.ownedShopPreviewGroupThunk=thunk;
  send({event:'shop_preview_group_compat_ready',timestamp:Date.now(),native_key_lookup:true,filtered_cycle_bound:true});
})();
