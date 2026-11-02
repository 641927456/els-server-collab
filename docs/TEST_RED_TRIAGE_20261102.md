# 84 条红测试的定性分诊（2026-11-02）

门禁 `python tools/run_release_tests.py release-tests.json --server` 当前报
389 条 / 23 失败 / 61 错误 / 1 跳过。本文把这 84 条（23+61）逐条归位，回答一个问题：
**哪些是"代码真有毛病"，哪些只是"跑不了"或"测试过期"。**

结论先说：**29 条根本跑不起来（缺夹具/缺工具/缺子进程）**，**26 条是测试过期（API 或约定变了）**，
**剩下 29 条需要逐条复核，其中 4 组有真 bug 嫌疑**。真正"可能影响玩家"的集中在最后那 4 组。

> **复核进度（11-02 晚已更新）**：4 组"最像 bug"的 12 条**全部复核完毕，无一属实**。
> 组 1/组 2 是「999 堆叠 + 商品 6 件变 7 件 + 测试专用函数」的过期断言，
> 组 3 是校验器正确而测试没按新信封发包，组 4 是称号首帧同步 / 测试自己发 Epic 跳过标志 /
> `retire` 半落地通道。逐条证据见各组小节末尾的「复核结论 / 逐条证据」。

## 一、跑不起来：29 条（与代码质量无关，但也没被验证）

### 1. 缺 `analysis/` 抓包夹具：13 条

这些模块在 **import 阶段**就读 `analysis/client-6c6b5180/...` 或 `analysis/runs/...`
（Git 忽略的 837 MB 夹具，新 worktree / 换机器时不会带过来）：

`test_challenge_flow`、`test_complex_dungeon_routes`、`test_dungeon_routes`、
`test_dungeon_spawns`、`test_el_tree_loot_flow`、`test_ground_loot`、`test_local_session`、
`test_local_state`、`test_seal_level_flow`、`test_session_inventory`、`test_summons`，
以及 `test_inventory_restore_and_drops.test_inactive_chest_spawns_once_without_advancing_clear`、
`test_region_quest_flow.test_all_thirteen_tasks_via_admitted_dungeon_sessions`。

判定：**环境缺件**。补回 `analysis/` 后这 13 条才谈得上判定。注意「跑不了」不等于「没问题」——
这 13 条覆盖副本路线、掉落、召唤、会话状态，是实打实的功能区。

### 2. 缺 `tools/audit_enchant_equipment.py`：2 条

`test_normal_equipment` 的两条。该工具从未入库（`tools/` 下没有），测试 `import` 就失败。
判定：**工具缺失**，补工具即可跑。

### 3. 测试夹具状态：今日建角额度用尽：4 条

`test_characters`、`test_fashion_bundles`（import 期）、
`test_role_progression.test_creation_15_roles_replay_equipment_and_reopen`、
`test_skill_unlocks.test_actual_consumption_all_15_roles_and_...`。

报错都是 `LifecycleError: Daily character creation limit`——`character_lifecycle.check_creation`
统计该账号当天的建角数已到上限。测试会复制一份存档再建角色，存档里今天已建满。

判定：**夹具状态**。顺带暴露一件事：这批测试**依赖真存档里的角色数量**，
连续跑测试会把额度耗光，第二天自己就好了。

### 4. 子进程起不来：10 条

`test_friends_server` 7 条 + `test_registration` 3 条，全是 `SystemExit: 1`——
测试会用子进程拉起一个便携版服务端，子进程退出码 1。单跑这些模块时
`test_friends_server` 的 12 条里有 11 条是过的，说明是**门禁单进程环境**下的问题
（端口/资源/环境变量），不是代码。

## 二、测试过期：26 条（实现有据可查，测试还按旧约定）

### 1. `inspect_request()` 缺 `profession_state` 参数：9 条

`test_manufacture_requirements` 全部 9 条。测试调用
`inspect_request(payload, items, now=..., profession_state=state)`，而实现签名是
`inspect_request(payload, items, *, now)`——**本地树和 `accepted-runtime-20261026-v1` 归档里
都是这个签名**，也就是说测试期待的 API 从来没交付过（属于「从未入库的模块」那一类）。

判定：**测试针对未交付的实现**。要么补实现（职业校验先于背包预检），要么把测试标记 skip。

### 2. 角色 ED 携带上限：9 条

