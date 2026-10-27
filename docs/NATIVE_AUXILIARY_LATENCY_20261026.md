# Potion, equipment and scene request backlog

The fixed DX11 client emits an unconsumed nine-byte `7D0` notification five times
per second. Running every notification through complete business projections
queues potion use, equipment changes and scene continuation behind that work.
The authenticated current actor now drains pending mailbox messages directly
for that exact auxiliary envelope in the ready-town and active-dungeon phases.
Transport framing, sequence checks, online clocks and independent periodic
consumers continue to run. Other envelopes retain ordinary admission.

The town-ready Lu/Ciel type check uses the existing identity projection. Typed
`58C/58D` diagnostics record the native envelope and rejection reason. This
change does not change teleport fees, entitlement or successful entry handling.

On the same formal parent, a controlled burst of 64 notifications reduced
equipment response time from 2986 to 530 ms, potion response from 2210 to 496 ms,
and scene progression from 2111 to 538 ms. The real private TLS flow verified
the same equipment UID, one potion debit with its native effect, actual stage
advance, disabled-account rejection and surviving periodic consumers.

The independent online release `potion-transition-latency-20261026-v1` completed
120 seconds of protected observation and public owned-account QA, including
cold inventory reads, exact account cleanup and registration-capacity checks.
The separate local promotion was refused by the original running-game guard.
Natural player GUI timing and the later paid-teleport disconnect repair are
separate acceptance scopes. No client files or player/account database restore
are part of this source change. This PR alone performs no service deployment.
