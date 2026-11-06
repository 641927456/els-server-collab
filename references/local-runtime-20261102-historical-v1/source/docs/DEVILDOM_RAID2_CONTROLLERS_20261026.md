# 34140 裂隙二阶段控制器退场受理（2026-10-26）

## 现象

角色艾米粒在 `selected_map: 34140`（`dungeon_devildom1_raid2.lua`）内无法离开：对话框正文为空只显示"……"，右下角"离开裂隙"按下无效。会话 20261026-214618 的客户端 trace 显示，该局从 `0xB3`（384594）到 `0x225` 返回城镇（418913）之间**从未发出 `0xB8`（传送门请求），也从未发出 `0xBB`（part end）**，服务端 `0xBA` 出现 0 次、`0xC1` 出现 0 次，因此结算入口根本没被触达。

## 根因

34140 三个阶段各自的通关条件都是 kind 3（按模板点名），被点名的模板全部是 `active=False`、`no_drop=True` 的 class103 剧本标记：

| 阶段 | 要求击杀 | 脚本 |
|---|---|---|
| 0 | 6851 | `2018_RAID_BOSS2_PHASE1_END.lua` |
| 1 | 6853 | `2018_RAID_BOSS2_PHASE2_END.lua` |
| 2 | 6855 | `2018_RAID_BOSS2_PHASE3_END.lua` |

`condition_ready` 的 kind 3 用 `all(k in dead for k in required)` 判定，所以只有客户端把这些标记按原脚本退场并上报，part 才可能被观察为结束。此前没有任何模块登记 34140 的控制器，`0xAD` 分支的准入链（`hunter_chest_flow` → `source_actor_expiry` → `lithia_memory1` → `scene_actor` → `story_controller`）对 34140 全部返回 `None`，落到通用路径后被 `d['flag'] not in (0,1)` 丢弃（原脚本退场用 255）。

### 证据：按副本统计 `0xAD` 受理率

`analysis/client-6c6b5180/*/server-logs/server.jsonl` 里 `local_business_response_sent` 的 `size` 是整帧长度（与载荷长度按 8 字节量化对应：`0xAD` 载荷 87 字节 ↔ 帧 160）。把每条 `0xAD` 与其后是否出现 `0xAE` 配对：

| 地图 | 帧 160 | 帧 184 |
|---|---|---|
| 30070 | 1 受理 | 21 受理 |
| 34090 | 3 受理 | 32 受理 |
| 34120 | 1 **拒绝** | 10 受理 |
| **34140** | **9 全部拒绝** | 无 |
| 34360 | 1 **拒绝** | 10 受理 |
| 35320 | 1 受理 | — |
| 35322 | — | 69 受理 |

两个事实：

1. 帧 160 不是"不支持的形状"——30070/34090/35320 都受理过。35320 的受理方是 `source_actor_expiry`，它开头就 `if report['flag']!=255:return None`，所以**帧 160 就是原生 255 退场**（载荷 87 = 45 基础 + status/hp_bits 5 + 空 contribution 4 + 一条 readiness 13 + extra 8 + 空 counters 4 + last_uid 8，正好 `valid_sentry_death` 要求的"一条 `{owner:0}` readiness + 空向量"）。
2. 34140 那一局 9 次 `0xAD` 全是 255 退场，无一次玩家击杀帧（184）。系统性地全部被拒，是因为没有任何模块认领这些控制器。

同局客户端从未销毁任何 actor（`updated_npc_actor_destroyed` 只在收尾 418919 一次性销毁全部 9 个），与"服务端未回 `0xAE`、客户端不落地死亡"一致。

### 第二条独立证据：团本结算自己就要求这个游标

34140 在 `formal_raid_economy.definition` 里，`graph_sha256` 正是 `e19bb64e…930a3`，`phases = {'0':1,'1':2,'2':3}`——与本模块钉的摘要完全一致。

它的 `0xBB` 不直接进通用分支：`dungeon_flow.handle` 一进门先调 `raid_economy_flow.solo()`，而 `solo` 走 `settle` → `_binding`，那里有：

```
or not isinstance(r.next,dict) or r.next.get('kind') not in(1,2,3,4)
or r.ready_at is None or r.clock()<r.ready_at   →  raise ValueError
```

