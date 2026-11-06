# 副本 Boss 掉落范围判定

## 结论

239 条准入路线里，**102 条已接奖励流程**（本轮新增 4 条），剩下 **137 条之中真正不能接的原因不是"掉落表没提取"，也不是"白名单漏扩"**，而是四道互相独立的闸门：

| 闸门 | 判据 | 现状 |
|---|---|---|
| 1. 路线准入 | `route_catalog()` 有捕获的 solo 图 | 239 条全过 |
| 2. 原生声明 | `DungeonData.lua` 的 `BOSS_DROP_ITEM` | **238/239 有**（只有 41430 没有） |
| 3. 获取策略 | `acquisition_policy.can_acquire()` | 大量拒绝 |
| 4. 实例描述符 | 现有目录能给出原生 ground/inventory 证据 | 本轮接入后剩 17 张可复用 |

第 4 道是最容易漏的一道：一个模板即使过了第 3 道，仍需要一个知道其实例形状的目录（装备 type1/2 默认实例、材质 type6/7、饰品 type3）。没有这一层，发放就得自己编客户端要解码的 body 字节。

判定工具：`python tools/loot_scope_report.py`（`--json` 出全量，`--map 34000` 出单图）。

## 137 张的分档

| 档 | 数量 | 含义 |
|---|---|---|
| `needs_class_evidence` | 72 | 策略放行，但没有对应类别的实例描述符 |
| `no_native_drop` | 30 | 原生就没有 `BOSS_DROP_ITEM`（过场/无 Boss 图） |
| `policy_blocked` | 18 | 声明的模板全部被获取策略拒绝 |
| `reusable_descriptor` | **17** | 已可复用现有描述符，只差加白名单 |

## 第 3 道闸门的拒绝原因（按模板引用计）

| 原因 | 数量 |
|---|---|
| `raid_source_only` | 89 |
| `accessory_compatibility_only` | 68 |
| `cartridge_use_only` | 15 |
| `policy_blocked_type_6` | 5 |

`accessory_compatibility_only` 是本次最关键的发现：经典图的 Boss 掉落物是旧饰品（如 30000 → 30163「班德斯的项链」），`ordinary_accessories.definitions()` 里 3047 个饰品中有 **2295 个标着 `compatibility_only=True`**，`can_acquire()` 因此明确拒绝新增来源。这是业主要求的获取策略（"只用于解码和操作既有存档，不新增来源"），不是数据缺失。

所以先前"87 张只差接线"的判断是错的：那一版只验证了模板是否**登记**在 `VERIFIED_TEMPLATES` 里，没有验证登记**取值**是否满足装备类约束，也没有走 `can_acquire()`。

## 本轮实际接入：4 张，不是 21 张

原计划接入 21 张（20 张芯片 + 1 张材质），实施时被两条独立证据各自砍掉一部分：

### 16 张芯片图是 raid 托管

用 `raid_economy_flow.rules.definition(map_id)` 逐张判定，22 张声明 118638 的图里 **16 张已有 raid 经济定义**（35370、35380、35410–35440、35490–35560、35580、35590）。把它们再加进碎片族会在 raid 结算之上**重复发放**。剩下 6 张非托管图中，35390、35400 早就在目录里，所以新增恰好是：

| 图 | 模板 | 上级图 |
|---|---|---|
| 35450 | 118638 | — |
| 35460 | 118638 | — |
| 35470 | 118638 | — |
| 35480 | 118638 | — |

四张都满足：路线已准入、非 raid 托管、原生 `COMMON` 声明 118638、`equipment_chip_rules.generate` 已存在。

**进入 `MAPS` 不只是"Boss 可能掉芯片"**：`values.fragment_on_validated_clear`（50 个 118445）会随通关一起发放。所以这四张图的实际变化是「原本通关零掉落」→「通关保底 50 碎片 + Boss 25% 芯片」。

这条保底有**两条互斥的实现路径**，分清很重要：

| 图 | 保底来源 | 原因 |
|---|---|---|
| 35340、35360 | `pve_economy_flow.clear()` | 它们有独立的 PVE 经济规则 |
| 35390、35400、35450–35480 | `dungeon_equipment_loot_flow.clear_rewards()` | 无 PVE 经济规则，走默认 clear 层的接管 |

互斥的机制是 `pve_economy_flow.clear()` 在派发前会设 `shadow.reward_transaction=db`，而 `clear_rewards()` 的第 3 行 `enabled(s)` 要求 `reward_transaction is None`——所以 PVE 路径下 `clear_rewards()` 主动让位，碎片只发一次。`tests/test_clear_bundle_ownership.py` 把这条边界与两条路径的归属划分都钉住了。

> 注意 `raid_economy_flow.managed(s)` 收的是**会话对象**，不是地图 id。传 int 时它取 `getattr(None,'identity',None)`，永远返回 `False`。判定必须读它同源的 `rules.definition()`。

### 35170 的原生图声明整张不掉落

35170 是 `dungeon_devildom2_secret.lua`（秘密副本）。它的图里 **17 个 actor 全部 `no_drop: true`**，包括那个 `boss: true, boss_lines: 70` 的模板 9180。因此 `boss_sources()` 返回 `[]`，而 `dungeon_material_loot_catalog.catalog()` 有一句结构性守卫：

```python
if not sources or row['accepted_boss_sources']!=sources:
    raise ValueError('Material loot original hostile Boss sources')
```

也就是说材质目录在设计上**不接受**"原生图声明不掉落"的地图。这不是本地缺描述符，是原生对地图的陈述，**不能硬接**。35170 因此留在 `reusable_descriptor` 档（它有 `ordinary-material-default-v1` 描述符），但不进任何 catalog。

