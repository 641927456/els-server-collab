# 大师之路（特殊副本 Dungeon_Md_*）BOSS 打不死

**现象**：特殊副本页里的 8 个大师之路副本（双头蛇的神殿、艾丽阿诺德修炼场、
元素精灵的圣地、解开的记忆的枷锁、动摇的眷属的苦恼、水龙的罗盘、纳斯德测试室、
黄昏之门）进图后 BOSS 血量离谱，实战里打不掉，副本收不了。

**根因**：这 8 个入口对应 `Dungeon_Md_*` 家族（34370–34700，含 8 个地狱难度共 16 张图）。
它们的 BOSS 血量来自 `els_server/data/formal_npc_hp.json` 的 `public_hp_templates`，
那是更晚零售世代的绝对值，而本客户端 Lv99 一次伤害约 1e5：

| 地图 | BOSS 模板 | 导入 BOSS 血量 | 同图小怪 |
| --- | --- | --- | --- |
| 34370 Gaia | 7620 | 505,514,880 | 119,702 / 30,000 |
| 34390 Rosso | 7800 | 1,866,516,480 | 119,702 / 30,000 |
| 34410 Ventus | 7640 | 972,144,000 | 119,702 / 30,000 |
| 34440 Deniph(Hell) | 7840 | 3,888,576,000 | 119,702 / 30,000 |
| 34460 Adrian(Hell) | 7670 + 7676 | 6,999,436,800 ×2 | 119,702 / 30,000 |
| 34500 Harnie(Hell) | 7710 | 13,998,873,600 | 119,702 / 30,000 |
| 34700 Ebalon(Hell) | 8130 | 6,999,436,800 | 119,702 / 30,000 |

对比已验证可玩的 34490（水龙的罗盘普通）：它没有公开导入，走地区曲线兜底
`default:boss = 113340 + 17005.6 × 99 = 1,796,894.375`，这个数值是能打死的。
`state/development.sqlite3` 的 `pve_kill_experience` 里这 16 张图没有任何击杀记录，
与「BOSS 打不死」一致；死亡上报本身（0xad → 0xae/0xaf）工作正常，缺的只是血量量级。

`config/local_hp_curve.json` 的全局压缩是关的（`enabled:false`，按 2026-10-27 要求恢复
导入原值），所以此前没有别的层把 BOSS 血量拉回来。

**改动**：

- `config/local_boss_hp_cap.json`：新增，`provenance: local_boss_hp_cap`，
  列出 16 张图及每图倍率（当前全 1.0）。删除该文件或 `enabled:false` 即恢复导入原值。
- `els_server/domain/local_boss_cap.py`：新增。`rules()` 校验 schema/provenance/开关/倍率
  边界；`target(dungeon)` 取该图地区/等级下的 `profile:boss` 曲线值；`apply(dungeon, value)`
  把超过 `target × multiplier` 的血量压到上限，低于上限的原样返回（幂等）。
- `els_server/domain/formal_npc_hp.py`：`_local_curve()`（唯一的本地可玩性出口，
  `maximum()` 两个返回点共用）在 `local_hp_curve` 之后再走 `local_boss_cap`。
  只影响配置里列出的地图，其他地图与 `field_boss` 完全不受影响。

生效后的名单：16 张图的 BOSS 全部 = 1,796,894（与 34490 相同），34460 的 6.99 亿大怪
7676 同步压到 1,796,894；119,702 / 432,064 / 30,000 的小怪原值不变，同图相对强弱保留。
34490 原本就是 1,796,894，数值不变。

**验证**：`tests/test_master_road_boss_cap.py`（8 项）：配置固定为 16 张图 × 1.0、
目标值 = 1,796,894.375、导入 BOSS 值被压且幂等、小怪与未列出地图（0 / 34000 /
34340 / 34350 / 34360 / 120000）原样通过、开关关闭与缺文件恢复导入、provenance 错误抛错、
运行时 16 张图每图恰好一个 BOSS 且血量 = 目标、关掉上限钩子后 34370 BOSS 回到 505,514,880。
既有 `test_retained_native_hp`、`test_altera_core_boss_gate`、`test_devildom2_part_markers`、
`test_nasod_factory_exit_gates`、`test_sentry_stage_persistence`、
`test_settled_run_trailing_death` 不变通过（`test_dungeon_rotation` 里 2 项因缺
`role_native_replay` 模块报错，与本次改动无关）。

**未验**：没有本机击杀这 16 张图 BOSS 的抓包，真机通关待玩家上号验证。若某张图
仍打不动，先看该图是否需要更高倍率（改 `config/local_boss_hp_cap.json` 对应行），
再取该次会话的 `analysis/client-*/<ts>/` 轨迹确认客户端是否另有场景门槛。

## 2026-10-30 回退：血量不是「打到一半不死」的原因

上号实测：压到 1,796,894 后 Rosso 依旧打不死，血条停住。轨迹里 BOSS 血量（服务端
`updated_dungeon_frame.npcs[].hp`）的行为两次一致，都停在 `上限 ÷ 1000`：

- 原值 `analysis/client-6c6b5180/20261030-001006`：1,866,516,480 一路掉到 12,162,609，
  随后一步落到 1,866,516.5（= 原值 ÷ 1000，float32），之后再无变化。
- 上限 `analysis/client-6c6b5180/20261030-011446`：1,796,894.375 → 1,796.894（= ÷1000）
  后冻结；该会话里客户端没有发出任何 0xad 死亡上报，也没有 0x2ce 召唤或 0xb8 开门请求。

结论：卡死与绝对血量无关，改大改小都停在 `max/1000`，所以本次把
`config/local_boss_hp_cap.json` 的 `enabled` 改回 `false`，16 张图 BOSS 恢复导入原值
（34390 → 1,866,516,480，34370 → 505,514,880），代码钩子保留。
`tests/test_master_road_boss_cap.py` 相应改为「配置处于关闭态」，上限逻辑本身仍由
patch 后的用例覆盖（8 项全过）。

下一个待验证的杠杆：客户端血条显示 151 格（`x 151`），而 `dungeon_population.py:41-43`
记录的客户端函数 1693620 会「把最大血量除以血条格数」，16 张图当前下发的
`boss_lines` 都是 1。若要验证，把某张图的 `boss_lines` 改成客户端实际格数再打一次。

## 2026-10-30 恢复上限：用户确认上限版才是修好的状态

用户确认「之前修好了」指的是上限版，并给了验收口径：
**BOSS 上方格数和脚下血条保持一致就是对的**，血条掉到一半属于正常进展。

数值上也对得上：上限目标 `1,796,894.375 ÷ 11,900 = 151.0`，正好是实机 `x 151` 的格数；
导入原值 `1,866,516,480` 换成 `156,850` 格，客户端表示不了，血量才会卡在 max/1000。
所以本轮把 `config/local_boss_hp_cap.json` 的 `enabled` 改回 `true`，
16 张图 BOSS 全部 = 1,796,894.375（= 151 × 11,900），`boss_lines` 保持导入的 1
（客户端自己按 HP 推格数，151 格已与上限自洽）。

`tests/test_master_road_boss_cap.py` 回到「配置处于开启态」：配置固定 16 张图 × 1.0、
导入 BOSS 被压到 1,796,894.375、小怪与未列地图直通、运行时 16 张图每图恰好一个 BOSS
且血量 = 目标、关掉钩子后 34370 回到 505,514,880。

配套新增的 `local_boss_gauge` 叠层（`config/local_boss_gauge.json`）保持代码但
`enabled:false`：上限恢复后客户端的 151 格已经正确，不需要再改下发的格数。

