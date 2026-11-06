# 宅邸 BOSS 血量 + 原生逐行鉴定（20261101）

本轮从上游归档 `refs/gift-title-quickstart-hp-integration-20261101-v1/` 里**选择性整合**了两件事：
Trosh 血量修正（BossHP 单元）与原生逐行鉴定（gift 单元）。标题精华、QuickStart、灿烂刻印预设
三项刻意未动，见文末。

---

## 一、恶魔领域2 宅邸的 BOSS 一击就死（34340 / Trosh）

### 症状

打「恶魔领域2 · 宅邸」（地图 `34340`）时，关底 BOSS Trosh 的三个形态**一刀就躺**，
血条一闪就空，和同区域其它 BOSS 完全不是一个量级。

### 根因

客户端脚本 `devildom2_residence_boss_{a,b,c}.lua` 里写的是 `MAX_HP 1500`——
这是个**脚本占位值**，不是战斗血量。服务端 `formal_npc_hp.policy()['templates']` 对
7584/7585/7586 记的是：

```json
{"source": "current_client_explicit", "fixed": 1500}
```

而 `maximum()` 里 `explicit=native['script_max_hp']` 一旦非空，就直接 `return f32(explicit)`，
所以 1500 原封不动变成 BOSS 血量。**服务端没有错，它只是忠实执行了脚本里那个占位值。**

### 修法

上游给的办法是「只在该地图、该等级、该模板三元组完全对得上时，用一条已批准的本地规则
替换战斗上限，同时把脚本原值留在旁边当证据」。落到两处：

1. `els_server/data/formal_npc_hp.json`：`maps["34340"]` 新增 `combat_hp_overrides`，
   7584/7585/7586 三条，`hp` / `hp_float32` = **758,272,320**，
   `expected_script_hp` = 1500，`local_policy` = `trosh-battle-hp-correction-20261101-v1`，
   `official_CN_claim` = `false`。
2. `els_server/domain/formal_npc_hp.py`：在 `if explicit is not None:` 之前插入一段守卫，
   只有下面全部成立才替换，否则抛 `NPC HP approved combat override source changed`：
   * 等级 == `meta['level']` == `override['level']`（99）
   * `enum` / `script` / `class_id` / `is_npc` 与全局 templates 表逐字段相等
   * `source` == `cobodex_named_graph_level_reference_adopted_local_rule`
   * `explicit` == `override['expected_script_hp']` 且 `row['fixed']` == `explicit`
   * 结果必须是有限正数且 **float32 原样可表示**

758,272,320 = 2⁵ × 3 × 5 × 7 × 11 × 13 × 17 × 19…——实测 `struct` 往返一致，
所以客户端那边不会因为精度掉一截。

### 验证

`tests/test_trosh_battle_hp.py`（8 条）：

| 断言 | 意义 |
| --- | --- |
| 三个模板都返回 758272320.0 | 修好了 |
| `f32(值) == 值` | float32 精确 |
| 等级 1 / 98 / 100 → ValueError | 只认 99 级 |
| 34350 / 34360 → 仍返回 1500 | 规则不会漏到隔壁地图 |
| 全库只有 34340 带 `combat_hp_overrides` | 没顺手改到别人 |
| 同图其它模板的 public 上限不变 | 没有副作用 |

`tests/test_retained_native_hp.py`（9 条）同步复跑通过，其中第一条会核对
`formal_npc_hp.json` 的 sha256 与 manifest 是否一致——所以改数据必须同时改 manifest。

> **注意**：758,272,320 是「上游从 cobodex 34340 页面按 99 级难度公式取的值，作为本地规则采纳」，
> 不是「当前国服真实血量」。真要打，这个数字对满配 Lv99 是一场正经持久战。

---

## 二、装备鉴定：从「一个共享池」变成「每件装备的原生词条行」

### 之前是什么样

`identification_ui.json` 只有 77 个模板 + **一个** 45 结果的池子，
所有能鉴定的装备都从同一个池里抽词条，最多一行。也就是「项链、上衣、武器抽到的可能是同一批词条」。

