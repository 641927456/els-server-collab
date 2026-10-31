const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const base = __dirname;
const parent = process.argv[2] || path.join(base, 'source/parents/friends/trace_dx11_login.js');

function replay(file, interactive, ready = true, reconnect = false) {
  const source = fs.readFileSync(file, 'utf8');
  const start = source.indexOf('  if(enterTown){');
  const end = source.indexOf('  if(enterDungeon', start);
  assert(start >= 0 && end > start);
  const callbacks = new Map(), calls = [];
  class Pointer {
    constructor(n) { this.n = n; }
    add(n) { return new Pointer(this.n + n); }
    sub(p) { return new Pointer(this.n - p.n); }
    toInt32() { return this.n; }
    toString() { return `0x${this.n.toString(16)}`; }
    equals(p) { return this.n === p.n; }
    isNull() { return false; }
    readS32() { return 0; }
    readU64() { return 1007n; }
    readPointer() {
      if (this.n === 1000) return new Pointer(0x41dcee0);
      if (this.n === 1000 + 0x420) return new Pointer(100000 + 0x8b);
      if (this.n === 1000 + 0x418) return new Pointer(100000);
      return new Pointer(200000);
    }
  }
  const context = vm.createContext({
    enterTown: true, lightweightPlay: interactive,
    game: {base: new Pointer(0)}, Date: {now: () => 30000},
    lastCharacterFrame: 0, characterReady: ready ? 1 : 0,
    channelsReady: ready ? 1 : 0, selected: false, chosen: false,
    loadedCharacter: true, selectedCharacterUid: null, note() {},
    Interceptor: {attach(p, c) { callbacks.set(p.n, c); }},
    nativeCall(rva) { return () => calls.push({rva, phase: reconnect ? 'game_connected' : 'characters_ready'}); }
  });
  vm.runInContext(source.slice(start, end), context);
  const frame = callbacks.get(0x137ad80);
  for (let i = 0; i < 3; ++i) {
    const scope = {};
    frame.onEnter.call(scope, [new Pointer(1000)]);
    frame.onLeave.call(scope);
  }
  return calls;
}

const candidate = process.argv[3] || path.join(base, 'source/friends/tools/trace_dx11_login.js');
const before = replay(parent, true, true, true);
assert.deepEqual(before.map(x => x.rva), [0x13a0f90, 0x13aeb90]);
assert.equal(replay(candidate, true, true, true).length, 0);
assert.equal(replay(candidate, true, true, false).length, 0);
assert.equal(replay(candidate, true, false, false).length, 0);
assert.deepEqual(replay(candidate, false).map(x => x.rva), [0x13a0f90, 0x13aeb90]);
const result = {passed: true, oldInteractiveReconnectionCalls: before,
  interactiveSelectionCalls: 0, interactiveReconnectCalls: 0,
  isolatedProbeCallsRetained: 2, gameProcessAccess: false};
if (process.argv[4]) fs.writeFileSync(process.argv[4], JSON.stringify(result, null, 2));
console.log(JSON.stringify(result));
