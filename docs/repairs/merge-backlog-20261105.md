# 待合并清单（2026-11-05 盘点）

盘点对象：`E:\游戏\艾尔之光\els-server-collab`，HEAD = `ed80b6b`（2026-11-05 00:53）。

## 0. 结论先行

- `origin/main` 是 `a9a3e80`（2026-11-01 23:27），比 HEAD **落后 109 个提交**。远端没有比本地更新的东西，**不需要 pull**。
- 用户在 GitHub 上看到的「open issue」页里**没有真正的 issue**，全是 PR：第一页 #867–#882（16 个，全部 11-05 当天），第二页 #766–#782（更早的批次）。这些 PR 在本地都留有对应的归档分支，**一个都没并进 HEAD**。
- 这些分支**不是普通代码分支**。每一个都是「一次性归档提交」：只在 `reference(s)/<release>/` 下放源码快照 + `review.md` + `verification.json`。合并动作不是 `git merge`，而是把 `.../source/els_server/...` 按文件覆盖到运行树（选择性整合，不整树覆盖）。

## 1. 判定方法（为什么不能用 `git diff`）

浅克隆已修：`git fetch --deepen=800 mirror`。此后再用 `git merge-base --is-ancestor` 判定才可信。

不能用 `git diff HEAD <branch>` 判断「有没有装」，原因有两个：

1. 每个 11-05 分支都把**历史全部归档**又带了一遍（一个分支里几百个 `references/*`），diff 必然巨大。
2. 归档里的源码是**当时的父版快照**（多为 10-30/10-31），现在的树已经往前跑了几千行（`local_session.py` 差 2964 行）。「有差异」不等于「没装」。

可信判定只有一条：**按文件比对 blob 与磁盘内容**，并把「磁盘上根本不存在该文件」单独算一类（`缺`）。`缺` = 这个功能确定没进树；`异` 可能只是树更新了。

归档内路径有四种布局，取实盘路径时要剥掉 `source/<channel>/` 前缀：

```
references/<release>/source/els_server/...            # 10-31 那批
references/<release>/source/common/els_server/...     # 10-31 那批（分 channel）
reference/<release>/source/els_server/...             # 11-05 那批（单数 reference）
references/<release>/source/<sha256>/<file>.py        # 内容寻址，需按 delta.json/patch 还原
```

## 2. A 组：11-05 的 16 个 open PR（对应 #867–#882）

| PR | 内容 | 归档目录 | 源文件 | 缺 | 结论 |
|---|---|---|---:|---:|---|
| #881 | 原生交易 / 摄影棚 / 宠物饰品 / 冰装分解闭环 | `native-independent-closures-20261105-v4` | 62 | 21 | 未装 |
| #877 #870 | 公会全量（银行/农场/远征/技能/皮肤/任务…） | `native-guild-reviewed-20261105-v1` | 109 | 48 | 未装 |
| #877 | 公会批准配置 + 首图 4FB/504 入场 | `native-guild-approved-leaves-20261105-v1` | 4 | 3 | 未装 |
| #880 | 原生玩家直接交易 | `native-player-trade-20261105-v2` | 3 | 3 | 未装 |
| #871 #868 | 八人摄影棚 + 背景解锁 + 常驻任务 | `native-photo-zone-20261105-v1` | 22 | 10 | 未装 |
| #879 | 冰装分解 fixed-45 | `native-ice-costume-fixed45-20261105-v1` | 2 | 1 | 未装 |
| #873 | 宠物远征计时 / 空奖励 / 公仓到期 | `native-pet-bank-leaves-20261105-v1` | 3 | 2 | 未装 |
| #875 | 成长指南箱写锁后核对期限 | `native-guide-box-writer-clock-20261105-v1` | 1 | 1 | 未装 |
| #874 | 协同票券写锁后核对期限 | `native-collection-writer-clock-20261105-v1` | 1 | 1 | 未装 |
| #872 | 邮件写锁后到期判断 | `native-mail-writer-clock-20261105-v1` | 2 | 0 | 疑似已装（树更新） |
| #869 | 家具保存绕过家园契约到期 | `native-housing-layout-clock-20261105-v1` | 1 | 0 | 疑似已装（树更新） |
| #876 | 摄影棚背景票 50 ED 上架 | `native-photo-ticket-shop-20261105-v1` | 1 | 0 | 疑似已装 |
| #867 | 公告栏成交后保留强化计量/保底 | `native-market-progress-20261105-v1` | 1 | 0 | 疑似已装 |
| #882 #878 | V80 / V79 启动器签名绑定 | `native-independent-launcher-20261105-v80` | 0 | — | 启动器资源，不涉及 `els_server` |

