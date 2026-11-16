// Keep account scope intact; let the existing server validate ordinary weeklies.
function installElsAccountWeeklyAccept() {
  'use strict';
  if (globalThis.__elsAccountWeeklyAccept) return globalThis.__elsAccountWeeklyAccept;
  const rules = __RULES__, mod = Process.getModuleByName('x2_dx11.exe');
  const emit = (event, extra = {}) => send({event: 'account_weekly_accept_' + event, ...extra});
  const hex = p => Array.from(new Uint8Array(p.readByteArray(16)), b => b.toString(16).padStart(2, '0')).join('');
  for (const [rva, prefix] of Object.entries(rules.prefixes)) {
    if (hex(mod.base.add(Number(rva))) !== prefix) throw Error('Account weekly native prefix mismatch');
  }
  const admitted = new Set(rules.quest_ids);
  // Only the CMP reads this operand. Never clear the real account-scope flag.
  const allow = Memory.alloc(1); allow.writeU8(0);
  let listener = null, disabled = false, reported = false;
  listener = Interceptor.attach(mod.base.add(rules.predicate_rva), function () {
    if (disabled) return;
    const qid = this.context.rbx.toInt32();
    if (!admitted.has(qid)) return;
    try {
      const quest = this.context.rax, engine = mod.base.add(rules.engine_rva).readPointer();
      const node = this.context.rcx;
      if (!engine.equals(this.context.r9) || quest.add(4).readS32() !== qid ||
          node.add(32).readS32() !== qid || !node.add(40).readPointer().equals(quest) ||
          quest.add(rules.account_offset).readU8() !== 1) {
        throw Error('Account weekly native quest identity');
      }
      // RAX is dead after this CMP on the original EE path (3044A4C).
      this.context.rax = allow.sub(rules.account_offset);
      if (!reported) { reported = true; emit('applied', {quest: qid}); }
    } catch (error) {
      disabled = true; listener.detach(); listener = null;
      emit('disabled', {reason: String(error)});
    }
  });
  const support = {stop() {
    disabled = true;
    if (listener) { listener.detach(); listener = null; }
    delete globalThis.__elsAccountWeeklyAccept;
    emit('stopped');
  }};
  globalThis.__elsAccountWeeklyAccept = support;
  emit('ready', {quest_ids: rules.quest_ids});
  return support;
}
