# Prevent starvation behind slow periodic work

The existing scheduler takes ready peers in registration order. When one
asynchronous batch takes longer than the periodic interval, its earlier
cohorts become due again before the next batch finishes. A 64-peer controlled
case with 40 ms work and a 20 ms interval repeatedly dispatches only the first
32 peers; the remaining 32 receive no periodic work in the first eight batches.

Order each ready scan by its original due time, with stable registration order
for equal deadlines. Unserved overdue peers then precede cohorts that have
already completed and received a new deadline. Keep the batch limit of 16,
single worker, operation/reply ownership, per-peer clocks, cancellation,
failure isolation and the existing interval unchanged.

The two slow-worker regressions fail on the exact old module and pass on the
one-line corrected module. Existing full App/TLS and economic regression suites
remain separate from these pure scheduler tests. The source archive changes
one existing runtime leaf, adds no schema or module, and preserves mode-specific
sources and V39. Candidate validation and actual protected dual delivery are
recorded separately; Git source alone does not imply installation.
