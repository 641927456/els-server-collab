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

## 10. 下一步（更新）

1. **`scroll-families` 实测**：重启后逐个卷轴点一次（强化卷轴 / 祝福复原 / 贤者 / 炼制 / 挑战初始化），确认扣物与回执。
2. **`identification_ui.json`（`975267cf…`）**：`native_templates`/`native_pools` 那份表不在任何归档里，要从持有该表的运行端取；拿到后 `domain/identification_ui.py` + `storage/identification_ui.py` 才能装。
3. B 组剩余：`promotion-fashion-bag`(7) → `three-activities-startup`(68) → 商城/戒指/掉落（后者多数已在树内）。
4. A 组：`native-guild-reviewed`(109)、`native-independent-closures-v4`(62)、`native-photo-zone`(22)、四个写锁类。
5. C 组 `pve-experience`(9)。
6. 注意：本仓库当前**有另一个会话在并发编辑** `quest_flow.py` / `el_search_collection*`（收集册 52700 登陆恢复）。提交时务必按路径 `git add`，不要 `git add -A`。

