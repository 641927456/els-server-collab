# Reject ordinary death reports for Lithia memory2 story dummy

For these exact current static scene actors, ordinary AD flags 0/1 previously fell through to generic combat admission. Their source-pinned DYING_END path uses flag255. Set `requires_native_255=True` only on the existing rows below, so ordinary combat cannot consume them while the existing original255 receipt path remains available.

| Dungeon | Stage | Part | Template | Source index | Original script |
| --- | --- | --- | --- | --- | --- |
| 35260 | 0 | 0 | 9319 | 12 | `LITHIA_MEMORY2_STORY_DUMMY.lua` |

Dependency: [Issue175](https://github.com/641927456/els-server-collab/issues/175), which provides the shared strict255 consumer and resource-free `fixture(rule, unit, quest)`. Preparation baseline is `3ca90dbc2633275eadb7f6b87cfa75528b66ab92` plus the pending175 controller `4948a1a0a2225256c9da7de830faecec1b6baa5f75f968da60f29400aa7b832f`. Rebase on its committed result before a branch or PR is created. No client, graph, script, task, HP, clock, gate, reward or DB-schema change is included.

Source qualification: immutable source-freeze SHA256 `b06f6fc592b9c4be8f1802c3b436c185dca1f2f09dcb1166f9883305f3644a54`; donor-controller SHA256 `88a88fa79426a2ba27d78fa99291a65957d0a9623bf2f1f4794dc3baa0ab4a41`. Only the listed row flags are ported; the full donor contains unrelated later work and must not replace main. Existing graph/script SHA pins, current stage, exact instance/source, unit, earned task and writer/receipt checks remain unchanged.

Resource-free verification: `python -m unittest discover -s tests -p test_lithia_native255_guard.py -v`. The Issue175 fixture supplies a small in-memory session and SQLite callback witness model, then this test parameterizes the target dungeon/stage/part. Cases cover original255 ACK+notice, same-payload ACK-only replay, changed replay, ordinary0/1 rejection, unrelated-actor fallthrough, wrong source/owner/quest/HP/unit/lease, and callback-failure memory preservation. This does not reproduce full storage atomicity or run an actual Application/TLS connection.

The production batch is pending installation when this issue is prepared. This source port, unit checks and later Git merge do not assert deployment, natural AI/wave timing, a complete player route, or multiplayer acceptance. Previously frozen private runtime evidence remains separate and is not copied into Git. No production logs, player DBs, raw packets, client resources, credentials or private paths belong in the commit.


本次Git移植基于已提交的 #175（`4cb8ef441f931d169ef3aebdb183daea029f0884`，PR #200），仅含本项独立差异。对应运行修复已随 `tasks-dungeons-native-continuations-20261021-v12` 在线上及独立本地完成备份、安装和120秒观察；公网核验限正常建角与未获资格请求拒绝，正向退场和事务仍引用本地受控证据。未宣称完整自然或多人验收。本PR等待维护者审查，不自动合并或部署。