A 组里另有 6 个分支是上面这些的中间版本（`-v1`、`-leaves-v2`、`v79`），已被 v4/最终版覆盖，不必单独处理。

## 3. B 组：11-01 整合列车 `cand/integrate/open-prs-20261101`（最值钱的一批）

这条分支收了 20 多个归档，**几乎全部没落地**。它是最容易「一次合并、修好一大片」的对象。

| 归档 | 内容 | 源文件 | 缺 | 玩家可见影响 |
|---|---|---:|---:|---|
| `common-box-opening-20261031-v1` | **76 个箱子模板 / 15 组消费者** | 21 | 全部 | 箱子打不开（主诉） |
| `owned-box-opening-20261031-v2` | 11 个既有箱子（109999/110850/135666/135871/300645/300646/300647/723618/723687/723688/117542） | 9 | 全部 | 右键无反应 |
| `owned-common-boxes-dual-20261031-v1` | 双端常用箱投递 | 4 | 全部 | — |
| `promotion-fashion-bag-20261101-v1` | 职业时装箱误入冰装背包（group7 被读成 group27） | 7 | 全部 | 时装进错背包 |
| `three-activities-startup-20261101-v1` | 三活动 + 签名启动（4 个奖励箱 / 共享银行限制 / 事件到期 / 房间 buff） | 68 | 20 | 活动奖励箱 |
| `scroll-families-20261101-v1` | 现有卷轴消费（强化 44 + 祝福复原 56 变体） | 37 | 13 | 卷轴用不了 |
| `controller-quest-gates-20261101-v1` | 控制器任务门禁（`public_controller_rules.py`，树上**完全没有**） | 1 | 1 | 任务接不了 |
| `shop-missing-20261031-v1` / `shop-rare-navy-20261101-v1` | 商城补漏 / 藏青 | 6 / 4 | 0 | 商城缺货 |
| `ring-cross-bag-delivery-20261101-v1` | 戒指跨背包投递 | 4 | 0 | 穿戴失败 |
| `retained-mail-login-20261101-v1` | 保留邮件登录 | 5 | 0 | — |
| `ep13-retained-inventory-20261101-v1` | EP13 保留消耗品 | 2 | 0 | — |
| `mainline-leveling-exp20-20261031-v1` | 主线 20 倍经验 | 4 | 0 | 升级速度 |
| `ground-drop-models-20261101-v1` / `registered-ground-items-20261101-v1` | 地面掉落模型 / 已注册地面物品 | 8 / 10 | 1 / 0 | 掉落显示 |
| `gm-high-level-scrolls-20261031-v1` | GM 高级卷轴 | 6 | 0 | — |
| `dungeon-map-markers-20261031-v1` | 地图标记 | 3 | 0 | — |
| `native-login-reconnect-20261031-v1` | 登录重连 | 7 | 0 | — |
| `elrian-breakable-gates-20261101-v1` | 艾尔丽安可破坏门 | 3 | 1 | — |
| `native-line-trigger-relay-20261031-v1` / `native-world-event-iteration-20261031-v1` | 线路触发中继 / 世界事件 | 3 / 3 | 0 | — |

## 4. C 组：单独一支

| 分支 | 内容 | 源文件 | 缺 |
|---|---|---:|---:|
| `cand/fix/858-pve-exp-reference` | PVE / 团队副本经验表（`pve_experience.json`、`raid_phase_experience.json`） | 9 | 4 |
| `cand/feature/native-friends-actor-20261105` | 好友 Actor | — | 0 源文件（纯证据） |
| `cand/repair/pr771-online-selective-20261103` | #771 六批（`server/local`、`server/online` 布局） | 另一套布局 | 待核 |

## 5. 已确认「不用再并」的老分支

`fix/701`、`fix/705`、`fix/owned-common-boxes`、`fix/741`、`fix/745` → 归档里已经没有活源码（后续提交已把内容装进树）；`fix/817`、`fix/846`、`fix/838` → 已是 HEAD 祖先。

## 6. 与手写修复的关系（重要）

本轮手改的 `els_server/storage/fixed_cubes.py` 数量门禁，与 B 组 `common-box-opening` 归档里的实现**完全一致**：

```python
if request.option not in (0,1):
    raise ValueError('Unsupported fixed cube quantity')
```

说明手改方向与上游一致，合并时不会互相打架，可以放心用归档版覆盖（归档版还带 76 个模板注册和 15 组消费者）。

