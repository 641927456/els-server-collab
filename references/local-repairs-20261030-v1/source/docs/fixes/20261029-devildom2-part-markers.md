# 尼格摩尔(Devildom2 34340/34350/34360) 打完图不开门

**现象**：尼格摩尔地区（Devildom2）的 34340 `Dungeon_Devildom2_Residence`、
34350 `Dungeon_Devildom2_Factory`、34360 `Dungeon_Devildom2_Portal` 走到出口换不了图；
部分房间连传送门都不亮，最后只能退图。

**卡点定位**：这些房间的 `kind==3` 出口条件 `required` 指的不是怪，而是
`npcs.json` 里 `class_id=103 / IS_NPC=true` 的脚本标记（`*_START` / `*_CLEAR` /
`*_END`）。客户端在自己的场景里销毁标记，服务端收不到任何 0xad 死亡上报，
`run.defeated` 永远不含它，`condition_ready(kind==3)` 永远为假，`poll_ready()`
不成立，`periodic()` 不置 `part_end_notified`，客户端的 0xbb 换图请求被丢弃。
既有的 `script_gate_relaxation` 也救不了：它要求房间「至少有一个激活敌对目标且
全部死亡」，而这些房间根本没有可打的怪。

运行时证据（会话 `analysis/client-6c6b5180/20261029-215610`）：34340 stage0 part1
在 2759.09 装载，房间唯一 actor 是 7587；客户端随后自行销毁它，没有任何 0xad 上报；
玩家 2764.10 发 0xb8，服务端回 `b9 result=-1`；2801 玩家退图。

**逐房间清单**（全部按 source 钉死）：

| 副本 | stage/part | 条件 required | 标记 | 同房真实战斗目标 |
| --- | --- | --- | --- | --- |
| 34340 Residence | 0/1 | 7587 | `DEVILDOM2_RESIDENCE_STAGE1_START.lua`，`active=false`，房间唯一 actor | 无 |
| 34350 Factory | 0/0 | 7568 | `DEVILDOM2_FACTORY_STAGE0_CLEAR.lua` | 无 |
| 34350 Factory | 1/0 | 7570 | `DEVILDOM2_FACTORY_STAGE1_DUMMY.lua` + `DEVILDOM2_FACTORY_BOSS_EVENT.lua`(7553) | BOSS 7551（仍必须打死） |
| 34360 Portal | 0/0 | 7593 | 条件本身是 BOSS 7593，只有 `_STAGE0_END`(7603) 需要放行 | BOSS 7593（仍必须打死） |
| 34360 Portal | 1/0 | 7605 | `DEVILDOM2_PORTAL_STAGE1_END.lua` | 14 个 class0 杂兵（仍必须全清） |
| 34360 Portal | 2/0 | 7607 | `DEVILDOM2_PORTAL_STAGE2_END.lua` | BOSS 7601（仍必须打死） |

34360 stage0 part0 是形状外延：它的 `kind==3` 条件要求的是真 BOSS 7593，但同房间
还声明了 `active=true / no_drop=true` 的 7603，BOSS 死后 0xb8 的「激活敌对目标
全死」校验仍会因它回 -1。该房间只放行标记 7603，7593 的 kind-3 要求原样保留。

**改动**：

- `els_server/domain/local_dungeon_flow.py`：新增开关 `part_marker_relaxation`、
  `PART_MARKERS`（6 行，按 (identity, stage, part) 钉死）、`part_marker()` /
  `part_marker_npc()` / `part_marker_gate()`。每行核对：条件 `required` 与该行
  完全一致、整行 source（template、source_index、points、team、no_drop、gage…）、
  图谱 `source_sha256`、脚本在路由清单里的 sha、原生 `class_id=103` 且
  `IS_NPC=true`；同房间其他活着的 actor 仍必须全部击杀。
- `els_server/domain/dungeon_routes.py`：kind==3 在 `script_gate` 之后再试
  `part_marker_gate`；战斗型 required 的分支原样不变。
- `els_server/domain/dungeon_flow.py`：0xb8 的「激活敌对目标全死」循环对已钉死的
  标记不再否决（客户端自己来要出口即其场景已结束）。
- `config/local_dungeon_flow.json`：新增 `part_marker_relaxation: true` 与
  `note_part_markers`（取证与放行范围）。设 false 即恢复上游行为。

34320 `Dungeon_Devildom2_Henir` 不受影响：它的 7523/7524/7513 已有
`story_controller_retirements` / `friends_story_retirements` 静态退场消费者；
20261029-215610 的 34320 stage0 是「打了 13 个怪后自己退图」，没有过门请求被拒的
证据。34330 `Dungeon_Devildom2_Tunnel` 同理，房间出口是真怪。

**验证**：`tests/test_devildom2_part_markers.py`（14 项）：6 行钉死值与图谱逐字段
一致、运行时名单确实声明这些标记、34340 无死亡上报也能过闸并 0xb8 回 0、0xbb 装载
下一关、34350 stage0 进房即满足、34350 stage1 的 BOSS 7551 仍严格、34360 stage1
的 14 个杂兵仍须全清、34360 stage2 的 BOSS 7601 仍严格、34360 stage0 只放行 7603
而 7593 仍严格、错 source 点被拒、未钉死房间不放行、同房活怪阻断、开关关掉恢复
卡死。原有 `test_altera_core_boss_gate` / `test_nasod_factory_exit_gates` /
`test_lithia_memory8_finale_door` 不变通过。

**未验**：34350 / 34360 没有本机通关抓包，仅有图谱 + 原生 class 证据（34340 有完整
运行时证据）。真机自然流程待玩家上号验证；若某间仍卡住，需要该次会话的
`analysis/client-*/<ts>/` 轨迹来确认是否还有别的未钉死标记。