`test_npc_trade` 8 条 + `test_npc_sale` 1 条，报错 `Sale exceeds character ED carrying limit`。

根因：测试 `fund()` 先给 1 级角色塞 **1,000,000 ED**，而
`bank_rules.player_ed_limit(1)` = **500,000**。角色早就超上限了，再卖东西当然被拒。
实现里的上限来自 `player_limits()` 数据表，注释还标了客户端地址
（`2C5C6D5..2C5C7DA` 用 service+480 的等级上限），是有据可查的行为。

判定：**测试前提不成立**（低等级角色不该有 100 万）。

### 3. 会话时钟包长：1 条

`test_session_clock.test_wire_fields_and_millisecond_boundary` 断言 48 字节，实际 86。

`els_server/protocol/session_clock.py` 的注释写得清楚：客户端 `13966E0` 先读一个宽字符串，
再读三个 int64、uint32、两个 int64。实现已经改成「真实日期字符串 + 44 字节数字」，
测试还是「空字符串 + 44 字节」时代的断言（模块注释里那句
"the former zero fixture hid this" 就是在说这次变更）。

判定：**测试过期**（实现是后改的、有依据）。

### 4. 回复码约定：7 条

`test_bag_ui_moves`、`test_equipment_moves`、`test_potion_moves` 3 条、
`test_friends_character_creation` 2 条，以及 `test_fashion_moves`（import 期一条）。

同一个形状：测试断言回复末 4 字节是 `0`（成功）或 `-1`（拒绝），实际是 `1`。
`local_session.py:1235` 写的是 `move_ack(result=2005 if ... else 1)`——
本地约定是**成功 1 / 拒绝 2005**，与测试的 0/-1 不同代。

判定：**约定换代**。需人工确认客户端对 `1` 的接受度（游戏里移动物品是正常的，
说明客户端认，但要确认拒绝分支 2005 是否被客户端正确显示）。

## 三、需要逐条复核：29 条

按现象分组，**前 4 组是真 bug 嫌疑，建议优先**。

### 组 1｜「该拒绝的没拒绝」：4 条 —— **已复核，四条全是否警报，没有白嫖口子**

| 测试 | 现象 | 复核结论 |
| --- | --- | --- |
| `test_decomposition.test_full_material_bag_and_encoder_failure_roll_back_equipment` | 材料背包满了，分解应拒绝，实际通过 | **测试过期**：999 堆叠，36×99 只占 4 格 |
| `test_equipment_repair_transaction.test_unverified_discounts_are_never_authorized` | `dict(unit_type=10)` 应拒绝 | **测试过期**：空 LuCiel 无折扣；该函数无生产调用点 |
| `test_paid_enhancement.test_bad_packets_...` | `request()` 放过 `mode=1` / `b=1` / `d=1` | **测试过期**：`request()` 无生产调用点，生产走 `options()` |
| `test_paid_enhancement.test_no_stone_...` | `enhancement=8` 应拒绝 | **测试自相矛盾**：同模块另一条测试遍历 13 级概率表 |

逐条证据：

1. **分解那条**和组 2 同源。探测：连塞 36 次 `135983 × 99`，实际只占 **4 格**
   （`LOCAL_MAX_STACK=999`，3564 = 3×999 + 567），材料背包**根本没满**，
   分解当然成功。不是「分解不收材料」。
2. **修理那条**逐个试探 5 个用例，只有第一个不抛：

   | 用例 | 结果 |
   | --- | --- |
   | `dict(unit_type=10), []` | 返回 `1.0`（没抛） |
   | `title=760` | 抛 `Incomplete title character` |
   | `repair_buffs=[202]` | 抛 `Buff repair pricing pending` |
   | `template=711611, group=4` | 抛 `Unsupported repair pass instance` |
   | `template=130261, group=9` | 抛 `Repair context is not baseline` |

   也就是只有「空的 LuCiel 角色」这一例。而 `require_baseline()` 在整个仓库里
   **只有测试调用，零生产调用点**（生产走 `character_quote → multiplier`，
   后者对双角色按 `price_side` 正常分流）。空角色没有任何装备，折扣本来就只能是
   1.0，拒绝它反而会误伤。**无玩家影响。**
