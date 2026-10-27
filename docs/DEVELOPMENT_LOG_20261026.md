# 开发文档 · 2026-10-26 本轮修复

> 2026-10-27 仓库核收说明：本文由原 PR #547 仅以一份历史日志提交，
> 未随附下列 26 个文件的代码增量，索引中的五份专项文档也未在本仓库提交。
> 因此本文保留的是作者当时的候选及验证叙述，不能据此认定六项已合入当前主干、
> 已正式安装或已通过自然实机验证。各项实际状态须核对应源码与独立交付回执。
> 尤其第五节的装备曲线相对缩放属于历史候选：当前主干已采用用户批准的
> [公开成长规则基础输入](CHARACTER_BASE_INPUTS_20261026.md)，
> 不能把本文的候选推导称为已还原当前客户端原生裸装成长公式，
> 也不能按文末历史恢复方式删除当前正式规则。

**基线**：`b3688a0`（2026-10-26 14:12）
**范围**：19:25–22:24 的六组修复，26 个文件（12 代码 / 8 测试 / 5 文档 / 1 工具）
**性质**：只记录本轮改动，不重复更早的批量修复（见 `DEVELOPMENT_LOG_20261025.md`）

## 索引

| # | 主题 | 专项文档 |
|---|---|---|
| 1 | 快捷栏 412 完全恢复药水 | `FULL_RECOVERY_POTION_SHORTCUT_20261026.md` |
| 2 | Memory8 终点房 | `LITHIA_MEMORY8_FINALE_DOOR_20261026.md` |
| 3 | 34140 裂隙控制器退场 | `DEVILDOM_RAID2_CONTROLLERS_20261026.md` |
| 4 | 裸装属性等级成长 | `NAKED_LEVEL_GROWTH_20261026.md` |
| 5 | 副本 Boss 掉落范围 | `DUNGEON_LOOT_SCOPE_20261026.md` |
| 6 | 城镇进入被拒 | 本文第七节（无专项文档） |

---

## 一、总览

| # | 现象 | 根因 | 结果 |
|---|---|---|---|
| 1 | 快捷栏第 1 格「完全恢复药水」点不动，`0x114` 结果 `-1` | 组 412 内两个模板被判歧义；`130165` 未进准入表 | 可用，服务端 1 秒冷却 |
| 2 | Memory8 终点房近侧打完不结算，门开了人不搬 | 客户端自己开门后等服务端选区域，而该段唯一出口是结束副本 | 近侧清完由服务端下发 part 切换 |
| 3 | 34140「离开裂隙」无效，对话框只有"……" | 9 个 class103 静态标记的原生 255 退场无人受理 | 新增控制器，恢复 `0xBA` 结算入口 |
| 4 | Lv1 与 Lv99 裸装属性完全相同 | `base_attributes` 是与等级无关的常量 | 历史相对缩放候选；当前已由公开成长输入规则取代 |
| 5 | 部分副本通关零掉落 | 芯片族被 raid 托管 / 原生声明不掉 / 缺描述符 | 新增 4 张图（35450–35480） |
| 6 | 被拒绝的城镇进入掉线甚至客户端崩溃 | 拒绝路径抛 `SessionOrderError` 直接断连 | 回 `0x226` 负号拒绝，会话存活 |

---

## 二、快捷栏 412 完全恢复药水

**文件**：`els_server/domain/consumables.py`、`els_server/storage/consumables.py`

### 两个独立拒绝

1. 组 412 内同时有 `130165`（279 个，背包格 7）与 `710000`（99 个，背包格 12），`item_binding` 都是 412。默认分支要求"同组只有一个模板"，否则抛 `Ambiguous consumable template`。这条守卫本意是不猜未知药族，结果把一直可用的 710000 一起挡死。
2. 即使只留一个模板，`130165` 也不在 `ordinary()` 准入表里，直接抛 `Consumable effect not implemented`。它的记录除模板 id 外与已准入的 710000 **逐字节相同**：冷却组 15、30 秒、`0xA8` 为空、最低等级 0、`0xAC` 两条依次 `(13,100)` / `(19,100)`。