`r.next` 只可能由 `poll_ready()` 在 kind-3 条件满足时产生。修复前 6851 永远不会 `defeated`，于是 `r.next` **恒为 `None`**，`settle` 必抛，`solo` 捕获后返回 `[]`——`handle` 直接返回 `[]`，`0xBB` 被吞，连 `0xBC` 都不会有。换句话说：**即使客户端发出了 `0xBB`，34140 也不可能推进**。所以这次受理不是"补一个 ack"，而是团本结算链的前置条件。

## 本次增量

新增 `els_server/domain/devildom1_raid2_controllers.py`，只受理该图 9 个已声明静态标记的原生 255 退场；在 `dungeon_flow.handle` 的 `0xAD` 分支、`scene_actor_retirements` 之后调用。

| stage/part | wire key | template | source | point | script SHA256 |
|---|---:|---:|---:|---:|---|
| 0/0 | 5 | 6850 | 6 | 89 | f0087de7e426caf0db4ddbe2c8cf9736a5db8d2c849db0403123b1d8cd49d8b2 |
| 0/0 | 6 | 6856 | 7 | 89 | 77b6dd224fdbbecead56d842ba552c6286da8c35a637370ed2d72ece8bb2bd2f |
| 0/0 | 7 | 6851 | 8 | 89 | b4e59bbf3796155a09ea56fd3c2ee92e1563cfdedf8347ad1129231685c5b7c2 |
| 0/0 | 8 | 6857 | 9 | 89 | edbb755ab7e092219b64040c0372efa652dc182e2edf7cbc4605f4dd68d33a84 |
| 1/0 | 1 | 6852 | 2 | 1 | 1f1d8d1e70912534a6a373ab65e0e7307891458e4ded3402e024441aa0033182 |
| 1/0 | 2 | 6853 | 3 | 1 | 8f4576beedac637a25d0c9b0f505d75c5cd282c5b5bcd62d6e5b732a2e311876 |
| 2/0 | 1 | 6854 | 2 | 1 | fff08f20ab413254c14ec96e443a6eda10749b0e020346f3c1f52fa92bfedc08 |
| 2/0 | 2 | 6855 | 3 | 1 | 216d41de584e8593326e48ccb015c449b1fa692487856fa6cc6060a07e89ad90 |
| 2/0 | 3 | 6849 | 4 | 1 | 115a691670abb4b0b54b9f00a8800af01057264183ce9815adc741d726b70802 |

图摘要钉死为 `e19bb64e80a3788b985b54910c9ad4d29004f29234c68db933bdb395d83930a3`。

每条受理同时校验：实际 graph 内容与摘要、graph 与 catalog 当前资源一致、manifest 脚本摘要、整条 source 字段（含 `active=False`/`no_drop=True`/`points`/`offset`/`rate`）、wire key 与 start point、当前 `initialized_maximum`、native `class_id==103 / script / is_npc`、`npc['active'] is False`、原 run/阶段/单人 owner/current lease/`reward_run_id`、完整 native255 包（`valid_sentry_death` + 有限坐标 + `hp_bits`）。

**不设 `unit_type` 门**。同族的 `scene_actor_retirements`（Memory2）与 `story_controller_retirements`（`unit:13`）都带职业门，因为那是角色专属剧情；34140 是共享团本，标记由路线本身声明，且**同一张图的普通死亡路径本来就不看 `unit_type`**（`dungeon_flow.handle` 通用分支没有该判断）。用唯一观察到的那一个角色去设门，只会把其他角色留在同一个空对话框里。

受理后只回 `0xAE` 和空奖励 `0xAF`，并沿原条件判断是否发 `0xBA`；shadow 里先编码完全部回复再采用状态，同 payload 重放只 ack，冲突重放拒绝。不调用任务、经验、掉落或经济消费者，不生成任何死亡、wave、计时或 gate。

## 为什么不采用其他路径

- **不复用 `story_controller_retirements`**：它的准入要求 `rule['quests'] or rule['map_quests']`（真实任务证据）。34140 的三个 END 控制器没有任何任务前置，用它会变成"无任务伪造准入"。
- **不允许 zero 别名**：`lithia_memory1` 允许 `report['index'] in (0,key)`，但 34140 的 key 0 就是 Boss 6801（`hp=1322115840`）。这里只接受精确 key，零永远不是别的实例的别名。
- **不给 6849 之外的特例**：6849（`PHASE3_SUMMONNER`，HP 与 Boss 同量级）同样是已声明 `active=False`/`no_drop=True`/class103 标记，一视同仁受理；它不是任何阶段的通关条件，受理它不改变条件判定。
- **不预置"Boss 必须已死"前置**：那是发明规则。`0xB8` 分支本身已经要求当前 part 全部 active 敌对已死，提前发 `0xBA` 不会让玩家绕过 Boss 开门的检查。
- **不改 `transport.py`**：新增诊断探针属于维护者核收范围，本轮不触碰；现有日志已足够定位（见上表）。

