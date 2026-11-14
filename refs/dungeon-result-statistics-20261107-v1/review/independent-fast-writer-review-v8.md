# Shared fast report serializer: independent mechanism review

The proposed boundary keeps the previously working generic network listener and replaces only the verified two-pointer, bool-returning DA2F50 serializer. This review does not authorize or claim another generic682D80 replacement. Its real-game failures are not explained by a successful small fixture.

The x64 fast-entry stub `mov r8,[rsp]; jmp [rip+0]` followed by the callback pointer preserves RCX/RDX/RSP and supplies the original native caller address as the third integer-register argument. A `uint8(pointer,pointer,pointer)` callback is compatible with the original caller's Win64 alignment and32-byte shadow space. It must invoke the pointer returned by replaceFast as the original `uint8(pointer,pointer)` writer. Calling DA2F50 again would recurse into the fast replacement. Appending is conditional on original low-byte success1 and original C690A1 callsite, with each mode's native owner checks retained.

The [official17.23.3 interceptor implementation](https://raw.githubusercontent.com/frida/frida-gum/17.23.3/gum/guminterceptor.c) specifies that fast replacement directly branches to its replacement and cannot coexist with attach on the target. Therefore both old DA2F50 writer listeners must move into this shared serializer; QA must not add an entry listener there. The original sender listeners may remain. Explicit PVE bound push/restore around the existing generic listener's original report call is necessary because that sender listener remains suppressed by the listener guard.

`independent-fast-writer-guard-v8.js/json` is a new actual-Frida17.23.3 test in a newly owned hidden Python helper. It executes private original x64 writer/report functions, with the writer fast-replaced by this three-argument stub. The test establishes:

- From an outer Interceptor onEnter, NativeFunction(report) still suppresses the sender observer (count0), but the fast writer callback executes and appends only PVE1 after original success.
- A normal report outside that listener invokes its sender observer and appends only PVP1 through the same fast writer.
- Original failure0 remains0 and appends nothing.
- A different native caller receives no extension, despite an otherwise present PVE context. The stub's captured caller equals the precise native call return address for the permitted report.

The original writer emits a base byte before the extension, proving original-first order rather than a replacement-only mock. The helper59204 detached/unloaded and exited0, with no Frida error, game process, player process attachment, or physical input. An initial six-byte test function was refused by fast relocation; that invalid fixture was corrected to have16 leading NOPs. This is not evidence about installation failure of the actual DA2F50 prologue. The final fixture exercises the real fast API and default traps, not a hand-dispatched hook mock.

Necessary implementation boundaries:

1. The shared serializer must own its fast hook, returned original trampoline, stub allocation and NativeCallback independently of either mode's controller. PVE dispose unregisters its append function and sender context; it must not remove a writer still needed by PvP. Retain code/callback/trampoline for the shared installation's lifetime, and do not revert while an invocation may still use that trampoline.
2. Preserve the existing PvP sender scoping, HP/max/reported checks, disable behavior, and lifecycle. Removing its writer attach is not permission to remove those checks. Keep the PVE context scoped by thread and original Game generation; an old bound must not leak after the report returns or fails.
3. The shared caller must append at most the one matching extension. Existing parser contracts accept one trailing extension, not PVP1 and PVE1 together. Tests of the actual registered append functions must establish the mode/ownership separation; this fixture only establishes the mechanism.
4. Return original failure unchanged and do not append after it. Define append failure behavior so a partially written extension is not reported as a valid completed serializer result; the original bool contract is available to signal failure. No new chance, cap, contribution score or reward formula is needed.
5. Capture the original callsite in the native stub before FFI entry; a callback's own return address is not a substitute. The fast stub intentionally uses volatile R8 to add its third argument. It is a narrow typed serializer adapter, not a claim to preserve all CPU state of an arbitrary function.

The actual new shared module and its installed native game path have not yet been reviewed/run at the time of this note. Reuse the passed unchanged payload parser/result-reader tests; validate the changed registration/lifecycle and actual native PVE/PvP extension writes when implementation is available. No product source was changed by this reviewer.