但工作树现在有 43 个未提交改动（含本轮箱子/任务修复、`hot_reload.py`、`bag_expansion_*`、`pet_auto_flow.py` 等），而 A/B 组会重写 `application.py`、`session_dispatch.py`、`local_session.py`、`inventory_items.py`、`seal_quests.json`。**合并前必须先提交或 stash。**

## 7. 建议的合并顺序

1. **先提交**当前工作树（箱子 Count1、任务注册、`hot_reload`、背包扩展、宠物自动喂食等），保证可回滚。
2. **B 组 `common-box-opening`**（21 文件）→ `python -m els_server --check` → 玩家实测开箱。这一步直接回应「背包很多箱子打不开」。
3. **B 组其余**按玩家痛点排序：`owned-box-opening` → `controller-quest-gates` → `scroll-families` → `promotion-fashion-bag` → `three-activities-startup` → 商城/戒指/掉落。
4. **A 组**：`native-guild-reviewed`（109 文件，最大）与 `native-independent-closures-v4`（62 文件，聚合了交易/摄影棚/宠物饰品/冰装分解）优先；写锁类四个（mail/housing/guide-box/collection）可最后扫尾。
5. **C 组 `pve-experience`** 补经验表。
6. 每步都跑 `python -m els_server --check` + 相关测试。注意存量失败用例：`test_seal_quests`(3)、`test_region_quest_flow`(2+1)、`test_epic_quest_experience_ceiling`(1)、`test_quest_expiry_regressions`(1)、`test_regional_boss_cubes_legacy`(2) —— 这些在合并前就已失败。

## 8. 不要做的事

- 不要 `git merge` 这些分支（会把几百个 `references/` 塞进树干，且没有代码效果）。
- 不要整树覆盖 `els_server/`：归档是**选择性整合**，LOCAL 和 ONLINE 两侧差异要保留（归档 README 反复强调这一点）。
- 不要 `importlib.reload` 持有模块级异常类的模块（`storage/seal_quests`、`storage/seal_quests` → `quest_flow` 持有 `QuestIncomplete`）。

## 9. 已执行（2026-11-05 20:30 起）

已按第 7 节顺序落地第一批：**B 组的两个箱子归档**。

| 提交 | 内容 |
|---|---|
| `090ffbd` | `owned-box-opening-20261031-v2`（11 箱）+ `common-box-opening-20261031-v1`（76 模板 / 15 组） |

执行细节：

- 21 + 9 个载荷文件里，**19 个与归档记录的父版哈希完全一致**，整文件覆盖；`owned_reward_boxes.py` / `owned_reward_boxes.json` 是新文件，按归档字节写入（JSON 的 sha256 = `3ed670…`，模块内 `DATA_SHA` 校验通过）。
- 另外 5 个已漂移、必须手工合并：`acquisition_policy.py`、`local_session.py`、`boosting_2026_nested_capacity.py`、`fixed_cubes.py`、`inventory_state.py`。手工合并保住了本轮早些时候加的两样东西：副本 DTO 的自定义选择载体，以及 `option not in (0,1)` 的 Count-1 门禁。
- `fixed_cubes.py` 里 `owned_reward_box` 分支单独走 `_legacy_actor` + 自有 `_issue_source`（policy `owned-reward-boxes-20261031-v1`），扣箱与发奖同一事务，`finalize_grants` 负责神物/时装的固定选项与已鉴定标记。
- `inventory_state.py` 的保留消耗品按 `owned_max_stack` 封顶并用 `read_existing` 重读，发出去的药水与原生持有的形状一致。

验证：

- `python -m els_server --check` 通过（items 181836、dungeons 740、npc 7526）。
- `catalog()` 92 → 98 条；消费者全部可解析：黑市 26、原力 3、时装 3、饰品 3、参与装备 1、扩包 1、称号 1、启航 2、自有箱 6；读取器定义 1430 条全部注册进 `VERIFIED_TEMPLATES`。
- `tests.test_regional_boss_cubes_legacy` 17 项仍是合并前那 2 个已知失败（`answer[-1].kind` 577≠0x197、stale-session 假成功）。
- 用 `git worktree`（5caad60 + 链接 analysis/state/data/client）做了 A/B：`test_advancement_cube_coverage`、`test_consumables`、`test_declining_consumers`、`test_bag_capacity`、`test_ed_shop`、`test_extended_shop`、`test_dungeon_rewards`、`test_durable_reward_acceptance`、`test_inventory_restore_and_drops` 九个模块在合并前后**失败集合与失败数完全一致**，没有新增回归。
- 另记：`tests/test_inventory_rewards.py` 是脚本式测试（import 即断言），`77000` 的堆叠上限是 999 而脚本按 99 填包，因此在合并前就已失败，与本次无关。

