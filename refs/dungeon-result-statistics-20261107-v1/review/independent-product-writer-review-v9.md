# Actual product shared writer: independent review

The fixture now reads the exact candidate `tools/pvp_hp_source.js` prefix up to `installElsPvpHpSource`, inserts it unchanged into a lexical wrapper, and calls its real `prepareElsReportWriter`. Only that wrapper's Process.getModuleByName('x2_dx11.exe') supplies a private fake base mapping DA2F50 to an allocated native writer; all other Process APIs come directly from the real Process object. Memory protection, NativeFunction/Callback, Interceptor.replaceFast, native caller code, and listener-guard behavior are actual Frida17.23.3. No helper implementation is transcribed in the fixture.

## Core mechanism passed

`independent-product-writer-v9.js/json` verifies original-first encoding with real writer bytes; PVE1 appears inside a listener guard while the sender observer count remains0. The normal report path observes the sender once and appends PVP1. Original failure0 remains0 without an extension; a different caller appends nothing. Removing dungeon preserves PvP, removing PvP preserves dungeon, and the captured original pin/singleton remain available after the fast entry is installed. Helper38108 exited0 after detach/unload with no Frida error, game process, other process attachment, physical input, or game-lock operation.

The initial fixture attempt to assign real Process.getModuleByName was rejected because it is read-only. The corrected fixture uses Object.create(realProcess) with exactly that one own method shadowed, bound as the helper's lexical Process parameter. The actual product helper source remains unchanged.

Product prefix SHA-256 at this review:`78ffb395e8a98e13d3eabde5a572b654e62554af80bc42f7a63887a2dfe9af9f`; full product file SHA-256:`81be44459e956667f69c9dd97dd50422a5b6bdbb6147e8b47e861cc5195671e0`.

## Confirmed lifecycle defect

The returned unregister closure is `()=>consumers.delete(name)`. After unregistering an old pvp registration and registering a new one, invoking the old unregister again deletes the new registration. The actual native fixture observes base byte only instead of PVP1, so its overall result is deliberately passed=false despite all core encoding checks passing.

This has a concrete caller: the current PvP controller's dispose is not idempotent. Disposing an old controller again after a new PvP controller has installed calls that old remover again; its singleton identity check preserves the new controller object, but the new writer consumer is silently gone. Dungeon's active guard avoids the equivalent repeated dispose on that controller.

Make each remover a one-use registration token, or otherwise bind removal to a distinct registration identity. A mere append-function equality check does not distinguish two registrations that intentionally reuse the same function. The fixture tests that reuse explicitly. No business source was changed by this reviewer.

## Actual consumer review and remaining boundaries

PVE preserves the committed source-map observation logic and now manually binds its sender scope before the guarded original report call, restoring the previous value in finally. It retains the original generic network attach and does not replace682D80. Its own dispose removes only the dungeon consumer. The shared fast writer/trampoline/allocation remain owned by the prepared helper independently of either mode.

PvP keeps its original sender attach, mode/actor/UID identity, current/max/reported HP checks, native maximum getter, disable behavior and diagnostic event. Its old DA2F50 attach has become the registered append function. Both old writer attaches are absent, and the code uses replaceFast's returned original trampoline. The coordinator checks original bool1 and original C690A1 caller before appending.

The author's ten combined fixtures, including actual-mode consumer selection and standalone PvP reload, are reused; they were read but not rerun. The new actual-helper fixture supplies its own mode-selecting append callbacks, so it establishes helper registration/guard mechanics rather than natural HP or CD production. The actual game installation, natural PVE1/PVP1 reports, multiplayer CD and result UI remain separate acceptance evidence. The blocked v15 game start is not treated as a pass or failure of this shared writer.
