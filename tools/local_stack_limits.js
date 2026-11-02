// Verified DX11 packed template table: count@8, sorted keys@16,
// 232-byte rows after keys, signed maximum@row+16. No item/save edits.
(() => {
  const allowed = new Set(__STACK_IDS__);
  const expectedPrefix = __LOOKUP_PREFIX__;
  const image = Process.getModuleByName('x2_dx11.exe');
  const lookup = image.base.add(0x6d56c0);
  const emit = v => send({event: 'local_stack_template_caps', at: Date.now(), ...v});
  const hex = p => Array.from(new Uint8Array(p.readByteArray(16)),
    x => x.toString(16).padStart(2, '0')).join('');
  let installed = false, busy = false, attempts = 0;
  const handled = new Set();
  function align(manager) {
    const app = image.base.add(0x4817e70).readPointer();
    if (app.isNull() || !app.add(0x58).readPointer().equals(manager)) return;
    const begin = manager.add(0x30).readPointer(), end = manager.add(0x38).readPointer();
    if (begin.isNull() || end.compare(begin) <= 0) return;
    const key = begin.toString() + ':' + end.toString();
    if (handled.has(key)) return;
    const bytes = Number(end.sub(begin).toString());
    if (!Number.isSafeInteger(bytes) || bytes < 16 || bytes > 128 * 1024 * 1024)
      throw Error('Template vector bounds');
    const range = Process.findRangeByAddress(begin);
    if (!range || !range.protection.includes('r') || !range.protection.includes('w'))
      throw Error('Template buffer is not readable/writable');
    const n = begin.add(8).readU32();
    if (!n) return; // The native loader has not populated the table yet.
    const required = 16 + n * 236;
    if (n > 250000 || required > bytes ||
        begin.add(required).compare(range.base.add(range.size)) > 0)
      throw Error('Template table count/range');
    const plan = [], before = {}, after = {};
    let previous = 0;
    for (let i = 0; i < n; i++) {
      const id = begin.add(16 + i * 4).readU32();
      const row = begin.add(16 + n * 4 + i * 232);
      if ((i && id <= previous) || row.readU32() !== id)
        throw Error('Template key/row invariant');
      previous = id;
      const cap = row.add(16).readS32();
      before[cap] = (before[cap] || 0) + 1;
      const change = allowed.has(id) && cap > 1 && cap < 999;
      const next = change ? 999 : cap;
      after[next] = (after[next] || 0) + 1;
      if (change) plan.push({id, field: row.add(16), before: cap});
    }
    // Validate the entire buffer before touching any field. Each write is
    // limited to an established stackable template in the server policy.
    const written = [];
    try {
      for (const item of plan) {
        if (item.field.readS32() !== item.before) throw Error('Template changed while planning');
        item.field.writeS32(999); written.push(item);
      }
    } catch (error) {
      for (const item of written) item.field.writeS32(item.before);
      throw error;
    }
    handled.add(key);
    emit({status: 'applied', templates: n, changed: plan.length,
      changed_ids: plan.map(x => x.id), histogram_before: before, histogram_after: after,
      singleton_preserved: before[1] === after[1], item_counts_modified: false,
      disk_resources_modified: false});
  }
  function install() {
    if (installed || hex(lookup) !== expectedPrefix) return false;
    Interceptor.attach(lookup, {onEnter(args) {
      if (busy) return;
      busy = true;
      try { align(args[0]); }
      catch (error) {
        // Fail closed for this buffer, with no partial writes or busy loop.
        try { handled.add(args[0].add(0x30).readPointer().toString() + ':' +
          args[0].add(0x38).readPointer().toString()); } catch (_) {}
        emit({status: 'guard-rejected', error: String(error)});
      } finally { busy = false; }
    }});
    installed = true; emit({status: 'installed', scope: 'local-only'}); return true;
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