尚未做：游戏内实测（需要重启服务端加载新模块与 875 KB 读表）。

## 9b. 已执行（2026-11-05 21:10 起，第二批）

| 提交 | 内容 |
|---|---|
| `8fd9ebf` | `980047 晋级时装（15日）宝箱` 消费端（玩家实际点不开的那个箱子） |
| `f3cce70` | `controller-quest-gates-20261101-v1`：#688/#729 的 `public_controller_rules.py` + `rules_for` |
| `1ca6c14` | 陈旧测试：四个职业箱已接线，不再断言「必须拒绝」 |
| `deee6e3` | `scroll-families-20261101-v1`：22 个新模块 + 6 处改动 |

### `980047`

不在 245 个归档、也不在 `catalog()`；以已审阅的 `135666（7日）` 为父本，194 个职业逐条照抄，只把 `inventory_days` 7→15。详见 `promotion-15day-box-980047.md`。

### `controller-quest-gates`

- 归档 shipped 的是**一半**：`public_controller_rules.py`（146 条 = 135 条原公开规则 + 11 条剧情行）从来没有进过树，而 `story_controller_retirements.rules_for` 在本树任何一版里都不存在（`082e4d3` 之前就没了）。两半一起装。
- 11 条新增行与它们替换的剧情行**逐字段相同**，只差 `quest_independent`（其中 4 条另加 `requires_native_255`）；任务列表、来源 pin、HP、graph sha、职业集合一律没放宽。
- `rules_for` 按 `(stage,part,template,source_index)` 合并，公开行只覆盖那 11 个身份；其余 87 条剧情门禁原样保留（用例已钉住）。
- 副作用：28 个此前只在公开表里的副本，`handle` 不再一律返回 `None`。
- `test_laby/noah_native255_guard` 看不到这次改动：它们在 `formal_npc_hp.initialized_maximum` 就因夹具缺 `static_npc_level` 报错（合并前后各 23 个 error，集合完全一致）。新增的 `tests/test_public_controller_rules.py` 9 项改为钉住新契约。

### `scroll-families`

- 22 个文件「缺失或仍是合约里的父版」，逐个核对 `source-contract.json` 的 sha256 后整文件写入；8 个漂移文件逐个判断。
- 取：`enhancement_scroll` 改为从 `owned_scroll_families` 取家族（44 条）、`wisdom_potions` 双端升级为「普通经验道具」（37 条贤者/等级卷轴 + 数量、剩余堆叠回执、整级目标）、`equipment_receipt_state` 加三个回执种类（保留 `0x8ad`/`0x8b9`，取并集）、`session_dispatch` 只加四个钩子（`artifact_flow.handle_consumable` 置首，其次 trait reset、challenge scroll，排在 wisdom potions 之前）。
- 不取：`domain/identification_ui.py`（依赖 `identification_ui.json` 的 `975267cf…`，本树是 `c3e9be1f…`，归档也没带新表，装上就会 `Identification source changed`；`storage/identification_ui.py` 一并回退）、`domain/inventory_items.py`（另一棵树的全量快照，会删掉 `0x395` 衣柜字段并引入六组别的功能）、`storage/wardrobe.py`（归档删掉本树的 `13890C0` 重放，树更新）。
- 未验证：归档自带的 15 组隔离检查需要 qualified runtime，本机跑不了；`--check`、导入体检（21 个模块）、34 个箱子用例、挑战状态/神物戒指/晋级箱覆盖均通过。

## 9c. 已执行（2026-11-05 21:30 起，第三批）

| 提交 | 内容 |
|---|---|
| `9ce2efe` | `promotion-fashion-bag-20261101-v1`：普通晋级时装回背包 7，冰装留 27 |
| `63bf44e` | `three-activities-startup-20261101-v1`：四个 Boost 箱子接通 + 活动到期上限 + 共享银行限制 |

### `promotion-fashion-bag`

- 三个箱子读者把原生 group7 的普通时装当成 group27，职业时装箱一直发进冰装背包。新增 `fashion_inventory.native_groups`，按原生 `flags8 & 0x100` 判定，`job_reward_boxes`/`promotion_reward_boxes`/`owned_reward_boxes` 三处 reader 统一过一遍。
- `inventory_items` 里职业箱读者注册 `if _r['group']in(7,27)`（原来只认 27），否则与归一化后的 reader 撞 `Career box reader conflict`。
- `storage/inventory_state`：新增 `migrate_normal_fashion_bag`（27→7，保留 UID 与实例子表，写 `ordinary-fashion-native-bag-7-v1:<owner>` 审计）；`owned_template` 是被 `artifact_flow` / `el_search_collection_tickets` 引用却在本树缺失的函数，一并补回；`inventory_ready(db, owner)` 让「存档里还有放错组的行」触发迁移。
- 不取：`validate_plan`/`grant_items` 的 `shop_fashion_templates` 参数（依赖本树不存在的 `fashion_singles.onepiece_templates`）。
- 已用玩家存档副本验证：手工注入放错的 398002 → 初始化后回到 `bag_group=7, slot=10`，UID 不变，审计 `receipts_preserved=True`；真实存档当前没有放错行。

