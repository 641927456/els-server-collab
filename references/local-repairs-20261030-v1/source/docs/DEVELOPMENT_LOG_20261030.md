# 开发文档 · 2026-10-30 本轮工作

**基线**：`f4665dd`（2026-10-29 21:49，"docs: record why Algorithm 2/3 payloads cannot be decoded from disk"）
**范围**：10-29 夜间至 10-30 全天的工作区改动（24 个跟踪文件 / 13 个新增文件），覆盖物品与背包、镶嵌协议、
大师之路副本、尼格摩尔换图、启动器工具链五条线
**性质**：只记录本批改动；每条线各有专项文档，本文做总览与索引

## 索引

| # | 主题 | 专项文档 | 主要文件 |
|---|---|---|---|
| 1 | 背包整包校验：一行未登记打翻整个背包 | `fixes/20261030-unregistered-owned-rows-broke-whole-bag.md` | `inventory_items.py` |
| 2 | 镶嵌 0x1C5 预览向量宽度错误（`?????` + 適用灰置） | `fixes/20261030-socket-armor-high-preview-stuck.md` | `storage/sage_sockets.py`、`tests/test_sage_sockets.py` |
| 3 | 消耗品：水晶球属性索引、斗志药水、宠物券放行 | 本文第四节 | `consumables.py`、`storage/consumables.py`、`apple_consumables.py` |
| 4 | 大师之路 BOSS 血量 / 血条格数 / Z 键复活 | `fixes/20261030-master-road-boss-hp.md`、`-boss-gauge-lines.md`、`-resurrection.md` | `formal_npc_hp.py`、`local_boss_cap.py`、`local_boss_gauge.py`、`known_resurrection_*` |
| 5 | 尼格摩尔三图出口不亮 | `fixes/20261029-devildom2-part-markers.md` | `local_dungeon_flow.py`、`dungeon_routes.py` |
| 6 | 启动器：僵尸进程判定 + GM 道具走邮件 | `fixes/20261029-launcher-stale-client-gm-item-mail.md` | `launcher/service.py`、`launcher/app.js`、`storage/game_mail.py`、`tools/*` |

---

## 一、总览

| # | 现象 | 根因 | 结果 |
|---|---|---|---|
| 1 | 材料页 41 件物品双击无反应；随后"只有材料能开，其他全不行" | `load_items()` 末尾 `inventory_payload()` 校验**每一行**，任一模板不在 `VERIFIED_TEMPLATES` 就整包抛错 | 12 行按既有 sha256 目录登记，四个 owner 背包（16/176/10/51）全部可加载 |
| 2 | 镶嵌界面 4 槽全 `?????`、`適用` 灰置，但钱和石头已扣 | 0x1C5 尾向量按**容量长度补零**下发，原生消费者按**每颗材料一项**配对，补出的 0 被读成「选项 0」 | `_results()` 只回本次材料的掷点值，预览恢复、4 槽实测落库 |
| 3 | 水晶球类消耗品报"证据改变"、斗志药水不生效 | 效果值向量宽度归一化把 amount 顶到第 2 字；属性索引未登记 | 9 件放行（水晶球 ×8 + 斗志 ×1），消耗品可用数 11→20/24 |
| 4 | 大师之路 8 张图 BOSS 打不死、按 Z 不复活 | BOSS 血量取自更晚世代的绝对值（客户单次伤害 1e5 量级）；死亡请求被 `death_ack(-1)` 拒 | 血量按本地量级缩放；死亡/复活链路恢复 |
| 5 | 尼格摩尔 34340/34350/34360 打完不开门 | `kind==3` 出口 `required` 指向脚本标记（`IS_NPC`），客户端自行销毁、服务端永远等不到死亡上报 | 脚本门形态放宽，整图可模拟通关 |
| 6 | 关掉客户端后启动器仍报"游戏运行中"；GM 发道具占背包格 | 进程列表残留条目（零线程）被按名字判活；GM 直接写 `inventory_items` | 改查进程句柄信号状态；GM 道具改走邮箱托管，登录后领取 |

---

## 二、背包整包校验（最关键的一条）

**现象链**：最初用户报「材料页这一整页 41 件双击弹错误」，修复登记后变成「只有材料能开，装备镶嵌、宝箱、宠物券全废」。

