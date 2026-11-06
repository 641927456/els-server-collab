# 女王侍者「哨兵」进下一张图就提前死亡

**现象**：艾丽西亚·女王侍者（`unit_type=5`）用哨兵召唤出持续 60 秒的纳斯德侦察兵
协助作战，但 60 秒没到，一进下一张副本地图，侦察兵就自己死了。

**卡点定位**（取证来源：玩家本机最新客户端轨迹
`analysis/client-6c6b5180/20261028-171135/trace.jsonl`）：

- 侦察兵是**服务端**造出来的 actor：客户端发 `0x2CE`，服务端回
  `0x2CF` + `0x2D0`，实例 key 由服务端分配在关卡名册之外
  （`local_session.py` 的 `16 <= key < 16384`，跳过 `run.reserved_keys`）。
- 跨 **stage** 换图时，服务端在 `0xBB` 分支下发缓存的 `0xB2` Population
  报文，同时清空 `summon_keys / summon_deaths / summon_requests` 并把
  `summon_next_key` 重置为 16（`dungeon_flow.py`）。
- 客户端拿 `0xB2` 重建场景后，**0.7–0.9 秒**就把侦察兵 actor 销毁，
  **且不发 `0xAD`**；新名册又把同一个 key 分给了普通怪
  （实测 key 19 → 模板 337）。服务端此时既没有这个召唤物的记录、
  也没有收到任何死亡上报，于是它再也不会重建，玩家只能重新放一次技能
  （轨迹里每个房间确实只有一次新的 384 请求）。
- 5 次「重建即杀」实测存活 22.1 / 26.3 / 27.2 / 27.3 / 42.2 秒，全部远小于 60 秒。
- 只换 **part**（`0xB7/0xBD`，不重建场景）**不会**销毁 actor，所以问题范围只在跨 stage。

**改动**（开关：`els_server/domain/summons.py` 的
`STAGE_SUMMON_PERSISTENCE_ENABLED`，设 `False` 即恢复上游「换图丢召唤物」行为）：

- `els_server/domain/dungeon_routes.py`：`DungeonRun` 增加 run 级
  `summon_payloads / respawn_payloads / summon_key_ceiling`（与既有
  `dynamic_requests` 同一作用域，换 stage 不会被 `_load_stage` 清掉）。
- `els_server/domain/summons.py`：
  `retain_sentry()` 记下原始 `0x2CE` 请求与已发出去的最高实例号；
  `carry_summons()` 在 stage 清空**之前**把还活着的召唤物（`summon_keys`
  有、`summon_deaths` 没有）搬到 `respawn_payloads`；
  `respawn_summons()` 在新房间装载完成后（`0xB3` 分支，`begin_substage` 之后）
  用**新分配的实例 key** 重发 `0x2D0`，其余字节原样回放——模板、阵营、
  等级、朝向、坐标、owner 全部来自玩家当初那次施放。
- `els_server/domain/dungeon_flow.py`：`0xBB` 的 stage 分支在原有清空语句前调
  `carry_summons()`；`0xB3` 的 `substage` 同步分支追加 `respawn_summons()`。
- `els_server/domain/local_session.py`：施放路径把分配到的实例号与请求体留存。

安全边界（全部有测试钉住）：

- **单人房才补**：`dungeon_participants != {自己}` 时一律不接管，多人房维持原生
  各自权威，避免给队友重造 actor。
- **实例号绝不复用**：整个 run 内 `summon_key_ceiling` 单调递增。旧 actor 的
  过期上报（客户端自己的 `sentry=True` 定时退场）可能晚于重建到达，若新召唤物
  顶替旧号，那条 `0xAD` 会把新侦察兵判死。
- **只补活着的**：已经上报过死亡/过期的不复活。
- **80 名额上限照旧**：`occupied_slots() >= 80` 就不补，宁可丢一次召唤也不越界。
- 回放仍走同一个 `sentry_spawn()` 严格解码，owner 绑定、模板白名单
  （`EVE_SUMMON_TEMPLATES`）、字段校验一步不少；`16384` 上界越界即放弃。

**验证**：`tests/test_sentry_stage_persistence.py`（9 项，30302 全流程）：跨 stage
后必发第二条 `0x2D0` 且 key 不在新名册、payload 与「同一请求换 key」逐字节相等；
整图走到 BOSS 房，每次跨 stage 都补、号绝不重复；part 过渡不补也不清；
已判死的不复活；多人不补；满 80 不补；开关关掉恢复上游；
真实 `LocalSession` 施放（临时存档 + 女王侍者）会写入 `run.summon_payloads`。
回归同批跑过 `test_altera_core_boss_gate / test_nasod_factory_exit_gates /
test_mount_flow / test_mount_recall / test_lithia_memory8_offfield_expiry /
test_devildom1_raid2_controllers / test_bait_30282_midboss_death /
test_retained_native_hp / test_settled_run_trailing_death` 等全部涉及召唤物、
可在本机运行的套件（均 OK）。

**未验**：客户端是否接受「没有对应 `0x2CE` 请求」的服务端主动 `0x2D0`——
本机轨迹里每一次 `0x2D0` 都跟在一次施放之后，没有反证，`C50040/1AADAA0`
只做解码建 actor，未见请求配对检查。真机效果待玩家上号验证：若换图后侦察兵
仍在，即成立；若客户端忽略这条报文，需要改走「重建时把召唤物并入 `0xB2`」
的路径（`0xB2` 目前是按 stage 缓存的字节，需要整包重编码，属下一步）。

**另**：本机缺 `analysis/` 抓包产物，`test_summons / test_dungeon_routes /
test_dungeon_lifecycle / test_dungeon_spawns / test_dungeon_rewards /
test_dungeon_return / test_challenge_flow / test_complex_dungeon_routes /
test_ground_loot` 仍在 import 期 `FileNotFoundError`；
`test_friends_server` 缺 `cryptography`；
`test_scene_actor_native_expiry`（NS 假 run 无 `graph`）、
`test_tunnel_native_retirements`（假 catalog 无 `static_npc_level`）、
`test_dungeon_session`（`_capture_luciel_dungeon_hp` 拿到 `None` 角色）、
`test_companions`（回执计数）是与本次无关的既有失败，未追查。