### `three-activities-startup`

- 归档是 local/online 双通道全量差分（213 文件），直接 merge 会删掉 34 万行。按文件分类：14 个 MISSING 是新功能，28 个 DRIFT 里 25 个是「归档比树新」。
- 本批只取「四个 Boost 箱子 + 活动到期 + 共享银行」这条最小闭环：`723619/723620/723621/723634` 四个固定内容箱子（归档 readers 1438 是树的严格超集，无冲突行）；`outputs_for` 改为「有 `class_outputs['0']` 就用它」，不再硬编码 `(117542,723618)`。
- `boosting_2026_item_policy` 从 `selected2026/local-growth.json` 的 `configuration.ends`（1796004000 = **2026-11-30 10:00**）取活动截止；`domain/item_expiration` 与 `storage/item_expiration` 都改为经 `item_deadline`，没有自身期限的活动行在截止后被同一次事务清掉；`bank_rules` 拒绝活动容器进共享银行。
- 不取同归档的 `world_buff_messages` / `world_elixirs` / `elixir_flow` / `elixir_peer_sync`：它们要 `activity2026_awards.world_rows`/`world_stamp`，本树的 `activity_2026_rewards` 没有这两个方法，装了也不会产生 `_boosting` 行。
- 仍未取的大件：`abyss_weapon_2026`（7 文件）、`quick_start`（5 文件），以及 `careers`(719707 大师转职映射)、`decomposition_rules`/`paid_enhancement`(深渊武器排除)、`first_story_entry`(快速开始参与判定) 这几处钩子。
- 既有失败（与本次无关，HEAD 上一致）：`test_item_expiration.test_move_preserves_uid_deadline_and_periodic_notices` 期望只有 `[0x1c6]`，实际多出 `0xc23`/`0x214`；`test_inventory_rewards.py` 模块级断言「满包必须拒绝」因背包扩容失效；`test_fashion_bundles` 一次建 15 个角色撞每日 4 个上限。

## 9d. 已执行（2026-11-05 21:55 起，第四批：百宝袋）

| 提交 | 内容 |
|---|---|
| `079391e` | `modern-ice-sale-window` + `cubes-points` + `cube-native-open` + `withdraw-request` 四连：挫宝机奖励进百宝袋，BD3 领取 |

**根因**：百宝袋（挫宝机奖励袋）整块功能从来没有进过树——`els_server/domain/modern_ice_flow.py` 连文件都不存在。玩家点「领取」时原生发的是 **0xBD3**，旧服务端把 **0xBD4**（回包）当请求入口，所以请求根本没进提取事务；同时挫宝机奖励走的是 `ice_state.draw` 的旧路径，直接塞进背包，百宝袋永远是 0/400。

- 7 个新增文件：`data/modern_ice.json`(995KB，154 机器 / 720 箱子 / 874 定义)、`domain/modern_ice.py`、`domain/modern_ice_flow.py`、`protocol/modern_ice_messages.py`、`storage/modern_ice.py`、`domain/ice_rules.py`、`protocol/ice_messages.py`（后两个是「树正好停在父版本」，可整文件装）。
- 手改 6 处：`domain/local_session.py`（BD3 分发、现代容器预览/路由、冰装预览与抽取的百宝袋快照、登录 BD8 恢复）、`storage/ice_state.py`（现代机器入袋 + 积分累积）、`application.py`（code529 期间表）、`protocol/activity_2026_entries.py`（`periods`）、`storage/equipment_receipt_state.py`（`0xbd4`）、`domain/cubes.py`、`storage/fixed_cubes.py`、`domain/inventory_items.py`（874 条模板注册）。
- **0xBD6 是共用操作码**：树里它是背包整理，归档里它是百宝袋整理。`handle` 先判 `s.ice_test`，没有冰装子系统就 `return None` 让回老的背包提供者，避免抢包。
- **账号作用域**：`modern_ice_bag.account_id` 非空，所以 `ice_state.draw` 只有在调用方给了账号身份时才入袋；不给（测试/工具直连）仍走 owner-local 分配。生产路径由 `selected(self)` 保证一定给。抽取分支也按「该机器是否属于现代家族」分流，老机器行为完全不变。
- **不需要迁移**：`modern_ice_points` / `modern_ice_bag` 由 `ensure(db)` 首次使用时建表，`bag_items`/`point_balance` 都带 `exists()` 守卫。
- 既有失败（HEAD 上同样失败，非本次引入）：`test_ice_draw`（'last' 重放不等）、`test_shop_ice_flow`、`test_role_ice`、`test_consumable_actor_lifecycle_current`、`test_native_ice_catalog`（`len(POOLS)==137` 与现代机器数不符）。`test_ice_session` 改用老机器 `163362` 保持路由覆盖，另新增 `tests/test_modern_ice_bag.py`（10 项）证明入袋、重放不重复发、BD3 提取回背包、BD4 不是请求入口、坏 payload 回 -1。