### 现在是什么样

| 项目 | 之前 | 现在 |
| --- | --- | --- |
| 原生模板 | — | **992** 个（按模板各自的词条行数） |
| 词条行数 | 固定 1 | **1~4 行**（1 行 329 个、2 行 385 个、3 行 256 个、4 行 22 个） |
| 原生词条池 | 1 个共享池 | **188** 个，每个 100.00% 封闭分布 |
| 兼容行 | — | **64** 条（老存档已有鉴定结果仍按原样读回） |
| 拒绝猜测 | — | 4 条（118332~118335）池未验证，生成/重置一律 `ValueError` |

关键语义变化：

* `draw_initial(template, randbelow)` 返回**该装备原生行数**个词条，每行从自己那一行的池里抽；
* `initial_pending(item)` 对「没有 `identified` 字段、group=1、count=1、且没有任何词条」的原生装备
  返回 `True` —— 这是新功能本体：**新打到的装备就是未鉴定的**；
* `require_initial_complete(item)` 是配套的准入闸（本条整合里没有被调用点，见「已知缺口」）。

### 装了哪些文件

| 文件 | 来源 | 说明 |
| --- | --- | --- |
| `els_server/domain/identification_ui.py` | `refs/gift-.../normal/shared/` | 主逻辑重写（+269/−82） |
| `els_server/data/identification_ui.json` | 同上 | 78 KB → 2.4 MB，内含 992 模板 / 188 池 |
| `els_server/storage/identification_ui.py` | `references/accessory-identification-20261030-v1/` | 改调 `draw_initial`，重置走 `reset=` |
| `els_server/domain/accessory_identification.py` | 同上 | 新增 `groups_catalog` / `profile` / `reset_supported`，`draw` 接受模板 |
| `els_server/data/accessory_identification_groups.json` | 同上 | 85 个分组饰品（如 30606 三行） |
| `els_server/domain/growth_guide_boxes.py` | `references/permanent-growth-guide-.../integrated/online/` | 4 个固定反应堆（720753~720756）鉴定时要用 |
| `els_server/data/growth_guide_boxes.{json,manifest.json}` | 同上 | 63 个固定箱 |

> 上游这个包的 `parent_release` 是 `native-weapon-growth-lifecycle-20261101-v1`，比我们仓库这一块
> **领先一代**。所以直接覆盖两个文件是跑不起来的：`storage` 会调 `draw_initial`、`accessory_draw(x, template)`，
> 而这两个函数在本地旧版里不存在。上面那张表就是把这个缺口补齐的最小集合，
> 每一份都取自 `references/` 里**作者已经归档过的字节**，没有一处手写猜测。三份 JSON 的 sha256
> 与代码里硬编码的常量逐一对上（`975267cf…` / `7770dc4d…` / manifest 自校验）。

### 验证

`tests/test_native_identification.py`（12 条）：

* 每件原生模板：行数 1~4、`pool_groups` 与 `native_groups` 一一对应、池都存在；
* 每个原生池：权重合计 10000、`options` 集合与 outcomes 完全一致；
* 对 1/2/3/4 行的代表模板各抽一次（roll=0 与 roll=上限）：**行数等于原生行数**，且每个值落在自己那行的池里；
* 抽出来的向量能被 `validate` 原样接受；
* 118332~118335 四个未验证池：`draw_initial` 与 `require_template(reset=True)` 都拒；
* 全新原生装备 `initial_pending` 为真，打上 `identified` 后为假；
* 兼容行仍能用 `template_pool` 读回历史向量（64 条逐条过）；
* 分组饰品 30606 抽 3 行、`reset_supported` 为真。

`tests/test_identification_ui.py`（9 条，既有）全部通过。

### 对存档的影响（测过了，实际只有 7 件）

物品序列化的 `0x34d` 字段是「是否已鉴定」。以前只有饰品/活动装备会填 `2`(未鉴定)，
现在**原生模板的装备只要没有 `identified` 字段就会填 `2`**。