3. **强化畸形包那条**：`request()` 只取 `uid, context`，丢了 `mode/b/d`，
   所以 `mode=1`/`b=1`/`d=1` 都被放过。但 `request()` 同样是**测试专用**，
   生产是 `enhance() → options()` 直接解析。实测生产路径：

   ```
   mode=1（等级 0）→ Enhancement mode level mismatch
   b=1 锤子标志   → Missing enhancement stone or fluorite material
   d=1 自动恢复   → Missing available automatic restoration scroll
   ```

   `enhance()` 里 `if mode in (1,2)` 要求背包有 `ore_templates`/`crystal_templates`，
   `if hammer` 要求有 `hammer_templates`——**锤子/矿石/恢复卷一个都白嫖不了**。
4. **`enhancement=8` 那条**：`quote()` 认为 +8 是合法的（`RATES` 13 行，
   文档字符串写明 "through +13"），而同一测试模块的
   `test_rate_boundaries_and_level7_down_and_reset` 正好遍历这 13 级并断言
   每级概率和为 10000。**同一文件里一条测试要 +8 合法、另一条要 +8 非法**，
   说明「拒绝 +8」是概率表从 8 行扩到 13 行之前的残留断言。
   归档 `references/accepted-runtime-20261026-v1` 里的 `RATES` 也是 13 行，
   等于上游同样会挂这条。

结论：**四条都不需要改实现**。真要动，是删掉 `require_baseline`/`request`
这两个无调用点的僵化辅助函数，或者按 999 堆叠与 7 件商品修正测试预算。

### 组 2｜背包容量没兜住：2 条 —— **已复核，两条都是测试过期，不是 bug**

- `test_bag_capacity.test_new_slots_are_usable_and_unowned_slots_rejected`：**已证伪**。
  探测脚本连发 38 次 `grant_items(77000 × 99, group=6)`，实际只占 4 格：第 11 次
  从槽 0 溢到槽 3，第 37 次溢到槽 4、第 38 次溢到槽 5——**都在 36 格以内，从未越界**。
  原因是测试假设堆叠上限 99，而本地 `LOCAL_MAX_STACK=999`、
  `TEMPLATE_MAX_STACKS[77000]=999`，同一物品会并进已有堆。测试里「第 37 次应抛
  `InventoryFull`」的前提不成立。附带确认 `load_items` 对超界槽位（`slot=76`）
  **正确抛** `ValueError: Item exceeds owned bag capacity`，兜底是好的。
- `test_bag_capacity.test_six_products_character_isolation_restart_and_wire`：**已证伪**。
  `PRODUCT_GROUPS` 现在是 **7** 项（`200751..200756` 六件 + `135964:21` 生命扩容），
  每件 50 ED，总价 **350**，`100000 - 350 = 99650`——测试仍按 6 件（300）写，
  所以期望 `99700`。复现脚本确认购买后
  `bag_capacities == {1:44, 2:44, 3:44, 4:44, 5:44, 6:44, 21:44}`，
  测试断言的 `{g:44 for g in range(1,7)}` 同样少了 group 21。两条断言都是商品
  从 6 件扩到 7 件后没跟着改的脱节，扣款与扩容本身算得对。

（`test_inventory_rewards` 的 `Full bag grant accepted` 同源，也是堆叠 999 导致。）

### 组 3｜初始化信封被自家校验拒：3 条 —— **已复核，校验器是对的，测试没按新信封发包**

`test_quick_slots`、`test_saved_economy_initialization`、`test_skill_state`，
报错 `SessionOrderError: Invalid character initialization envelope`。

校验条件（`local_session.py` 0x28 分支）：

```python
if (event.performers!=(0,) or event.uid!=2**64-1
        or event.target_uid!=2**64-1 or event.payload_mode!=0):
    raise SessionOrderError('Invalid character initialization envelope')
```

三个测试都写的是 `Event(0x202,kind=0x28,payload=...)`，而 `Event.performers`
默认是 `()`，不是 `(0,)`。**这是有意收紧的**：`test_current_latency_tls.py`
里专门有一条 `bad=Event(0x202,kind=0x28,payload=...,performers=())`
在断言这种包必须被拒。`test_guidebook.py` 用的就是 `performers=(0,)`，能过。

补上 `performers=(0,)` 后再跑，三条各自露出**第二层**的旧账：