## 10. 下一步（更新）

1. **重启后实测**：`980047`（玩家点了 4 次都 `code=-1` 的那个）、四个 Boost 箱子、各卷轴家族（强化 / 祝福复原 / 贤者 / 炼制 / 挑战初始化）。以上全部只在本机临时存档验证过，没有一次是真的客户端点开。
2. **`three-activities-startup` 剩余两件大功能**：`abyss_weapon_2026`（code580，7 个新文件 + `decomposition_rules`/`paid_enhancement`/`fixed_cubes` 钩子）、`quick_start`（code578，5 个新文件 + `first_story_entry`/`careers`/`application` 钩子）。这两个都要动 `local_session.py`（146KB，162 行漂移）与 `session_dispatch.py`（161 行漂移），必须逐 hunk 三方合并，不能整文件覆盖。
3. **`identification_ui.json`（`975267cf…`）**：`native_templates`/`native_pools` 那份表不在任何归档里，要从持有该表的运行端取；拿到后 `domain/identification_ui.py` + `storage/identification_ui.py` 才能装。
4. A 组：`native-guild-reviewed`(109)、`native-independent-closures-v4`(62)、`native-photo-zone`(22)、四个写锁类。
5. C 组 `pve-experience`(9)。
6. **活动到期是硬截止**：`local-growth.json` 的 `configuration.ends = 1796004000`（2026-11-30 10:00）。到点后 `EVENT_ITEMS` 里那些活动容器/激活券会在登录时被清掉（原生行为）。要保持开放就改这个值，别改代码。
7. 注意：本仓库当前**有另一个会话在并发编辑** `quest_flow.py` / `el_search_collection*` / `artifact_flow.py` / `session_dispatch.py` / `character_custom.py`。提交时务必按路径 `git add`，不要 `git add -A`，不要 `git stash`。


## 11. 定制道具（0x219 定制书）

- **症状**：`街头合奏表演吉他-白（艾索德定制）` 之类定制道具，客户端弹「确定要使用吗？」，点确认后道具不消失、定制不出现。
- **根因**：原生 C595C0 的 0x219 定制书请求是 **29 字节 `>QQiiIB`** = `UID + custom_id + family + 高亮 socket + 两个填充 0`（27E0F10）。旧 `career_messages.use_request()` 只取 UID 而且要求 `target==0`，客户端却一定把 custom_id 填进去 → 每一本真书都在解析阶段就被拒，回 `0x21A result=-1`，客户端只表现为「没反应」。
- **修复**：`storage/character_custom._book_request` 按 `>QQiiIB` 解析并校验 `(custom_id,family)==(rule['custom_id'],rule['type'])`（客户端只能声明这本书真正给的那个定制，socket 只是高亮位不作准）；`domain/character_custom` 的角色限制由 `{1}` 放宽到 `ALL_UNITS=1..15`，`COUNTS` 合计 3200，新增 `BOOK_COUNT=3200`；`data/character_custom_permanent.json` 由 752 本扩到 **3200 本**（加入 `merged_all_units` / `hyper_effect` 等来源）。
- **载荷核对**（真实日志 → 目录，三条全对）：`451208 → custom 1000073 / family 15`、`450319 → 54090 / 7`、`311328 → 14107 / 7`。
- **测试**：修好被新契约打断的 `tests/test_character_custom_apply.py`（`use_payload` 必须带 custom_id/family）与 `tests/test_character_custom_opening.py`（夹具补 `client_build/item_test/role/phase/characters` 并 patch `current_lease`，因为 `panel_admitted` 现在会重查租约）；新增 `tests/test_character_custom_all_books.py`。
- **验证**：3200 条规则 `canonical/custom_type/slot_value` 全通过、custom_id 全目录无重复；艾索德可持有 **299 本逐本 `use_book` → 299/299** 成功（`0x21A + 0x4CD`）；family 1/2/3/7/15/24 注册后 `0x4CB` 应用全部 `code=0`。
- **注意：必须整体重启服务端**。线上库 `inventory_action_receipts` 里一条 `custom-book` 回执都没有，说明跑着的进程还是改前的代码。`state/hot-reload.json` 里没有 `character_custom`，而且 `hot_reload.watch()` 只在启动时读一次名单，所以改名单也没用。
- **范围说明**：165 本 `native_only`（只存在于原生 CharCustomData 表、没有背包书）不能靠书获得；其他角色的书受道具记录 `raw[210]/raw[211]` 的原生职业掩码限制，是正确行为，不应放宽。

