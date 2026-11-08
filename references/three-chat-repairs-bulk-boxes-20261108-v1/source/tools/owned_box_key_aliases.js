// Only current native RandomItem records with explicitly approved missing keys.
// No template grants, count changes, eligibility changes or resource writes.
(() => {
  const name = 'elsOwnedBoxKeyAliasesV1';
  if (globalThis[name]) return;
  const spec = __OWNED_BOX_KEY_SPEC__;
  const module = Process.getModuleByName('x2_dx11.exe');
  const policies = new Map(spec.rules.map(r => [r.template, r.aliases]));
  const hooks = [];
  const changed = new Map();
  let disabled = false;
  const hex = p => Array.from(new Uint8Array(p.readByteArray(16)), b => b.toString(16).padStart(2, '0')).join('');
  const emit = fields => send({event: 'owned_box_key_aliases', ...fields});
  function manager() {
    const world = module.base.add(0x4817e70).readPointer();
    return world.isNull() ? ptr(0) : world.add(0x58).readPointer();
  }
  function records(m, template) {
    const head = m.add(0xb8).readPointer();
    if (head.isNull()) throw Error('Owned box native tree absent');
    const rows = [], visited = new Set(), pending = [head.add(8).readPointer()];
    while (pending.length) {
      const p = pending.pop();
      if (p.equals(head) || p.add(0x19).readU8()) continue;
      const address = p.toString();
      if (visited.has(address) || visited.size >= 20000) throw Error('Owned box native tree topology');
      visited.add(address);
      const key = p.add(0x20).readS32();
      // Native multimap is sorted by source ID, not the mutable key ID.
      if (template >= key) pending.push(p.add(0x10).readPointer());
      if (template <= key) pending.push(p.readPointer());
      if (key !== template) continue;
      const value = p.add(0x28).readPointer();
      if (value.isNull() || value.readS32() !== template) throw Error('Owned box native value identity');
      rows.push(value);
    }
    return rows;
  }
  function align(m, template) {
    const aliases = policies.get(template);
    if (!aliases || disabled || m.isNull() || !manager().equals(m)) return;
    const generation = m.toString() + ':' + m.add(0xb8).readPointer().toString();
    const writes = [];
    for (const value of records(m, template)) {
      const old = value.add(4).readS32(), replacement = aliases[old];
      if (replacement === undefined) continue;
      const range = Process.findRangeByAddress(value.add(4));
      if (!range || !range.protection.includes('w') || value.add(8).compare(range.base.add(range.size)) > 0)
        throw Error('Owned box native value range');
      writes.push({value, old, replacement});
    }
    // Validate the complete relevant graph before its first mutation.
    for (const w of writes) {
      w.value.add(4).writeS32(w.replacement);
      changed.set(generation + ':' + w.value.toString(), {template, old:w.old, replacement:w.replacement});
    }
    if (writes.length) emit({status:'applied',template,aliases:writes.length,original_possession_checks:true});
  }
  function enter(m, template) {
    try { align(m, template); }
    catch (error) { disabled = true; emit({status:'rejected',error:String(error)}); }
  }
  function dispose() {
    const m = manager();
    if (!m.isNull()) {
      const generation = m.toString() + ':' + m.add(0xb8).readPointer().toString();
      for (const template of policies.keys()) {
        for (const value of records(m, template)) {
          const record = changed.get(generation + ':' + value.toString());
          if (record && value.add(4).readS32() === record.replacement) value.add(4).writeS32(record.old);
        }
      }
    }
    for (const hook of hooks) hook.detach();
    changed.clear(); delete globalThis[name]; emit({status:'disposed'});
  }
  globalThis[name] = {dispose};
  let attempts = 0;
  function install() {
    for (const [rva, prefix] of Object.entries(spec.entry_prefixes))
      if (hex(module.base.add(Number(rva))) !== prefix) return false;
    hooks.push(Interceptor.attach(module.base.add(0x2231a40), {onEnter(a) {
      if (!a[1].isNull()) enter(manager(), a[1].add(8).readS32());
    }}));
    hooks.push(Interceptor.attach(module.base.add(0x6ac800), {onEnter(a) {
      enter(a[0], a[2].toInt32());
    }}));
    emit({status:'installed',sources:policies.size,original_resources:true}); return true;
  }
  if (!install()) {
    const timer = setInterval(() => {
      if (install() || ++attempts >= 1200) { clearInterval(timer); if (!hooks.length) emit({status:'prefix-timeout'}); }
    }, 100);
    const originalDispose = globalThis[name].dispose;
    globalThis[name].dispose = () => {clearInterval(timer);originalDispose();};
  }
})();