| 测试 | 补信封后 | 性质 |
| --- | --- | --- |
| `test_quick_slots` | 4 条里 3 条过，1 条抛 `Chip reset trusted local actor` | 测试手工建的 `LocalSession` 没挂 `_chip_reset_local_application`/`_chip_reset_local_live`（`application.py` 才会挂） |
| `test_saved_economy_initialization` | `TypeError: 'NoneType' object is not subscriptable`（`local_session.py:1572`） | 测试从未 `enable_characters()`，`account.character()` 是 None |
| `test_skill_state` | 同上 | 同上 |

关于「角色投影为 None」：`account.characters is None` 才会返回 None，而
`Application` 在 `profile=='integrated_dx11'` 时**必定**调 `enable_characters()`
（`application.py:254`），且只有非 bootstrap 的 profile 才给
`enter_town=True`（`config.session_options()`）。所以「有人物选择阶段 +
没启用角色表」在生产里不可达，只有手工拼 `LocalSession(..., enter_town=True)`
的老测试会撞上。

顺带记一笔**可加固点（非 bug）**：0x28 分支在取 `character['unit_type']` 前
没有判 None。生产不可达，但如果哪天 profile 组合放松，这里会从
`SessionOrderError` 退化成 `TypeError` 裸崩。加一行 `if character is None:
raise SessionOrderError(...)` 更稳。

### 组 4｜事件条数不符：3 条 —— **已复核，2 条是「少了不是多了」+ 1 条测试自己发错包**

原先写成「多发」，逐条对照后方向反了：

**① `test_item_expiration`——确实多发，但多的是新增的称号首帧同步**

实际 `[454, 3107, 532]`，期望 `[454]`。多出来的是
`title_messages.initialization`（0xC23=3107，称号任务面板）和
`title_messages.equipment`（0x214=532，当前佩戴称号）。来源是
`title_flow.periodic()`，它有脏检查：

```python
previous=getattr(s,'_title_active',active)          # 首帧 previous==当前
previous_owned=getattr(s,'_title_owned',None)       # 首帧 None != owned → 发一次
```

也就是**只在第一次往世界里推一次全量称号同步，之后永久静默**。测试里紧接着的
`assertEqual(s.periodic_notifications(),[])` 本来就是验证这一点，只是期望列表
没跟着称号系统更新。把期望改成 `[0x1c6,0xc23,0x214]` 后该模块 5 条全绿。

**② `test_region_quest_flow`——不是多发，是测试发了一个「Epic 跳过」标志**

实际 `[245]`，期望 `[245, 43, 1371]`。抓内部异常得到：

```
QuestState.action → epic_skip.reward → ValueError: Epic skip source/level/After requirement
```

原因：测试的领取包写的是 `struct.pack('>iiI5B',qid,10025,0, 0,1,1,1,0)`，
五个 bool 是 `(0,1,1,1,0)`；而 `epic_skip.requested()` 的判定正是
`flags[1]==1`。也就是说**测试自己在说「我要跳过这个 Epic 任务」**，
然后把 `m_iFairLevel=99` 的角色（等级也是 99）的跳过请求发给服务端——按
`level-fair<=5` 的原始规则，恰好差 0 级，**服务端拒绝跳过是正确的**。

把五个 bool 改成 `(0,0,1,1,0)`（普通领取）后，领取立刻成功：

```
实际 [245, 43, 240, 240, 1371]   期望 [245, 43, 1371]
```

多出的两个 `0xf0`(240) 是 `wire.accepted(...)`，即领取 26640 后按
`m_iAfterQuestID` 自动接下的两个后续任务。所以这条测试真正的偏差是
**期望列表没算自动接取**，而「该拒绝没拒绝 / 多发未知包」都不是实情。

**③ `test_seal_quests`——不是多发，是**少了**一条，而且是一条半落地通道**

实际 `[]`，期望 `[0xf3]`(243)。测试用
`record('retire', 35250, npc=9470, tutorial_quest=28110, retired_by=9310)`
期望把 28110 的第一步「击杀 9470」结算掉。但 `inactive_increment` 的门槛是：

```python
event.get('kind')=='kill'   # ← 测试给的是 'retire'
```

查生产侧：`kind='retire'` / `retired_by` 这两个字段**只在
`storage/seal_quests.record()` 的白名单里出现，没有任何代码产生这种事件**，
`inactive_increment` 也不认它。也就是说「终章分控制器退役」这条通道
**只落了 schema，没落规则也没落生产者**。