### 11b. 更正：真正的阻断点是 0x219 的分发顺序

上一节的「服务端还是改前代码」判断有误。用 `__pycache__/*.pyc` 内嵌的源 mtime/size 比对，`character_custom`（21:58/21:59）、`local_session`（22:11）、`session_dispatch`（22:06）**全部 MATCH**，进程确实加载了新代码。

`local_session` 处理 0x219 的顺序是 **容量券 → ERP 共鸣书 → 永久定制书**。而 `storage/resonance_state.use_book` 第一句 `use_request(payload)` 用的是 `career_messages.use_request`，它要求 29 字节里 UID 之后**全部为 0**；定制书把 `custom_id` 填在 target 位 → 抛 `Unsupported career item use parameters` → `local_session` 的 `except ValueError: return [use_ack(result=-1)]` 立刻收场，定制分支一次都没执行过。这就是「一本自定义书都用不了」的唯一原因。

- **修复**：`storage/resonance_state.use_book` 把 `use_request` 包进 `try/except ValueError: return None`——不是这一族就交棒，别替别的族回 -1。
- **证据链**：同一份存档副本上依次调用三个消费者，修前 `None / RAISES / [0x21a,0x4cd]`，修后 `None / None / [0x21a,0x4cd]`。
- **道具对号**：截图里的「街头合奏表演吉他-白」是模板 **311328**（`custom_id 14107 / family 7`，owner 1001），不是早先误认的 451208（那是「觉醒：隐约的鬼火」）。日志 23:12:55 / 23:13:25 的载荷正是它。
- **回归**：`tests/test_character_custom_all_books.py` 增 `DispatchOrderTests`——容量券与共鸣书必须对定制书请求返回 `None`，之后定制书仍要能回 `[0x21a,0x4cd]`。
- **既有失败**：`tests/test_declining_consumers` 19 个。A/B 跑 HEAD 版与新版本都是 19 个；夹具的 payload target=0，新加的 try/except 在那里是空操作，与新改动无关。

## 12. 副本「门不开 / 图过不去」——先加诊断（未定论）

- **日志事实**：`state/wire-debug.log` 里 `0xad`（怪物死亡）到 **23:17:57 归零**，之后只有 `0x3e6` 位置同步，**再没有一次 `0xb8`（请求传送门）**。说明客户端根本没机会点门——门没开，不是门开了不给过。23:20:03 的 `0x85+0xa0+0x67+0x3e9` 是玩家退出重进。
- **开门的唯一路径**：`dungeon_flow.periodic()` → `run.poll_ready()` 为真 → 发 `part_end_notice`。而 `poll_ready` 依赖 `condition_ready(c)`，其中 `kind in (1,2)` 的判据是 `keys=[n['key'] for n in npcs if n['key_code'] in c['required']]` 再 `bool(keys) and all(k in dead for k in keys)`。**`keys` 为空时该房间永不开启**——正是「怪清完了门不开」的形态（`pending=[]` 却 `NOT-READY`）。
- **已加诊断**（`domain/dungeon_flow.py`，不动判定）：`_trace/_pending/_slow` 写 `state/dungeon-debug.log`。
  - `periodic` not-ready 分支（3 秒节流）一次输出 `stage/part/visits/pending`、全部 `npcs(key,key_code,template,active,team)`、`defeated`、以及每条 condition 的 `kind/required/next/ready`；
  - `0xb8` 输出 `payload/part/synced/valid/late/pending`；
  - `0xbb` 输出四条早退原因：`MISMATCH` / `NOT-NOTIFIED` / `BLOCKED by story controller` / `NOT-READY`。
- **暂不改 `condition_ready`**：它决定所有副本的路由，等日志证明是「`required` 的 key_code 不在 roster 里」还是「有一个怪客户端没刷出来」再动。
- 回归：`test_dungeon_clock` 通过；`test_complex_dungeon_routes`/`test_dungeon_lifecycle` 缺 `analysis/client-6c6b5180/20261013-160720/death-event-header.json`，`test_dungeon_actions` 缺 `verify_dungeon_actions` 模块 —— 都是本机既有缺口。