**根因**：`load_items()` 在返回前调用 `inventory_payload()` 做整体自洽校验，**任意一行**模板不在
`VERIFIED_TEMPLATES` 就抛 `Invalid inventory item identity/template`，整个背包读取失败。
背包在客户端仍能显示，是因为这些行早已增量下发；只有服务端下一次读取才会失败。
所以症状永远是"某个不相关的操作突然全废"，而不是"那一件不能用"。

**改动**（`els_server/domain/inventory_items.py`，+110 行）：按既有带 pin 的目录登记 12 行

| 包位 | 模板 | 来源目录 |
|---|---|---|
| bag4 ×7 | 710085 / 710106 / 714139 / 714143 / 714147 / 723610 / 723618 | `published2026-bundles.json`（53b00587…）、`boosting2026-title-support.json`（bb9457a0…） |
| bag4 | 718117 [阿莉尔]巨人石苹果 | 记录 pin `d01ea1d4…`，`(2,6,999)` |
| bag4 | 712040 / 712041 阿莉尔属性球 | 元素球登记块 `_ARIEL_ELEMENT_BALLS` |
| bag6 | 78926 一类苹果族 | 苹果族绑定 |
| bag9/27 ×4 | 118828 / 118830 / 118834 / 118835 莉缇娅时装 | `boosting2026-fashion90.json`（481d8d33…），校验 `equip_position`/`slot` 一致 |

**验证**：四个 owner 背包分别 16 / 176 / 10 / 51 件全部通过 `load_items`，`inventory_payload` 不再抛错。

---

## 三、镶嵌 0x1C5 预览向量

见专项文档。摘要：`acknowledgement()` 的 options 尾向量原本是**容量长度**（下衣 4、武器 6，未镶槽补 0），
原生消费者按**请求里每行材料一项**读取；2 颗石头换回 4 项（含补 0）时整份预览作废。
新增 `_results(values,materials)` 按材料槽序取值，长度 = 石头数，重放分支共用同一函数保证幂等回包逐字节一致。

根因判定的证据是会话流水对齐：成功案例的结果数全部等于材料数，唯一失败案例是 2 颗石头 → 4 项。

---

## 四、消耗品

**水晶球（8 种）**：`kind18` 是**属性索引**，第 4 字恒为 1（属性等级）：

| 模板 | 属性 | 模板 | 属性 |
|---|---|---|---|
| 78360 | 3 火 | 78390 | 6 风 |
| 78370 | 4 水 | 78400 | 7 光 |
| 78380 | 5 地 | 78410 | 8 暗 |
| 712040 | 4 水（阿莉尔） | 712041 | 6 风（阿莉尔） |

交叉验证：712040↔78370、712041↔78390 成对重复。

**向量宽度归一化**（`_native_vector`）：原生布局是 `(kind, 0, amount, 0,0,0)`，amount 在**第 3 字**。
第一版把 2 元组插 0 展开成 `(kind, amount, 0, …)`，把 amount 顶到第 2 字，导致 10 个原本可用的药水
报 `Ordinary potion evidence changed`；修正为 `len<3` 时返回 `(kind, 0, amount, 0, 0, 0)`。

**斗志药水**：分支扩为 `(130467, 710193, 723674, 190624)`，pins 补 `190624`。

**宠物券**：`330562`（升级）与 `500720`（拾取）实测放行；`164566` 因 `automatic=1` 已解锁被正确拒绝；
`500867`（15 日限时拾取）仍需「有时限 pickup」模型，暂不处理。

**结果**：可用消耗品 11 → 20/24，余 4 个苹果卡在缺失原生抓包。

---

## 五、大师之路与尼格摩尔

**BOSS 血量**：8 个 `Dungeon_Md_*` 入口（34370–34700，含地狱难度共 16 张）的 BOSS 血量取自
`formal_npc_hp.json` 的 `public_hp_templates`（更晚零售世代绝对值），与本客户端 Lv99 单次约 1e5 的
伤害量级不匹配。`local_boss_cap.py` + `config/local_boss_hp_cap.json` 按本地量级缩放，
上限目标 `1,796,894.375 ÷ 11,900 = 151` 格，恢复上限即恢复同步血条。