玩家影响判定：**目前为零**。因为 28110 的第一步走 `kill` 路径是通的
（`inactive_quest(35250,9470)==28110`，目标要求 clearType=2 / killNum=1 /
killNPC=9470 / dungeon∈{35250,35251}，全部对得上），杀怪就能推进。
配套的 `test_unqualified_retire_event_cannot_fabricate_finale_progress`
之所以一直是绿的，是因为**任何 retire 事件都不会推进**，它属于「空过」。
要收尾，就是给 `inactive_increment` 加一条 `retired_by==9310` 的等价分支，
或者干脆把 retire 从白名单里删掉，别留悬空字段。

### 组 5｜计数不符 / 其他：7 条

- `test_expansion_items`：`2 != 1`（扩展道具数量对不上）
- `test_friends_character_creation` ×2：`1 != 0`（建角后数量对不上）
- `test_friends_server.test_four_member_capacity_and_loading_timeout`：`0x8b0 != 0`（同前，单独跑是断言失败）
- `test_region_quest_flow.test_session_refuses_locked_map_...`：`False is not true`
- `test_role_progression.test_full_bag_defers_old_kit_...`：字符串整体 diff（`++++`）
- `test_inventory_restore_and_drops.test_actual_clear_end_then_town`：
  `'NoneType' object has no attribute 'get'`（取角色投影拿到 None）

### 组 6｜模块级断言：10 条

`test_careers`（`periodic_notifications()` 不再是空列表）、
`test_ed_shop`（商店全量 ack 不一致）、`test_extended_shop`（报价条数公式不符）、
`test_fashion_moves`（同回复码问题）、`test_inventory_rewards`（**满背包仍可发放**）、
`test_role_ice`、`test_shop_entry_protocol`、`test_shop_supplements`、
`test_dungeon_session`（`character` 为 None）、`test_persistent_endpoint`（JSON 解析失败）。

其中 `test_inventory_rewards` 的 `AssertionError: Full bag grant accepted` 与组 2 同源。

## 建议的下一步（按玩家影响排序）

**四组"真 bug 嫌疑"已全部复核完毕，结论：12 条里 0 条是保证玩家受损的 bug。**
- 组 1（4 条「该拒绝没拒绝」）→ 全是否警报，两条是 999 堆叠/商品从 6 件变 7 件的过期预算，
  两条挂的是**没有生产调用点的测试专用函数**。详见上文各组小节。
- 组 2（2 条背包容量）→ 全是否警报，同上。
- 组 3（3 条初始化信封）→ 校验器是对的，测试没按 `performers=(0,)` 发新信封。
- 组 4（3 条事件条数）→ 1 条是称号首帧同步、1 条是测试自己发 Epic 跳过标志、
  1 条是 `retire` 半落地通道（玩家可用 kill 路径推进，暂无影响）。

剩下可做的，按性价比排：

1. **修测试（不需要动实现，纯赚）**：`test_bag_capacity` 两处预算按 7 件商品 / 999 堆叠改，
   `test_decomposition` 的「填满背包」改成按 `LOCAL_MAX_STACK` 循环填到 `InventoryFull`，
   `test_item_expiration` 期望加 `0xc23,0x214`，`test_region_quest_flow` 五个 bool 改 `(0,0,1,1,0)`
   并把自动接取的 `0xf0` 算进期望，`test_quick_slots`/`test_skill_state`/`test_saved_economy_initialization`
   补 `performers=(0,)` 和 `enable_characters()`。
2. **删悬空代码**：`repair_pricing.require_baseline`、`paid_enhancement_messages.request`
   全仓库零生产调用点，只服务于过期断言；`record()` 白名单里的 `retire`/`retired_by`
   既无生产者也无规则，要么补 9310 分支要么删。
3. **回复码 / 时钟 / ED 上限 / manufacture API**（26 条测试过期）——决定是改测试还是补实现，
   其中 manufacture 的 `profession_state` 是唯一「可能要补功能」的一项。
4. **补 `analysis/` 与 `tools/audit_enchant_equipment.py`** 后再看那 15 条（本轮新增 1 条：
   `test_region_quest_flow` 里的 `death-event-header.json` 也在缺件之列）。

本轮只读不写：没有为解决任何一条改动运行代码（临时探针脚本已全部删除）。
