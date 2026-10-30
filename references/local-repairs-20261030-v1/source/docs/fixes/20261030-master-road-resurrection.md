# 大师之路（Dungeon_Md_*）里按 Z 复活失败、「复活石用不了」

**现象**：在罗索（34390，`Dungeon_Md_ROSSO_Normal`）里被打死，客户端照常弹出
「复活请按 Z 键（消耗 1 个复生石）」，按 Z 后只弹一个空白对话框（确认），
角色不复活、复活石数量也不扣。

**证据**（`analysis/client-6c6b5180/20261030-013523/server-logs/server.jsonl`）：

| 时间 | 客户端请求 | 服务端回应 | 说明 |
| --- | --- | --- | --- |
| 17:41:40 / 17:49:09 | 0xa7 死亡请求 | 0xa8 | 回的是拒绝（`death_ack(-1)`），没有进入 dying |
| 17:41:44 / 17:49:13 | 0xaa 死亡完成 | 无回应 | 只有 dying 状态才回 0xac；说明 0xa7 已被拒 |
| 17:41:46 / 17:41:48 / 17:41:54 / 17:49:16 / 17:49:17 / 17:50:04 | 0x160 用复活石 | 0x161 | 没有配 0x162（续命），即返回失败码 |

**根因**：`known_resurrection_maps.qualified()` 的白名单
（`els_server/data/known_resurrection_maps.json`）只有 `30000 / 30072 / 30092`
三张图。16 张 `Dungeon_Md_*` 不在表里，`qualified()` 直接抛
`Resurrection scene source not qualified`，此后 0xa7 回 `death_ack(-1)`、
0x160 回 `use_ack(...,-1)`，客户端就只显示失败对话框。复活石本身没问题：
只读查库 `state/development.sqlite3` 的 `known_resurrection_stones`，
该角色还有 130 个。

**改动**：

- `els_server/data/known_resurrection_maps.json`：加入 16 张
  `Dungeon_Md_*`（34370–34700）。每张图单关卡单分部，因此
  `stages: {"0": {parts:[0], keys:[], native_solo_selector:true}}`——
  沿用既有的「solo 用客户端原生 -1 选点」通道，不新增选点证据。
  现有 3 张图的条目一字未动。
- 每张图的 `definition_sha256` 是 `client_data().dungeon(id)` 规范化 JSON 的 sha256，
  `graph_source_sha256` 取自 `dungeon_routes.json` 对应 graph 的 `source_sha256`；
  两处都会在 `qualified()` 里逐步复核，客户端/路线数据一变就会重新拒绝。
- `els_server/data/known_resurrection_maps.manifest.json`：重算 `payload_sha256`，
  `solo_native_selector_scope` 与 `map_rule_sources` 补齐 16 行
  （含各自的 `DUNGEON_CHECK_CONDITION`、`LimitedMaxResurrectionUseCount`），
  并加 `master_road_qualification` 记录本次判定与上面那条抓包。
- `els_server/domain/known_resurrection_flow.py`：拒绝时把原因写进
  `s.resurrection_rejection`。
- `els_server/transport.py`：0xa7/0xaa/0x160 现在会多记一条
  `resurrection_diagnostic`（phase、请求字节数、拒绝原因、回复里的结果码），
  下次再失败不用靠推。

**验证**：`tests/test_master_road_resurrection.py` 3 项——16 张图都登记为
单人原生选点；每张图用真实 `DungeonRun` 造会话发 0xa7 得到 `death_ack(0)`
并进入 dying；未登记的 34000 仍是 `death_ack(-1)` 且原因被记下。
`tests/test_known_resurrection_current.py` 8 项不变通过。

**边界**：只开了单人通道；多人房间仍要求显式 spawn keys，且其它未登记副本
（如 34000 等）依旧拒绝复活——需要的话按同一格式继续加图。
地狱难度条目在客户端有 `LimitedMaxResurrectionUseCount: 3`，本地服务端没做每次
副本的次数上限，客户端自己会拦，不影响可玩性。

**未验**：真机复活待上号——进罗索被打死后按 Z，若仍失败，看服务端
`server.jsonl` 里新的 `resurrection_diagnostic.rejection` 是哪一条。
