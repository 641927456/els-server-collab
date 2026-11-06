// The original state render methods still run, including UI queue preparation.
// Only draw submissions within these two startup state types are suppressed.
let elsStartupVisibility = null;
function elsStartupVisibilityReady() {
  // The executable unpacks code before populating these tables. The first
  // observed gap was 109 ms; use native readiness rather than a fixed delay.
  return [
    [0x42e9ba0, 0xb76c20], [0x42e9ba8, 0xb76c60],
    [0x42e9bb0, 0x133daf0],
    [0x42ea0d0, 0x30f2050], [0x42ea0d8, 0x30f2090],
    [0x42ea0e0, 0x30f20c0],
  ].every(([slot, rva]) => game.base.add(slot).readPointer().equals(game.base.add(rva)));
}
function finishElsStartupVisibility(reason) {
  if (elsStartupVisibility !== null) elsStartupVisibility.finish(reason);
}
function installElsStartupVisibility() {
  if (elsStartupVisibility !== null) throw new Error('Startup visibility installed twice');
  // Dialog entry 74ecd0 is already observed by the parent startup. Verify its
  // unchanged code at +32, outside that observer's patched prologue.
  const pins = __STARTUP_UI_PINS__;
  for (const [rva, hex] of Object.entries(pins)) {
    const actual = Array.from(new Uint8Array(game.base.add(+rva).readByteArray(hex.length / 2)),
      x => x.toString(16).padStart(2, '0')).join('');
    if (actual !== hex) throw new Error('Startup visibility native contract: ' + rva);
  }
  for (const [table, entries] of [
    [0x42e9b90, [[0x10, 0xb76c20], [0x18, 0xb76c60], [0x20, 0x133daf0]]],
    [0x42ea0c0, [[0x10, 0x30f2050], [0x18, 0x30f2090], [0x20, 0x30f20c0]]],
  ]) {
    for (const [slot, rva] of entries) {
      const actual = game.base.add(table + slot).readPointer(), expected = game.base.add(rva);
      if (!actual.equals(expected))
        throw new Error('Startup visibility state vtable contract: table=' + table.toString(16) +
          ' slot=' + slot.toString(16) + ' actual=' + actual + ' expected=' + expected);
    }
  }
  const scopes = new Map(), listeners = [], replacements = [], callbacks = [];
  const counts = {loading: 0, login: 0, draws: 0};
  let finished = false;
  const stateTables = [game.base.add(0x42e9b90), game.base.add(0x42ea0c0)];
  function finish(reason) {
    if (finished) return;
    finished = true;
    for (const listener of listeners) listener.detach();
    for (const target of replacements) Interceptor.revert(target);
    Interceptor.flush();
    scopes.clear();
    note({event: 'startup_ui_visibility_finished', reason, ...counts});
  }
  elsStartupVisibility = {finish, callbacks};
  try {
    for (const rva of [0xb76c20, 0xb76c60, 0x133daf0, 0x30f2050, 0x30f2090, 0x30f20c0]) {
      listeners.push(Interceptor.attach(game.base.add(rva), {
        onEnter(args) {
          const table = args[0].readPointer();
          const kind = stateTables.findIndex(value => value.equals(table));
          this.startupScope = kind !== -1;
          if (!this.startupScope) return;
          scopes.set(this.threadId, (scopes.get(this.threadId) || 0) + 1);
          const key = kind === 0 ? 'login' : 'loading';
          if (counts[key]++ === 0)
            note({event: 'startup_ui_render_scope_entered', page: key});
        },
        onLeave() {
          if (!this.startupScope || finished) return;
          const depth = scopes.get(this.threadId) - 1;
          if (depth === 0) scopes.delete(this.threadId);
          else scopes.set(this.threadId, depth);
        },
      }));
    }
    for (const rva of [0x454200, 0x4542b0, 0x454330, 0x4546c0]) {
      const target = game.base.add(rva);
      const args = rva === 0x4546c0 ? ['pointer', 'uint8'] : ['pointer'];
      const original = new NativeFunction(target, 'void', args);
      const callback = new NativeCallback(function (manager, mode) {
        if (!finished && (scopes.get(Process.getCurrentThreadId()) || 0) > 0) {
          counts.draws++;
          return;
        }
        if (rva === 0x4546c0) original(manager, mode);
        else original(manager);
      }, 'void', args);
      callbacks.push(callback);
      Interceptor.replace(target, callback);
      replacements.push(target);
    }
    // Native error/info prompts must be drawable even before the roster arrives.
    listeners.push(Interceptor.attach(game.base.add(0x74ecd0), {
      onEnter() { finish('native-dialog'); },
    }));
    Interceptor.flush();
    note({event: 'startup_ui_visibility_ready', native_updates_retained: true,
      render_preparation_retained: true, sites: pins});
  } catch (error) {
    finish('installation-failed');
    throw error;
  }
}