旁证：`consumable_cooldowns` 里该角色有组 2/5/10/12/14 的近期使用行，**完全没有组 15**——这一格从没成功用出去过。

### 改动

```python
# domain/consumables.py
expected[130165] = (0, 15, 30, ((13, 100), (19, 100)))
LOCAL_COOLDOWN_SECONDS = {130165: 1}

def acknowledged_cooldown(template, seconds):
    """0x114 cooldown float; -1 keeps the native record value for other rows."""
    return float(LOCAL_COOLDOWN_SECONDS[template]) if template in LOCAL_COOLDOWN_SECONDS else -1.0
```

```python
# storage/consumables.py
if binding in (399, 412, 775):        # 原为 (399, 775)
```

选定顺序沿用同一套确定性规则：有期限优先 → 到期早优先 → 背包格 → UID。本角色因此固定消耗 `130165`（格 7），不会误吃 `710000`。`acknowledged_cooldown()` 只把 `0x114` 尾部冷却浮点从 `-1` 改为 `1.0`，其余药水仍是 `-1`。

### 边界

- 目录与清单未动：`consumables.json` 记录字节保持原样（`0xD6` 仍 30），`consumables.manifest.json` 与 `check_EP_owned_goods_source_boundary.py` 的哈希不变。
- 710000 仍按原生 30 秒并回报 `-1`；它与 130165 **共享组 15**，先喝 710000 会让这格等 30 秒——共享冷却组的既有语义，不是新缺陷。
- 宠物自动使用、Buff、面向目标或活动类药品继续拒绝。

### 验证

`test_full_recovery_shortcut.py` 4 项：目录记录仍 30 而服务端计时 1、`0x114` 尾部浮点 1.0（710000 为 -1.0）、组 412 两模板时按背包格取 130165 且 1 秒后可再用、只剩 710000 时维持 30 秒。回归 `test_additional_potions`、`test_consumables`、`test_consumable_current_owner`、`test_manual_magic_potion_current`、`test_potion_bag_migration` 全绿。

**未验**：客户端界面冷却是否画成 1 秒——客户端本地记录仍是 30 秒。

---

## 三、Memory8 终点房

**文件**：`els_server/domain/dungeon_flow.py`

### 现象（会话 20261026-191129）

进 35322，15 条 `0xad` 全部被接收（184 字节，全是普通死亡），**没有一条 160 字节的原生 255**；服务端 `0xba / 0xbb / 0xbc / 0xc1` **各 0 次**。客户端已自己打出「右边的大门打开了」，Boss 条 `x18`，角色停在阵上。

即：客户端不看服务端脸色就开门，然后**等**服务端选下一块区域；它自己不发 `0xB8`、也不发 `0xBB`。

### 死结

该段唯一条件是 `kind 3, required=[9452]`，唯一出口是 `kind 4`（结束副本）；而 9452（`LITHIA_MEMORY8_STORY_DUMMY_3`）按源码注释是「门后那场战斗打完才退役」。玩家在门前 → 9452 不退 → 条件不成立 → 不发 `0xba` → 客户端继续等。环路闭合。

### 改动

```python
FINALE_ROOMS = {35320: (3, 0), 35321: (2, 0), 35322: (0, 0)}
FINALE_BOSS = 9431
FINALE_AREA_ENABLED = True
FINALE_AREA_PART = 1

def finale_boss_pending(run):    # Boss 未离场 → 房间不结算
def finale_area_cleared(run):    # 近侧（除 9431 外全部 active 且 team≠0）清完
```

- `periodic()`：近侧清完后**一次性**下发 `initial_part(1)`（`0xb7`，选资源 part）+ `begin_substage(1, npc_entries=当前全员)`（`0xbd`），把下一块区域交给客户端；actor 名单原样透传，不新造。
- `0xbb` 分支：`finale_boss_pending()` 为真时只回 `0xbc`，不结算。