## 13. 定制书 0x219：链路已通（含线上实证），注册丢失来自库被回写

**代码侧（已改）**
- `els_server/storage/resonance_state.py::use_book`：0x219 是共享信封，定制书把授予的 custom 填在 target 位，
  `use_request()` 会拒绝。原来这里直接抛 `ValueError`，`local_session` 捕获后 `use_ack(-1)`，定制分支永远跑不到。
  改为 `except ValueError: return None`，把请求让给下一个家族。
- 诊断埋点（`state/custom.log`，均在 `session_dispatch._live()` 热重载名单内，改完无需重启）：
  - `domain/character_custom.require_admitted`：拒绝时记录 `build/item_test/role/phase/characters/store/lease`；
  - `storage/character_custom.use_book`：入口 `book store enter`、静默让位 `book store declined`、成功 `book store committed`；
  - `domain/local_session` 0x219 段（需重启生效）：会话闸门、容量券、共鸣书、定制书四处决策点。

**验证**
- 真库副本回放 `uid=1001077 / custom=14107 / type=7`：`character_custom_permanent` 写入 `(1001,14107,311328)`、
  `inventory_action_receipts` 写入 `custom-book:…`(kind 537)、物品从背包删除、总数 249→250。
- 线上 `state/custom.log` 累计 **601 次** `book store committed`，含用户截图那本
  `23:48:14 book store committed uid=1001077 custom=14107 template=311328`；仅 1 次正常让位（`template=276290` 非定制书）。

**未解决项（非代码）**
- 注册未落库：23:46 客户端在用 uid 1001291-1001299，而当前所有 sqlite 的 `max(inventory_items.uid)` 只有 1001235。
  `_refile.sqlite3`(23:49:03) / `_filing.sqlite3`(23:47:13) 为同尺寸工作副本 →
  **refile 类工具在 23:47-23:50 用旧快照回写了 `development.sqlite3`**，把注册和已消耗的书一起冲回。
  需要先停掉这类工具再复测，否则每次结果都会被还原。

## 12. 已执行（2026-11-06 00:30~01:00 第二批）

| PR | 内容 | 落地方式 | 验证 |
|---|---|---|---|
| #879 | 冰装分解固定 45 个未鉴定艾尔结晶(130047) | 新 `domain/ice_decomposition.py`（46 行）+ `decomposition_rules` 两处钩子；走既有 0x1C0 事务 | 真实库存 10 件全部报价 45；DB 副本端到端 2 件 → 90 个，回执写入 |
| #869 | 家具保存写锁后核对家园到期 | `housing_layouts.save` 的 `stamp` 移进 BEGIN IMMEDIATE/guard 之后 | 与归档 source 逐行一致 |
| #874 | 协同票券写锁后核对期限 | `el_search_collection_tickets.use` 同上 | 同上 |
| #872 | 邮件写锁后核对到期 | `game_mail.read/claim/delete` 三处 `now` 移进事务 | 邮件三套测试全绿 |
| #873（部分） | 公仓写锁后核对到期 | `guild_bank_items.perform` 的 `stamp` 移进事务 | — |
| #771（分解部分） | `decompose` 编码器改为调用时解析 | `encode=None` + 函数内兜底 | `test_full_material_bag_and_encoder_failure_roll_back_equipment` 由红转绿 |

前置核对：#879 需要的 `role_ice_catalog()`（11537 条 group27）、130047 登记（verified=2/group4/999）、`item_deadline()` 本树全都在，所以只新增 1 个文件。

未装及原因：

- **#873 的宠物远征两文件**（`pet_expedition_flow.py` / `pet_expedition.py`）：本树没有任何 `pet_expedition` 调用点，宿主（market-progress 父树）不在，装了是死代码。
- **#875 成长指南箱**（`growth_guide_boxes.py`）：同上，宿主缺失。
- **#877/870 公会全量**（46 新文件 + 59 处合并）：动 `local_session.py`/`session_dispatch.py`，必须逐 hunk 三方合并，单独一轮。
- **#871/868 摄影棚、#880 玩家交易、#881 聚合**：都要第二个人进服才看得见效果，且 #881 内含 #879 与 #880 子集，冲突面大。
- **#876/#867**：归档里没有源码差异，不需动。

既有失败（非本次引入，已用 stash 验证）：`test_bag_capacity` 2 项（六件/七件扩容夹具仍是旧 350→300 ED 口径）、`test_force_guild_contract` 1 项。