## 剩余 17 张可复用图

| 图 | 模板 | 现有描述符 |
|---|---|---|
| 35170 | 154065 | `ordinary-material-default-v1`（原生 no_drop，不可接） |
| 35370、35380、35410–35440、35490–35560、35580、35590（共 16 张） | 118638 | `equipment-fragment-v1`，但均为 raid 托管 |

所以这 17 张全部卡在**非技术**原因上：16 张要给 raid 经济让路，1 张原生不掉。没有一张是"再写点代码就能接"。

## 本次落地的改动

1. `els_server/data/dungeon_equipment_loot.json`：新增 4 张图的规则（`graph_source_sha256`、`source_definition_sha256`、`finite_boss_candidates: [118638]`）；`chip_extension_revision` 升到 `equipment-chip-compatibility-v2`，`chip_extension_provenance` 与 `values.native_membership` 改写为八张图的实际构成（原文"four listed admitted maps / four circuit IDs"已失真）。`DATA_SHA` 更新为 `8fa0415a…`
2. `els_server/domain/dungeon_equipment_loot_rules.py`：`MAPS` 由 4 张扩到 8 张，`DATA_SHA` 同步
3. `els_server/data/dungeon_material_loot_catalog.json`：**未改动**（35170 回滚后字节级还原，sha 仍为 `b936d1bb…`）
4. `tests/test_equipment_loot_route_admission.py`（新增 8 条）：钉住 MAPS 集合、非 raid 托管、原生声明、图/定义摘要与实时数据一致、boss 计划产出单枚带词条芯片、图摘要不符即拒、通关保底碎片包的连带后果、相邻未接图不外溢

原生表只给"掉什么"，不给"多大概率、掉几个"。概率只能本地设并留档，这是三个 catalog 全部自称 `local compatibility` 的原因。

## 不建议做的事

- **不要**把 `compatibility_only` 批量改成 `False`。那是业主要求的获取策略，改它等于单方面放开 2295 个旧饰品的获取来源。
- **不要**为凑数给 `needs_class_evidence` 的 72 张编实例描述符。每一类都需要 ground/inventory 原生证据（现有目录各自带 `native_proof`、`inherited_dto_evidence` 等数十个字段），编出来的 body 字节会让客户端解码出错。
- **不要**把 `no_native_drop` 的 30 张硬塞掉落。原生没声明，塞了就是自造来源。
- **不要**为了消化那 16 张 raid 图去改 `raid_economy_flow`。raid 经济是独立的一条结算链，并进来就是双发。

## 数据来源与未知

`DungeonData.lua`（2,141,413 B 已解码）里 740 条 `AddDungeonData`，502 条带 `BOSS_DROP_ITEM`，结构为 `{职业桶: {槽位: 模板}}`，含 `COMMON` 与各职业覆盖。`DropItemManager.lua` 只有 151 条 `SpecialDropItemInfo`（特效集、散布 ±500、冷却 3s），**没有概率**。`AdjustDropTableCommon.lua` 只有 5 条 `DropTable`，带 `DropLevel` 分级累计阈值，属调整表而非主表。

因此**掉落概率与数量在任何已提取表里都不存在**，属未知；本判定不据此推算任何数值。

## 验证

`tests/test_loot_scope_report.py` 九条断言钉住：239/102/137 的总账、四档计数、30 张无声明的集合、四类拒绝原因计数、30000 被饰品标记拦截而非缺数据、17 张可复用图的模板与描述符一一对应、35170 全 no_drop 因而不进材质目录、每一档与其组成自洽、可发放与已拒绝恰好划清每个声明模板。

`tests/test_equipment_loot_route_admission.py` 八条断言钉住本轮四张图的准入依据（见上）。

`tests/test_clear_bundle_ownership.py` 五条断言钉住通关保底的两条互斥路径：每张图恰好归一条机制所有、六张 loot 托管图能过 `enabled()`、持有 `reward_transaction` 时 `clear_rewards()` 让位（这就是防双发的机制）、家族外的图（30000）仍归默认固定奖励、两条路径的数量同为 50。

**验证状态（两层，要分清）。**

客户端实机尚未发生：存档回执里艾米粒打过的图集中在 35320 / 35260 / 35250 / 35270 / 30000 / 34090 等，`reward_receipts` 的 `title_dungeon` 从未出现本节任何一张；背包模板清单里也没有 118638 / 118445 / 154065。

已完成的端到端验证是用**存档副本**（`D:\tmp\els-verify\verify.sqlite3`，原档只读不动）直接驱动真实代码路径，映射 35450：

| 步骤 | 结果 |
|---|---|
| `flow.enabled()` | `True`（真实 `DungeonRun(35450,…)`，阶段 0 / 部分 1） |
| Boss 9889 命中 25% | 回包 `0xae 0xaf 0xcf 0xcf`；地面掉落 = 金币 127000 + 芯片 118638（`dungeon-equipment-loot-compatibility-v1`） |
| Boss 9889 未命中 | 回包 `0xae 0xaf 0xcf`；只有金币，无芯片 |
| 拾取芯片 | 回包 `0xd1 0xd2 0xd3`；`pickup_committed=True`；背包 118638 由 0 → 1，`metadata=1, group=1` |

未覆盖：完整通关信封（`0xBB`→`0xC1`）与 50 个碎片的实际入包——那要真实 `reward_store`，本轮只到"归属与数量正确"这一层。要拿到客户端实机证据，仍需用其中一张图（如 35450）真正通一次关。

`tools/ci_checks.py` 全量通过（1673 文件 / 980 源）。