### 边界

- 只管 35320 stage3 / 35321 stage2 / 35322 stage0。
- 不产生 9452 的死亡、任务证明、掉落或经验；房间真正的结束仍只由客户端上报的 9452 退役驱动。
- `FINALE_AREA_PART` 是唯一实验参数，改回 0 或关掉 `FINALE_AREA_ENABLED` 即回到旧状态。

### 验证

`test_lithia_memory8*.py` 24 项全绿；新增 `test_lithia_memory8_finale_door` 四项：近侧清完只发一次 `0xb7+0xbd` 且名单透传、近侧未清完什么都不发、非终点房不受影响、Boss 未离场时 `0xbb` 不结算。

**未验**：客户端是否会因为资源里没有 part 1 而拒绝、忽略或黑屏，只能实机验。

---

## 四、34140 裂隙二阶段控制器退场

**文件**：新增 `els_server/domain/devildom1_raid2_controllers.py`；`dungeon_flow.py` 3 行调用

### 现象

`selected_map: 34140`（`dungeon_devildom1_raid2.lua`）内无法离开：对话框正文为空只显示"……"，"离开裂隙"按下无效。会话 20261026-214618 的 trace 显示，`0xB3` 到 `0x225` 之间**从未发出 `0xB8`，也从未发出 `0xBB`**，`0xBA`、`0xC1` 各 0 次。

### 根因

三个阶段各自的通关条件都是 `kind 3`（按模板点名），被点名的模板全部是 `active=False`、`no_drop=True` 的 class103 剧本标记：

| 阶段 | 要求击杀 | 脚本 |
|---|---|---|
| 0 | 6851 | `2018_RAID_BOSS2_PHASE1_END.lua` |
| 1 | 6853 | `2018_RAID_BOSS2_PHASE2_END.lua` |
| 2 | 6855 | `2018_RAID_BOSS2_PHASE3_END.lua` |

`condition_ready` 的 kind 3 用 `all(k in dead for k in required)`，只有客户端把这些标记按原脚本（flag 255）退场并上报，part 才可能被观察为结束。此前没有任何模块登记 34140，`0xAD` 准入链（`hunter_chest_flow` → `source_actor_expiry` → `lithia_memory1` → `scene_actor` → `story_controller`）对它全部返回 `None`，落到通用路径后被 `d['flag'] not in (0,1)` 丢弃。

### 改动

只受理该图 9 个已声明静态标记的原生 255 退场，插在 `scene_actor_retirements` 之后：

| stage/part | wire key | template | source | point |
|---|---:|---:|---:|---:|
| 0/0 | 5 | 6850 | 6 | 89 |
| 0/0 | 6 | 6856 | 7 | 89 |
| 0/0 | 7 | 6851 | 8 | 89 |
| 0/0 | 8 | 6857 | 9 | 89 |
| 1/0 | 1 | 6852 | 2 | 1 |
| 1/0 | 2 | 6853 | 3 | 1 |
| 2/0 | 1 | 6854 | 2 | 1 |
| 2/0 | 2 | 6855 | 3 | 1 |
| 2/0 | 3 | 6849 | 4 | 1 |

图摘要钉死 `e19bb64e80a3788b985b54910c9ad4d29004f29234c68db933bdb395d83930a3`。每条受理同时校验 graph 与摘要、catalog 当前资源、manifest 脚本摘要、整条 source 字段、wire key 与 start point、`initialized_maximum`、native `class_id==103 / script / is_npc`、`npc['active'] is False`、unit15、原 run/阶段/单人 owner/current lease/`reward_run_id`、完整 native255 包。

受理后只回 `0xAE` 与空奖励 `0xAF`，并沿原条件判断是否发 `0xBA`；shadow 里先编码完全部回复再采用状态，同 payload 重放只 ack，冲突重放拒绝。**不调用任务、经验、掉落或经济消费者，不生成任何死亡、wave、计时或 gate。**

### 为什么不复用其它路径

