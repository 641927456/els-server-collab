# Deterministic scheduler deadline cohorts

The first full main runtime workflow after integrating PRs 552, 554, 571, 570,
574, 577, 579, 581 and 586 exposed a scheduler-test timing assumption. Creating
64 peers assigns 64 different real deadlines. On a loaded Windows runner,
only 58 were due in the first four batches; the final six were correctly
deferred. The test incorrectly required all 64 to share a deadline.

Hold the peers' operation locks until all registrations are complete, assign
one common due time, then release them. Keep the original four-batch coverage,
batch-size, maximum-batch and fairness assertions. Add a separate 58/6 staged
deadline regression that checks partial batches, refusal to process future
peers early, and eventual delivery to the late peers.

Only the test fixture changes. The scheduler, batch limit, timing interval,
single writer, economic rules, accepted runtime selector and formal files
remain unchanged. The original failed main job is retained as evidence;
neither retries nor removed assertions are used to conceal it.
