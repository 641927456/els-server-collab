// Route the registered ERP unlock books through the native ordinary use request.
function installElsResonanceBookUse() {
 const client = Process.mainModule;
 if (client.name.toLowerCase() !== 'x2_dx11.exe' || !client.base.equals(game.base))
  throw Error('ERP book use requires the pinned main module');
 if (globalThis.elsResonanceBookUse) return;

 const base = client.base, pins = __ERP_BOOK_USE_PINS__;
 for (const [rva, expected] of Object.entries(pins)) {
  const bytes = new Uint8Array(base.add(Number(rva)).readByteArray(expected.length / 2));
  const actual = Array.from(bytes, x => x.toString(16).padStart(2, '0')).join('');
  if (actual !== expected) throw Error('ERP book use native bytes: ' + rva);
 }
 const call = (rva, result, args) => new NativeFunction(base.add(rva), result, args,
  {exceptions:'propagate', traps:'all'});
 const inventoryArgs = ['pointer','uint64','int'];
 const original = call(0x220ebd0, 'uint8', inventoryArgs);
 const currentActor = call(0x7eea50, 'pointer', ['pointer']);
 const findItem = call(0x197f500, 'pointer', ['pointer','uint64','uint8']);
 const itemGroup = call(0x197f660, 'int', ['pointer','uint64']);
 const makeText = call(0x152210, 'pointer', ['pointer','pointer']);
 const useItem = call(0x2260fd0, 'uint8', ['pointer','uint64','uint64','int','uint8','pointer']);
 const books = new Set([163561, 163562, 300891]);
 const replacement = new NativeCallback((controller, uid, slot) => {
  const handled = original(controller, uid, slot);
  if (handled) return handled;
  const engine = base.add(0x4817e70).readPointer(), app = base.add(0x4817e80).readPointer();
  if (engine.isNull() || app.isNull() || app.add(0x160).readS32() !== 14) return handled;
  const menu = engine.add(0x558).readPointer(), actor = currentActor(engine);
  if (menu.isNull() || !menu.add(0x18).readPointer().equals(controller) || actor.isNull() ||
      engine.add(0xc0).readPointer().isNull()) return handled;
  const bag = actor.add(0x440), item = findItem(bag, uid, 0);
  if (item.isNull() || !books.has(item.add(8).readU32()) ||
      item.add(0x310).readPointer().isNull() || itemGroup(bag, uid) !== 4) return handled;

  const text = Memory.alloc(32);
  return useItem(controller, uid, 0, 0, 0, makeText(text, base.add(0x3fa02d0)));
 }, 'uint8', inventoryArgs);
 Interceptor.replace(base.add(0x220ebd0), replacement);
 globalThis.elsResonanceBookUse = replacement;
 note({event: 'resonance_book_inventory_use_ready'});
}