- **不复用 `story_controller_retirements`**：它要求 `rule['quests'] or rule['map_quests']`（真实任务证据）。34140 的三个 END 控制器没有任务前置，用它会变成"无任务伪造准入"。
- **不允许 zero 别名**：`lithia_memory1` 允许 `report['index'] in (0, key)`，但 34140 的 key 0 就是 Boss 6801（`hp=1322115840`）。这里只接受精确 key。
- **不预置"Boss 必须已死"前置**：那是发明规则。`0xB8` 分支本身已要求当前 part 全部 active 敌对已死。

### 恢复与验证

- 代码回退：revert 本笔（1 个新模块 + 3 行调用）；或 `DEVILDOM1_RAID2_CONTROLLERS_ENABLED = False`。
- `test_devildom1_raid2_controllers.py` 10 项通过；`tools/ci_checks.py` 1673 文件 / 980 源全绿。

**未验**：未实机；9 次 255 上报的 index 顺序没有落盘，"9 = 4 + 2 + 3 全量"目前只是数量巧合。

---

## 五、裸装基础属性的等级成长

**文件**：`els_server/domain/character_stats.py`、`config/combat_rules.json`、`config/integration_roadmap.json`、`tests/test_instance_stats.py`

### 现状

`base_attributes = [10000, 100, 100, 100, 100, 10, 10]` 与等级无关，`combat_values()` 原样返回，`combat_attributes()` 只发裸装七元组。所以 Lv1 与 Lv99 的裸装输入完全相同。

实测 Lv99 艾米粒（27 件在穿装备）：

| 字段 | 裸装 | 装备估算 | 裸装占比 |
|---|---|---|---|
| HP | 10000 | 76466 | 11.6% |
| 物理攻击 | 100 | 15455 | 0.6% |
| 魔法攻击 | 100 | 11378 | 0.9% |
| 物理防御 | 10 | 2749 | 0.4% |

### 静态来源

没有已核实的原生裸装成长日志。`integration_roadmap.json` 已逐条排除候选：`m_Stat` 属技能配置，`iBaseHP` 与 `6A3F20` 属 `SetItemLevelEnchantData`，`UserUnitStateData` 更新函数只是状态索引注册。

因此复用 `CharacterStatTable.lua` 中已有、且由 `_parameters()` 加锁校验的 knum 常量：

```
physical = [1, .15, .8, .0225, .5]
hp       = [1, .17, 10, 1.1, .5]
```

依据是公式退化：裸装时 `relative_attributes` 的 A 与 B 取自同一行，逐级倍率退化为 `(pivot + n*rate) / pivot`，与 A、C 无关。HP 无法退化（A=B 时差值为零），改用同表的 `growth` 项线性缩放。

### 改动

```python
def level_multipliers(level):
    """Return (health, attribute) scalars, or None when growth is disabled."""
    spec = _growth()
    if spec is None: return None
    pivot, rate, hp_growth, _flat = spec; n = level - 1
    return f32(1 + n*hp_growth), f32((pivot + n*rate) / pivot)
```

配置新增 `level_growth` 块：`provenance=native_equipment_curve_relative`、`reference_level=1`、`flat_indices=[]`。系数在代码中从已校验的 knum 常量现算，**配置不复制数字**。

### 效果（Lv99，同角色同装备）

| 字段 | 改前合计 | 改后合计 | 变化 |
|---|---|---|---|
| HP | 86466 | 253066 | ×2.93 |
| 物理攻击 | 15555 | 21802 | +40% |
| 魔法攻击 | 11478 | 17725 | +54% |
| 物理防御 | 2759 | 3384 | +23% |

### 边界与恢复

- 只缩放裸装输入。装备属性、套装、被动、实例派生字段、DTO 布局（`length=28` 七元组保留）、协议字节、数据库与迁移均不变。
- 等级 1 倍率为 `(1.0, 1.0)`；无角色上下文时仍是历史未缩放元组。
- `retail_base_verified` 与 `level_growth_verified` 仍为 `false`。
- 恢复：删除 `level_growth` 整块即回到常数行为；只让某项保持原值则写进 `flat_indices`（`0`=HP，`6`=魔法防御）。

