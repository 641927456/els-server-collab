// Align only the template returned by the verified native lookup.
// The native binary search remains authoritative; no startup table sweep.
(() => {
  const allowed = new Set(__STACK_IDS__);
  const expectedPrefix = __LOOKUP_PREFIX__;
  const image = Process.getModuleByName('x2_dx11.exe');
  const lookup = image.base.add(0x6d56c0);
  const emit = v => send({event: 'local_stack_template_caps', at: Date.now(), ...v});
  const hex = p => Array.from(new Uint8Array(p.readByteArray(16)),
    x => x.toString(16).padStart(2, '0')).join('');
  let installed = false, disabled = false, attempts = 0, changed = 0;
  function align(manager, id, row) {
    // The native lookup returned this row. Only a pending change needs the
    // ownership/range checks; already aligned records require no mutation.
    const cap = row.add(16).readS32();
    if (cap <= 1 || cap >= 999) return;
    const app = image.base.add(0x4817e70).readPointer();
    if (app.isNull() || !app.add(0x58).readPointer().equals(manager)) return;
    const begin = manager.add(0x30).readPointer(), end = manager.add(0x38).readPointer();
    if (begin.isNull() || end.compare(begin) <= 0) return;
    const bytes = Number(end.sub(begin).toString());
    if (!Number.isSafeInteger(bytes) || bytes < 16 || bytes > 128 * 1024 * 1024)
      throw Error('Template vector bounds');
    const n = begin.add(8).readU32(), required = 16 + n * 236;
    if (!n || n > 250000 || required > bytes) throw Error('Template table count/range');
    const rows = begin.add(16 + n * 4), offset = Number(row.sub(rows).toString());
    if (!Number.isSafeInteger(offset) || offset < 0 || offset % 232 || offset >= n * 232)
      throw Error('Native template row bounds');
    const range = Process.findRangeByAddress(row);
    if (!range || !range.protection.includes('r') || !range.protection.includes('w') ||
        row.add(232).compare(range.base.add(range.size)) > 0)
      throw Error('Native template row is not readable/writable');
    if (begin.add(16 + offset / 232 * 4).readU32() !== id || row.readU32() !== id)
      throw Error('Native template key/row invariant');
    row.add(16).writeS32(999);
    if (++changed === 1) emit({status: 'applied', mode: 'native-lookup-result',
      first_template: id, previous: cap, maximum: 999, startup_table_sweep: false,
      item_counts_modified: false, disk_resources_modified: false});
  }
  function install() {
    if (installed || hex(lookup) !== expectedPrefix) return false;
    Interceptor.attach(lookup, {
      onEnter(args) {
        this.id = args[1].toUInt32();
        this.manager = !disabled && allowed.has(this.id) ? args[0] : null;
      },
      onLeave(row) {
        if (disabled || this.manager === null || row.isNull()) return;
        try { align(this.manager, this.id, row); }
        catch (error) {
          disabled = true;
          emit({status: 'guard-rejected', error: String(error)});
        }
      }
    });
    installed = true; emit({status: 'installed', scope: 'local-only', mode: 'native-lookup-result'});
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
