"""Restore the server's refused pet-use wait in the existing native slot gate."""

SOURCE = r"""
function installElsPetAutoCooldownWait() {
  'use strict';
  if (globalThis.__elsPetAutoCooldownWait) return globalThis.__elsPetAutoCooldownWait;
  const game = Process.getModuleByName('x2_dx11.exe');
  const address = game.base.add(0x30567fb);
  const expected = '41c6852a010000004180bd5101000000';
  const actual = Array.from(new Uint8Array(address.readByteArray(16)),
    value => value.toString(16).padStart(2, '0')).join('');
  if (actual !== expected) throw new Error('Pet cooldown wait native contract mismatch');
  let listener = Interceptor.attach(address, {
    onEnter() {
      try {
        const frame = this.context.rbp;
        if (this.context.rsp.add(0x68).readU64().toString() !== '1631' ||
            frame.add(0x30).readS32() !== 1369) return;
        const seconds = frame.add(0x441).readFloat();
        const slot = frame.add(0x445).readU16();
        // The original item CD is u8 seconds; extra slot intervals are 0..300.
        // Old servers send -1, so they retain the original rejection behavior.
        if (slot > 1 || !Number.isFinite(seconds) || seconds <= 0 || seconds > 300) return;
        const manager = game.base.add(0x4817e70).readPointer();
        if (manager.isNull()) return;
        const inventory = manager.add(0x558).readPointer();
        if (inventory.isNull() || !inventory.add(0x58).readPointer().equals(this.context.r13) ||
            this.context.r13.add(0x12a).readU8() !== 1) return;
        const pet = manager.add(0x5e8).readPointer();
        if (pet.isNull()) return;
        const timer = pet.add(0x548 + slot * 4);
        const before = timer.readFloat();
        if (!Number.isFinite(before) || before < 0) throw new Error('Invalid native pet wait');
        const remaining = Math.max(before, Math.ceil(seconds));
        timer.writeFloat(remaining);
        send({event:'pet_auto_cooldown_wait_synced',slot,remaining,
          result:1369,source:'server_rejection',original_pending_clear:true});
      } catch (error) {
        listener.detach();
        send({event:'pet_auto_cooldown_wait_disabled',reason:String(error)});
      }
    }
  });
  globalThis.__elsPetAutoCooldownWait = listener;
  send({event:'pet_auto_cooldown_wait_ready',rva:'0x30567fb'});
  return listener;
}
"""


def compose(template):
    anchor='  clearInterval(timer);'
    if template.count(anchor)!=1:raise ValueError('Pet cooldown wait startup anchor')
    return SOURCE+'\n'+template.replace(anchor,
        anchor+'\n  try { installElsPetAutoCooldownWait(); } catch (error) {\n'
        "    send({event:'pet_auto_cooldown_wait_disabled',reason:String(error)});\n  }")