### 验证

`test_naked_level_growth.py` 六点：配置声明为本地策略、等级 1 复现占位值、倍率与 knum 一致、单调且报文长度不变、`flat_indices` 生效、常量漂移时抛错。`test_instance_stats.py` 改为直接钉原生 `7902/6047` 增量，不再钉随占位值浮动的合计。

---

## 六、副本 Boss 掉落范围

**文件**：`els_server/data/dungeon_equipment_loot.json`、`dungeon_material_loot_catalog.json`、`domain/dungeon_equipment_loot_rules.py`、`domain/dungeon_equipment_loot_flow.py`、新增 `tools/loot_scope_report.py`

### 四道闸门

239 条准入路线里 **102 条已接奖励流程**（本轮新增 4 条）。剩余 137 条不能接的原因**不是"掉落表没提取"或"白名单漏扩"**：

| 闸门 | 判据 | 现状 |
|---|---|---|
| 1. 路线准入 | `route_catalog()` 有捕获的 solo 图 | 239 条全过 |
| 2. 原生声明 | `DungeonData.lua` 的 `BOSS_DROP_ITEM` | 238/239 有 |
| 3. 获取策略 | `acquisition_policy.can_acquire()` | 大量拒绝 |
| 4. 实例描述符 | 现有目录能给出原生 ground/inventory 证据 | 本轮接入后剩 17 张可复用 |

判定工具：`python tools/loot_scope_report.py`（`--json` 全量，`--map 34000` 单图）。

137 张分档：`needs_class_evidence` 72、`raid_source_only` 89、`accessory_compatibility_only` 68、`cartridge_use_only` 15、`policy_blocked_type_6` 5。

### 本轮只接 4 张，不是 21 张

原计划 21 张（20 芯片 + 1 材质），被两条独立证据各砍一部分：

- **16 张芯片图是 raid 托管**：22 张声明 118638 的图里 16 张已有 raid 经济定义，再加进碎片族会在 raid 结算之上**重复发放**。
- **35390 / 35400 早在目录里**。

所以新增恰好是 35450 / 35460 / 35470 / 35480（模板 118638）。

进入 `MAPS` 不只是"Boss 可能掉芯片"：`values.fragment_on_validated_clear`（50 个 118445）会随通关一起发。四张图的实际变化是「原本通关零掉落」→「通关保底 50 碎片 + Boss 25% 芯片」。

保底有**两条互斥路径**：

| 图 | 保底来源 |
|---|---|
| 35340、35360 | `pve_economy_flow.clear()` |
| 35390、35400、35450–35480 | `dungeon_equipment_loot_flow.clear_rewards()` |

互斥机制：`pve_economy_flow.clear()` 派发前设 `shadow.reward_transaction = db`，而 `clear_rewards()` 的 `enabled(s)` 要求 `reward_transaction is None`——PVE 路径下 `clear_rewards()` 主动让位，碎片只发一次。

> `raid_economy_flow.managed(s)` 收的是**会话对象**，不是地图 id。传 int 会永远返回 `False`，判定必须读同源的 `rules.definition()`。

### 35170 不可接

秘密副本 35170 图里 **17 个 actor 全部 `no_drop: true`**（含 `boss: true, boss_lines: 70` 的 9180），`boss_sources()` 返回 `[]`，而材质目录有结构性守卫 `if not sources or row['accepted_boss_sources'] != sources: raise`——设计上不接受"原生声明不掉"的地图，不能硬接。

### 验证

客户端实机**尚未发生**（存档回执里打过的是 35320 / 35260 / 35250 / 35270 / 30000 / 34090）。已完成的是用**存档副本**（`D:\tmp\els-verify\verify.sqlite3`，原档只读不动）驱动真实代码路径，映射 35450：

