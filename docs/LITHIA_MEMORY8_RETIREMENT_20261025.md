# PR494 原生退场链：有限修复v3与正式父版核对（2026-10-26）

本次从实际 `assembly-native-completion-20261026-v1` 正式包继续。Git main 中旧消费者不能覆盖已交付的 HP、原生攻防/抗性、普通及团本经济、共享来源准入、Memory1 真任务证据和屏障。

## 已实现的独立增量

35320 graph `696e2f7ad0e4685ea9dea807e03bf7eb54a953c7d9b08453deae8bb0dcba79e3` 仅新增三条原静态 actor 的 native255 退场受理：

| stage/part | wire key | template | source | point | script SHA256 |
|---|---:|---:|---:|---:|---|
| 0/1 | 15 | 9436 | 4 | 12 | a5d1caf39396087d781e2475f4078908eb3e30a031d593a8dab758ec183c3f16 |
| 0/1 | 17 | 9436 | 6 | 37 | a5d1caf39396087d781e2475f4078908eb3e30a031d593a8dab758ec183c3f16 |
| 1/0 | 4 | 9433 | 5 | 26 | 82f6b52a62d2bb6ed56f8f595a0875c5f7b421bd201774814a5856e4513d243c |

原会话线索为 20261025-193058 的 bug keys15/17（requests475/481）与 20261025-165751 的 plant key4（request5511）。它们来自原PR文档及本轮指定有限证据；本修复没有重新操作游戏，也没有将旧 trace 文案当成本轮自然实机验收。35321 没有同等独立退场证据，未新增其战斗 actor 过期来源。

每条同时校验实际 graph 内容/摘要、模板 class0/script、脚本摘要、全部原 source 字段、wire key/start point、当前正式初始化 HP、unit15、原 run/阶段/单人 owner/current lease、会话阶段及完整 native255 包形态。实际正式 HP 为109506；没有恢复原候选500兜底。三条只回0xae和空奖励0xaf，并沿原条件判断是否发0xba；不调用任务、经验或掉落消费者。shadow 中先准备门与clock并编码全部回复，成功后采用状态；同payload重放只ack，冲突重放拒绝。

9450两条原控制器（35320 s1p0/source10，35321 s0p0/source10）继续走原真实任务事务。退场资格采用各自已存在的 `map_quests`：35320包含28540访问任务，35321仍为28550及其原后继任务；没有给35321增加28540或无任务准入。原 `quests:[28550]` 不改，实际任务只在其已激活时进度一次，不领取奖励。两条都要求原native255，不能走普通玩家击杀或generic scene过期旁路。

## 比较后保留/剔除

- 保留实际正式113条控制器规则、当前地图/职业准入、真实初始化HP与原经济消费者。
- v2剔除main的泛class103静态scene过期受理及无用scene_controller helper。class103元数据不足以证明特定来源有退场许可；未限定来源的active/inactive scene255均拒绝且不改状态。原正式dynamic expiry保持，source_pinned独立证明保留。
- Memory1保持真实9470自身报告和原barrier；9310不生成9470任务证据。没有采用main/PR的合成 `retire` 证据。
- 不采用泛静态expiry、WAVE_RETREATS/retreated模拟、动态scene prefix扩展或ELS_TUTORIAL_ALIAS；main的35270无任务放宽及PR的35290/35320/35321无任务放宽均未安装。
- 9432一只或八只已报告死亡都不能虚构未报告9452的退场，原kind3条件继续等待真实控制器。

## 验证与边界

v1的34项结果仅为旧候选历史，不作为v2核收。v2修正后，S及实际online/local两个候选各22项关键回归全部通过；两端确认205/203个服务模块均只从各自候选加载。覆盖有限三源当前HP、owner/unit/lease/graph/source/HP等拒绝、完整预编码失败状态保持、相同/冲突重放、原门判定、9450真实临时SQLite事务，以及未限定class103 scene拒绝无状态泄漏、原server-allocated dynamic expiry保留。临时库验证28540不赠送28550、28550激活后进度一次且不领取奖励。本轮未访问玩家或账号库。

泛 `test_lithia*.py` 仍有原first-entry/town会话fixture触发的 `Chip reset trusted local actor` 错误，详见本轮独立receipt；没有为了让旧fixture通过而削弱正式身份检查。源码/临时库通过不代表自然GUI、战斗或本轮公网通过；主线程还须在实际正式父包装配候选后核全部业务摘要、独立验证、发布保护及双端验收。


v2相对当前正式父包仅两项退役行为叶：els_server/domain/dungeon_flow.py、els_server/domain/story_controller_retirements.py；两端dungeon_spawns.py恢复各自父包原始字节，作为零delta排除。详细原字节前后SHA、精确替换ops及双向逆证明见本轮retirement-v2/scene-expiry-removal-raw-proof-v2.json。


## v3 code-first recovery（2026-10-26）

生产默认两个常量为True。仅代码恢复时，将dungeon_flow.py的MEMORY8_SOURCE_ACTOR_EXPIRY_ENABLED=False，有限三源返回None并沿原正式拒绝链；将story_controller_retirements.py的MEMORY8_9450_MAP_QUEST_ADMISSION_ENABLED=False，9450资格恢复原rule[quests]，原28550报告仍受理。新回执读者及已接收相同回执ack、原dynamic expiry、其余113规则均保留；无数据/schema/安装DDL。S与online/local候选各27项关键测试全部通过，包含False恢复准入、原目标任务与动态退场不受损。各端原字节前后SHA、恢复精确True到False字节、parent到新两叶差异及逆证明见retirement-v3/recovery-switches-raw-proof-v3.json；旧v1/v2证明保持历史。
