'use strict';
// Only STR_ID_350's verified producer. Original resources and timer stay native.
const module = Process.getModuleByName('x2_dx11.exe');
const base = module.base;
const gate = base.add(0x74b39a);
const reset = base.add(0x74b5c7);
const chat = base.add(0x122edf0);
const noticeReturn = base.add(0x74b507);
let policy = __INITIAL_POLICY__;
const enabledFlag = Memory.alloc(1);

function configure(value) {
    if (typeof value.enabled !== 'boolean' || typeof value.text !== 'string' ||
        typeof value.revision !== 'string' || !value.text.trim() || value.text.length > 280)
        throw new Error('Invalid authenticated client notice policy');
    policy = value;
    enabledFlag.writeU8(value.enabled ? 1 : 0);
    send({event: 'client_notice_policy_applied', revision: value.revision, enabled: value.enabled});
    return value.revision;
}

function check(rva, expected) {
    const bytes = new Uint8Array(base.add(rva).readByteArray(expected.length / 2));
    const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    if (actual !== expected) throw new Error('Client notice native prefix mismatch at ' + rva.toString(16));
}

check(0x74b39a, '48833dbeca0c0400');
check(0x74b5c7, 'ff1523ea7503418987500b0000');
check(0x74b502, 'e8e938ae00');
check(0x122edf0, '40555356574154415541564157488d6c');
configure(policy);

// A native conditional branch preserves registers/flags and skips before any
// temporary objects exist. Interceptor's callback PC is not a branch primitive.
const trampoline = Memory.alloc(Process.pageSize, {near: gate, maxDistance: 0x7ffff000});
function int32(value) { const n = value | 0; return [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]; }
function addressBytes(pointer) {
    const bytes = Memory.alloc(8); bytes.writePointer(pointer);
    return Array.from(new Uint8Array(bytes.readByteArray(8)));
}
function relative(from, to) {
    const difference = to.sub(from).toInt32();
    if (!from.add(difference).equals(to)) throw new Error('Client notice branch out of range');
    return int32(difference);
}
const code = [0x50, 0x48, 0xb8, ...addressBytes(enabledFlag), 0x80, 0x38, 0, 0x58, 0x0f, 0x84];
code.push(...relative(trampoline.add(code.length + 4), reset));
code.push(0x50, 0x48, 0xb8, ...addressBytes(base.add(0x4817e60)), 0x48, 0x83, 0x38, 0, 0x58, 0xe9);
code.push(...relative(trampoline.add(code.length + 4), gate.add(8)));
Memory.patchCode(trampoline, code.length, pointer => pointer.writeByteArray(code));
const branch = [0xe9, ...relative(gate.add(5), trampoline), 0x90, 0x90, 0x90];

const chatListener = Interceptor.attach(chat, {
    onEnter(args) {
        if (!this.returnAddress.equals(noticeReturn)) return;
        // Keep the allocation on this native invocation until AddChatLog has
        // copied it. Other system messages, players and resource users pass through.
        this.noticeText = Memory.allocUtf16String(policy.text);
        args[1] = this.noticeText;
    },
    onLeave() { this.noticeText = null; }
});

// Keep native allocations alive if a controller disconnects unexpectedly.
// The shared launch owner ends the owned process before detaching.
// No live-unload RPC: another native thread could still be in the trampoline.
Script.pin();
try { Memory.patchCode(gate, branch.length, pointer => pointer.writeByteArray(branch)); }
catch (error) { chatListener.detach(); Script.unpin(); throw error; }
rpc.exports = {configure};
send({event: 'client_notice_ready', text_id: 350, interval_seconds: 3600});
