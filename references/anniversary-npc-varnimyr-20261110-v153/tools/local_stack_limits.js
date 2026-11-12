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
  const actionBooks = new Map(__ANNIVERSARY_ACTION_BOOKS__.map(book => [book.template, book]));
  const actionTables = new Map();

  function actionBook(manager, id) {
    const app = image.base.add(0x4817e70).readPointer();
    if (app.isNull() || !app.add(0x58).readPointer().equals(manager)) return null;
    const begin = manager.add(0x30).readPointer(), end = manager.add(0x38).readPointer();
    const strings = image.base.add(0x478ae30).readPointer();
    if (begin.isNull() || end.compare(begin) <= 0 || strings.isNull()) return null;
    const key = [manager, begin, end, strings].join(':');
    const cached = actionTables.get(key);
    if (cached !== undefined) return cached.records.get(id);

    const count = 181836, bytes = 85682984;
    if (Number(end.sub(begin).toString()) !== bytes || begin.readU32() !== 0x204d494b ||
        begin.add(4).readU32() !== 0x1201 || begin.add(8).readU32() !== count ||
        strings.readU32() !== 0x204d494b || strings.add(8).readU32() !== count ||
        strings.add(78383346).readU16() !== 15 ||
        strings.add(78383348).readUtf16String(15) !== '[路莉尔]噗鲁不负有心人：诺亚')
      throw Error('Anniversary action book item table identity');

    // Compact KIM references are offsets from the native strings base.
    // Keep the native table and base intact, and place the exact linked
    // payloads above that base within the signed 32-bit displacement range.
    const page = Memory.alloc(Process.pageSize,
      { near: strings.add(0x40000000), maxDistance: 0x3fff0000 });
    const displacement = Number(page.sub(strings).toString());
    if (!Number.isSafeInteger(displacement) || displacement <= 0 || displacement + Process.pageSize > 0x7fffffff)
      throw Error('Anniversary action book allocation outside native offset range');
    const fromHex = text => Uint8Array.from(text.match(/../g), value => parseInt(value, 16));
    const records = new Map();
    let cursor = 0;
    for (const book of actionBooks.values()) {
      const row = page.add(cursor);
      const record = fromHex(book.record_hex);
      if (record.length !== 232 || cursor + record.length > Process.pageSize) throw Error('Anniversary record bounds');
      row.writeByteArray(record.buffer);
      if (row.readU32() !== book.template) throw Error('Anniversary record ID');
      cursor += record.length;
      for (const [field, encoded] of book.links) {
        const payload = fromHex(encoded);
        if (cursor + payload.length > Process.pageSize) throw Error('Anniversary link bounds');
        page.add(cursor).writeByteArray(payload.buffer);
        row.add(field).writeU32(displacement + cursor);
        cursor += payload.length;
      }
      cursor = (cursor + 7) & ~7;
      records.set(book.template, row);
    }
    if (!Memory.protect(page, Process.pageSize, 'r--')) throw Error('Anniversary record protection');
    // Preserve returned pointers even if the native catalog later reloads.
    actionTables.set(key, { page, records });
    send({event:'anniversary_action_item_support', status:'loaded', templates:[...records.keys()]});
    return records.get(id);
  }

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
        this.action = actionBooks.has(this.id);
        this.manager = !disabled && (this.action || allowed.has(this.id)) ? args[0] : null;
      },
      onLeave(row) {
        if (disabled || this.manager === null) return;
        try {
          if (this.action) {
            if (row.isNull()) {
              const record = actionBook(this.manager, this.id);
              if (record !== null) row.replace(record);
            }
          } else if (!row.isNull()) align(this.manager, this.id, row);
        }
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