**血条格数**：本轮先做了 `local_boss_gauge.py`（resource+0x58 → DTO 0x77）叠层，
经验证**未随服务端启用**（`enabled:false`）——血量上限版已足够，该项留作可开关的实验钩子。

**Z 键复活**：死亡请求 `0xa7` 被 `death_ack(-1)` 拒绝，从未进入 dying，后续 `0xaa` 自然无回应。
`known_resurrection_flow.py` + `known_resurrection_maps.json`（+210 行）按图登记可复活性；
`transport.py` 增 `resurrection_diagnostic` 日志（记录 `0xa7/0xaa/0x160` 与 `0xa8/0x161` 的返回码）。

**尼格摩尔换图**：34340/34350/34360 的 `kind==3` 出口 `required` 指向 `class_id=103 / IS_NPC=true`
的脚本标记（`*_START`/`*_CLEAR`/`*_END`），这些标记由客户端场景自己销毁，服务端收不到 `0xad`，
`condition_ready(kind==3)` 永远假。`local_dungeon_flow.py`（+171 行）放宽脚本门形态。

**进图后裸装**：`local_session.py` 在首个 substage 追加 `0x105` 装备恢复——副本场景的物品状态是新建的，
成员 DTO 的 equipped 表只还原 UID，不重放实例选项，否则本地模型是"裸装"。

---

## 六、启动器工具链

- **僵尸进程判定**：`x2_dx11.exe` 退出后进程列表条目会存活到句柄全关（零线程/零句柄/无窗口）。
  启动器和两个启动脚本原来只按名字匹配。改 `launcher.service.exited(pid)` 查进程句柄
  （`SYNCHRONIZE` + `WaitForSingleObject(0)`），`launch_friends_client.running_clients()` 共用同一规则。
- **GM 道具走邮件**：原来直接写 `inventory_items`，占背包格。新增 `game_mail.local_item_campaign()`
  在调用方事务内写 `game_mail` + `player_mail_meta` + `player_mail_items` 托管；
  地址走 `player_mail_meta` 保证同账号其他角色不可见/不可领；未领取按退回同角色过期。
  角色指纹加入 `game_mail` 行，防旧表单重复发放。

---

## 七、明确不可实现 / 暂缓

| 项 | 原因 |
|---|---|
| 7 个宝箱开箱 | 模板 0 命中 `cubes.catalog()`（73 模板）；RandomItem 规则在但 ItemGroup 表缺；`PackageItemData.lua` / `CanUseInventoryItem.lua` 是 KOG 定制字节码（魔数 `1b 4b 4c 82`） |
| 特级魔法石 ×6、[阿莉尔]贤者的魔法石 | 8 种石头无任何镶嵌目录收录（`ordinary`/`additional`/`spell_socket` 三处均未命中），需从客户端选项表提取属性池+权重 |
| 原生证据补采 | `fixed-cubes-native.json` 被 `image_sha256` 锁定，每条带原生读取；生成工具不在仓库 |
| 4 个苹果（78926/78928/78929/718117） | 同上，缺原生抓包 |
| 500867 宠物自动拾取（15 日） | 需"有时限 pickup"模型 |

---

## 八、验证

```bash
# 背包整包
python -c "from els_server.storage.inventory_state import load_items; print(len(load_items(db, 1002)))"

# 镶嵌向量宽度（本轮新增回归）
python -m pytest tests/test_sage_sockets.py -q

# 大师之路
python -m pytest tests/test_master_road_boss_cap.py tests/test_master_road_boss_gauge.py tests/test_master_road_resurrection.py -q

# 尼格摩尔
python -m pytest tests/test_devildom2_part_markers.py -q

# 启动器
python -m pytest tests/test_launcher.py -q
```

实测记录：

- 镶嵌：+20 [阿莉尔]赤血魔影下衣（721938）用高级魔法石连镶 4 槽 → 预览正常、`適用` 可点、
  `option_groups['0'] = [40813,40004,40705,40912]` 落库
- 宠物券：330562 升级置 1；500720 需选无永久拾取的宠物；164566 正确拒绝
- GM 道具：邮件领取回背包，耐久完整
- 背包：owner 1002 = 176 件、1004 = 51 件全部通过