先看存储结构（`els_server/storage/equipment_identification.py`）：

```
inventory_items(uid, owner, template, metadata, count, bag_group, slot)   -- 只有骨架
equipment_identification(item_uid, identified 0/1)                        -- 显式标记，只存「设过的」
equipment_options(item_uid, groups_json)                                  -- 词条行
```

也就是说 `identified` 不是物品本体的字段，而是**旁表里的一条显式标记**；没有这行就按
`initial_pending()` 现算。所以「迁移」= 给受影响物品插一行 `identified=1`。

实测当前存档（`state/development.sqlite3`，277 件物品）：

```
物品总数 277，其中会按「未鉴定」下发的 7 件

角色    uid       模板     背包  槽  原生行数  名字
1002   1001438   118373   1    0   3        赤血魔影下衣（莉缇娅）
1002   1001441   118373   1    1   3        赤血魔影下衣（莉缇娅）
1002   1001439   118374   1    2   3        赤血魔影手套（莉缇娅）
1002   1001440   118375   1    3   3        赤血魔影鞋子（莉缇娅）
1002   1001193   136197   1    5   3        死龙的遗言-必灭的冰镐
1004   1001219   30206    1    5   1        克劳尔莱德手套
1004   1001251   30268    1    6   1        大酋长的风石护手
```

三个关键事实：

1. **7 件全在背包组 1（背包），没有一件在组 9（身上穿着的）**——不会有人站着站着装备变未鉴定。
2. 线包差异只有**一个字节**：`item_body()` 对比「默认 vs 显式 identified=True」，
   差异是 `body[157]` 或 `body[301]`：`2` ↔ `0`，其它 303 字节完全相同。
3. 服务端**不拦穿戴**：通用穿戴路径没有鉴定闸门（`require_initial_complete` 无调用点），
   只有神器/暗影/特内布罗斯/卡片这几个家族各有自己的守卫。所以这 7 件服务端照样能穿。

**结论：不做迁移。** 这 7 件正是最该鉴定的一批（3 行原生词条），标成已鉴定等于永久锁死在
「零词条」状态，反而把它们变废。让它们显示为未鉴定、玩家用卷轴开一次，才是新功能的本意。

留了个只读体检工具，随时能复查，也留了退路：

```
python tools/identification_state_audit.py                      # 只读副本，列出会被下发成未鉴定的物品
python tools/identification_state_audit.py --pin 1001219 1001193  # 真出问题时把这几个标回已鉴定（先备份）
```

审计模式**拷贝一份存档到临时目录读副本**，连 `CREATE TABLE IF NOT EXISTS` 都不会落到真存档上；
`--pin` 会先写 `development-backup-<时间戳>.sqlite3` 再改。


---

## 三、刻意没做的三件事

| 单元 | 为什么先不动 |
| --- | --- |
| 称号精华（title） | 要改 `boosting_2026_essence.py` 与 `local_session.py`，而这两个文件正压着上一轮 `0x460` 白框的止血补丁，等真实 96 字节载荷抓到了再一起动 |
| QuickStart | 只对 ONLINE 通道生效，本地没有对应入口 |
| 灿烂刻印预设 / `abyss_weapon_2026` | 属于 campaign580 +11 的发放链路，本地还没有这条链，先不加死代码 |

## 四、已知缺口

* `require_initial_complete` 已定义但**没有调用点**——本地通用穿戴路径不检查鉴定状态，
  未鉴定的装备服务端照样能穿（只显示为未鉴定）。要让「未鉴定不许穿」生效，得在穿戴/详情路径
  里显式调一次；本轮刻意没接，因为接了会立刻锁掉上面那 7 件装备。
* `tools/audit_enchant_equipment.py` 从来没进过仓库，`tests/test_normal_equipment.py` 有 2 条
  因此报 `ModuleNotFoundError`（**既有问题**，与本轮改动无关）。
* 三个新增模块（`growth_guide_boxes` 等）不在 `tools/run_release_tests.py` 的 98 个白名单里，
  需要新测试时得手工点名。