## 恢复方式

1. 代码回退：`git revert` 本笔（1 个新模块 + `dungeon_flow.py` 里 3 行调用）。
2. 不改代码：把 `DEVILDOM1_RAID2_CONTROLLERS_ENABLED` 置 `False`。该开关只关掉新增受理，`handle` 立即返回 `None`，`0xAD` 回到改动前行为。

## 验证

- `tests/test_devildom1_raid2_controllers.py` 15 项通过：九个标记全部通过实时 `source_rule` 且 runtime HP 与 `initialized_maximum` 一致；只退 6851 才结束 stage 0 的 part 并给出 `next.kind=1 → stage 1`；stage 1（6853）与 stage 2（6855）各自退场后同样在 `delay=5` 到点发 `0xBA`，stage 2 的 `next.kind==4`；端到端一条链（退 6851 → 计时到点 → `0xBA`；五个 active 敌对未全死时 `0xB8` 回 -1；全部击杀后 `0xB8` 回 0；`0xBB` → `0xBC` + 换阶段报文，cursor 落到 stage 1 且种群换成 6831/6852/6853）；stage 2 退场后 `0xBB` 进入 `clear()` 分支并回 `0xBC`+`0xC1`（`clear` 本身用桩替代，只验证入口）；`formal_raid_economy.definition(34140)` 的 `graph_sha256` 与本模块 `GRAPH_SHA` 相同、`phases` 覆盖 0/1/2 三个阶段，且退场前 `run.next is None`、退场后 `ready_at` 与 `next` 依次就位；unit 1/5/10/15/17 五个职业都能受理；同 payload 幂等、异 payload 拒绝；Boss 与 4 个 active 小怪不能被 255 退场；相邻 34120 不外溢；外来 owner/participants 拒绝；flag 0 时本模块 `None` 让位通用路径；编码失败不落地任何状态；开关关闭后 `handle` 返回 `None`。
- `tools/ci_checks.py`：1673 文件、协议往返 OK、`no_owner_data` OK，无 failure。
- 相邻既有测试（`test_scene_actor_native_expiry` 等 8 个模块）在本改动前后同样报 `SimpleNamespace` 缺 `catalog`/`graph` 的错误——把本模块 `handle` 强制替换为 `None` 复跑仍报同样 3 项，**与本改动无关**，属既有 fixture 与 `formal_npc_hp` 接口漂移。

## 风险与未覆盖

- **提前 `0xBA`**：如果客户端在 Boss 还活着时就退场 END 标记（6851），`periodic` 会立刻宣告 part 结束；此时 `0xB8` 仍回 -1（Boss 与 4 个小怪未死，门不开），但客户端若自行发 `0xBB`，`0xBB` 分支只要求 `part_end_notified` 与 `poll_ready()`，会直接推进到 stage 1。端到端测试里已能看到这条路径。这里没有加"Boss 必须已死"的前置，因为那属于发明规则；`scene_actor_retirements` 对 Memory2 花朵也是同一处理方式。若实机出现"没打 Boss 就过了 stage 0"，再按 `finale_boss_pending` 的既有模式加定点守卫。
- 那 9 次 255 上报的具体 `index` 顺序没有落盘（`transport.py` 只对 35250 打 `retirement_probe`，且该文件属维护者核收）。本受理按"9 个已声明标记全收"设计，无论客户端报哪几个都能落地；但"9 = 4 + 2 + 3 全量"目前只是数量上的巧合，不是已证事实。
- 未做实机验证。需要下一局真实进入 34140，确认 `0xAE`、`0xBA`、`0xB8`→`0xB9` 开门、`0xBB`→`0xBC`→`0xC1` 结算。
- stage 2 的 `next.kind==4`（CLEAR）只验证到"进入 `clear()` 分支并回 `0xBC`+`0xC1`"，`clear()` 内部用桩替代；真实 `reward_store` 事务、碎片/金币入包、回执幂等未在本轮验证。