| 步骤 | 结果 |
|---|---|
| `flow.enabled()` | `True`（真实 `DungeonRun(35450,…)`，阶段 0 / 部分 1） |
| Boss 9889 命中 25% | 回包 `0xae 0xaf 0xcf 0xcf`；地面掉落 = 金币 127000 + 芯片 118638 |
| Boss 9889 未命中 | 回包 `0xae 0xaf 0xcf`；只有金币 |
| 拾取芯片 | 回包 `0xd1 0xd2 0xd3`；`pickup_committed=True`；背包 118638 由 0 → 1 |

`test_equipment_loot_route_admission.py` 8 条、`test_clear_bundle_ownership.py` 5 条、`test_loot_scope_report.py` 钉分档统计；`tools/ci_checks.py` 全量通过。

**未覆盖**：完整通关信封（`0xBB`→`0xC1`）与 50 碎片实际入包——需要真实 `reward_store`。

---

## 七、城镇进入被拒不再断连

**文件**：`els_server/domain/local_session.py`

会话 20261026-200944：DX11 客户端请求了一次显式默认位置入场（flag 1），但背后没有服务端签发的 58C。旧代码直接抛 `SessionOrderError('Invalid local town entry')`，把整条连接丢掉，于是一次被拒绝的传送变成了客户端崩溃。

```python
if not (native_noah_return or native_committed_warp):
    refused = struct.unpack_from('>i', event.payload)[0]
    if refused not in TOWN_SCENES:
        raise SessionOrderError('Invalid local town entry')      # 未知地图仍是畸形输入
    return [Event(0x201, kind=0x226,
                  payload=i32(-1) + i32(refused) + i32(0) * 3)]  # 已知城镇：负号拒绝，会话存活
```

边界：**未知地图身份仍然硬拒绝**；已知城镇用和其它未授权目的地一致的方式拒绝——负号 226、不为被拒的城镇编造位置。此项没有新增独立测试文件，靠现有会话/传送测试与实机观察。

---

## 八、变更清单

**代码（12）**

```
els_server/domain/consumables.py                    +11
els_server/storage/consumables.py                   +11/-2
els_server/domain/dungeon_flow.py                   +38
els_server/domain/devildom1_raid2_controllers.py    新增
els_server/domain/character_stats.py                +45
els_server/domain/local_session.py                  +14/-1
els_server/domain/dungeon_equipment_loot_rules.py   +2/-2
els_server/domain/dungeon_equipment_loot_flow.py    +6/-1
els_server/data/dungeon_equipment_loot.json          4 图扩展
els_server/data/dungeon_material_loot_catalog.json   材质表
config/combat_rules.json                            +level_growth
config/integration_roadmap.json                     属性进度
```

**测试（8）**：`test_full_recovery_shortcut`、`test_lithia_memory8_finale_door`、`test_devildom1_raid2_controllers`、`test_naked_level_growth`、`test_loot_scope_report`、`test_clear_bundle_ownership`、`test_equipment_loot_route_admission`（新增）、`test_instance_stats`（修改）

**工具（1）**：`tools/loot_scope_report.py`

---

## 九、未验与回退

| 项 | 状态 |
|---|---|
| 412 药水界面冷却是否显示 1 秒 | 未验，客户端本地记录仍是 30 秒 |
| Memory8 终点房 part 切换 | 服务端已下发，客户端是否接受只有实机能验 |
| 34140 三阶段连续推进 | 未实机；9 次 255 的上报顺序未落盘 |
| 裸装成长的绝对量级 | `retail_base_verified` 仍 false，只证明相对缩放 |
| 35450–35480 通关保底 50 碎片 | 只验到"归属与数量正确"，未真实通关 |
| 城镇进入拒绝 | 无新增独立测试 |

回退成本都很低：药水改 `LOCAL_COOLDOWN_SECONDS`；终点房关 `FINALE_AREA_ENABLED`；34140 关 `DEVILDOM1_RAID2_CONTROLLERS_ENABLED`；裸装删 `level_growth` 块；掉落回退 `MAPS` 与 `DATA_SHA`。
