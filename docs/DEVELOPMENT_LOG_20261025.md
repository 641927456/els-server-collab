# 艾尔之光单机版 · 开发文档

> **文档性质**：批次汇总（batch dev log），不是单项验收记录。`docs/` 下其余 `*_2026MMDD.md` 是逐项改动的事实记录（自检、验收边界、渠道快照）；本文是把这些记录与全部 234 个提交按主题归并后的索引，用于回溯定位「哪类问题在什么时候修过」。新增单项改动仍应另建 `*_2026MMDD.md`，不要往本文追加。

> 覆盖范围：仓库全部 **234 个提交**（2026-10-19 ~ 10-25，7 天）
> 其中最近 5 个提交（`0a44fa7` ~ `69e42c4`）单独展开详解，之前 229 个按主题归并索引

| 项目 | 内容 |
|---|---|
| 仓库 | `641927456/els-server-collab`（本地 `E:\游戏\艾尔之光\els-server-collab`） |
| 分支 | `main`（受保护），当前推送分支 `sync/local-69e42c4` |
| 变更规模（本批） | 26 个文件，+1533 / −506 |
| 已有说明文档 | `docs/` 下 **118 份**，按日命名 `*_2026MMDD.md` |
| 合并状态 | PR #480 已提交，待仓库 owner 审批 |

---

## 一、提交构成

| 类型 | 数量 | 说明 |
|---|---|---|
| 原生功能接通 | 102 | 让客户端某个原生入口真正跑通（`Connect / 接通 / Admit / 绑定`） |
| 修复 | 94 | 修 bug（`fix / 修复`） |
| 记录 / 验收归档 | 28 | 只写文档与快照，**不改代码**（`Record / docs / Archive / Reconcile`） |
| 新功能 | 2 | 启动器 GM 面板预设等 |
| 其他 | 8 | 初始化、协作规则、CI |

按天分布：

| 日期 | 提交数 | 新增 docs | 当天主线 |
|---|---|---|---|
| 10-19 | 11 | 5 | 仓库初始化、协作与隐私边界、首批邮件任务分配 |
| 10-20 | 18 | 20 | 成长装备/宝石/时装/EP 商城、启动器 V29~V31 |
| 10-21 | 62 | 38 | 物品归属校验大扫除、Elixir/苹果/叶/药水可用、ERP 页面、净化器与红柱兑换 |
| 10-22 | 4 | 4 | 收尾（EP 商城、复活、随从） |
| 10-23 | 68 | 12 | 卡带（Cartridge）体系、染色与衣橱券、重铸/强化/分解、副本退役线 |
| 10-24 | 68 | 16 | 铁匠/炼金/强化、史诗任务批量接通、Tenebros、家园/公会/钓鱼、启动器 V35/V36 |
| 10-25 | 3 | 0 | **本批 5 个提交**：莉缇亚副本卡死 + 启动器仓库同步 |

---

## 二、本次 5 个提交详解

### 2.1 场景假人 9470 不发 DYING，导致 stage1 死锁（`cc82f75`）

**现象**：stage1/part0 的屏障永远不开，任务 **28110** 长期停在 `0/1`。

**根因**（追踪 `20261024-130855` 证实）：客户端把 9470 的 actor 一直保留在 stage1/part0 场景里，直到场景卸载都不发 `DYING` 报告。之前为 9470 加的屏障因此死等，整个 part 卡住。

**修复**：
- 按 pinned graph，**9310 退役**才是 part 的结束条件，改以该事件驱动；
- 把这条被接受的退役记录为 finale 任务的事件（`kind=retire`，绑定 `controller 9310` 下的 `npc 9470`）；
- `stage0/part2` 的 key-15 屏障保持不变；
- `seal_quests` 的进度记录放开 `retire` 类型。

**保护**：9470 先到只确认、不结束 part；重复上报幂等；未接取任务时该退役不计分。

### 2.2 class-103 场景对象被 `ISACTIVE` 误判（`69e42c4`，本批核心）

**现象**：`LITHIA_MEMORY2_FLOWER` 上报 native 255 退役被服务端拒绝，花打不死，part 屏障 **9324** 不开。

**根因**：原判定是

```python
scene = npc is not None and not npc['active'] and not npc.get('dynamic') and scene_controller(npc['template'])
```

class-103 的 Lua 对象**可以在源声明里是 `ISACTIVE`，却仍然自退役**。用 `ISACTIVE` 反推「已退役」从根上就错了——**该由类决定，不该由 `ISACTIVE` 决定**。

**修复**：
- 去掉 `not npc['active']` 这个错误前提；
- 新增 `source_pinned(run, npc)`，判断当前路线是否声明了「精确的退役来源」（stage / part / template / source_index 四元组全等）；
- 通用过期分支**不得**吞掉规则本身已拒绝的不匹配；source-pinned 控制器继续走严格规则路径。

```python
def source_pinned(run, npc):
    return any((r['stage'], r['part'], r['template'], r['source']['source_index'])
               == (run.stage, run.part, npc['template'], npc['source_index'])
               for r in RULES if r['dungeon'] == run.identity)
```

**同时修**（`0a44fa7`）：声明式退役报告此前被**丢弃**，客户端在等一个已经消失的 actor。改为**主动确认（ack）**；进度仍只由先运行的、绑定数据源的特化处理器产生。

### 2.3 LITHIA_MEMORY3 副本假人退役条件过严（`69e42c4`）

**现象**：**35270** stage0 只有剧情假人，屏障是 **9338** 的退役，结果 stage0 变成**无战斗可打**的僵局。

**根因**：每个假人对应的史诗任务（`28230` / `28240` / `28250`）只在**两次 run 之间**才激活。服务端却要求「退役前必须先有匹配任务」，于是永远等不到。

**修复**：
- 放宽**只对 35270 声明**，不扩散到其他副本；
- 退役本身不再要求任务存在，但**任务计数仍然要求有活动任务**——「无任务退役」不会凭空加分；
- 保留 source / owner / unit / HP / lease 四类校验，防止伪造报告钻空子。

### 2.4 转职后客户端技能页空白（`69e42c4`）

**现象**：完成转职任务后，客户端技能树页面是空的。

**根因**：只发了 F5 的 `skill_slots_initialization`，而当前客户端还需要 **`B9C380` kind `29F`** 来重建 career / 技能树上下文。

**修复**：
- `seal_quests` 在奖励结算时记录 `class_changed`（比较 `apply_quest_transition` 前后的 `unit_class`）；
- `quest_flow` 在 `class_changed` 为真时补发 `career_notice(...)`，再发技能槽初始化。

### 2.5 场景控制器自动登记（`0a44fa7`）

**现象**：原生 loader 对 DUNGEON 侧返回 `-1`，客户端等不到 actor。

**根因**：dungeon 的 cmd block 会在玩家交互时创建 Lua 场景对象，这类对象**不在** stage 的 `READY_NPC` 列表里，也就不在 pinned 路由图中。

**修复**：不再手写 id 白名单，而是**从路由自身的源文件名推导家族**——路由源自 `Dungeon_<STEM>.lua`，就拥有其图中未声明的 `<STEM>_*.lua` 控制器。之所以要推导而非列举：35250 一次会创建全部 5 幅壁画面板（`9305..9309`），手写列表只会记住第一个。

**四重守卫**（缺一不可，纯前缀匹配不安全——`EN_TUNNEL_*` 会放进 135 个战斗期对象）：

1. 必须属于副本级脚本家族；
2. 必须与客户端枚举一致；
3. 必须属于 controller class **103**；
4. 必须**不在**静态图中。

### 2.6 教程传送门别名（`0a44fa7`，默认关闭）

**现象**：序章城镇某些传送门提交的是脚本化教程地图（如 35240 `Dungeon_Tutorial_Lithia.lua`），当前客户端未在任何区域注册该地图，`config/dungeon_scope.json` 判为 `no_current_selectable_entry`，传送门回 `DUNGEON_CLOSED`，门永远不开。

**修复**：新增环境变量 `ELS_TUTORIAL_ALIAS`（形如 `35240:34240`），把请求折叠到已准入的路线。

**约束**：默认关闭；目标必须已准入；**不新增**路线、奖励或 scope 条目；**未经实机（native）验证**。

### 2.7 启动器「仓库同步」页（`0a44fa7` / `626886a` / `f111635`）

**新增**（`launcher/service.py` +170 行）：

| 方法 | 行为 |
|---|---|
| `repo_state()` | 读取当前分支、脏文件、ahead/behind、远端地址 |
| `repo_commit()` | `add` → `commit` → `fetch` → `rebase`（落后时）→ `push`，逐步返回中文进度 |
| `repo_pull()` | 干净工作区下 `fetch`，`ahead==0` 走 `--ff-only`，否则 `rebase`，失败自动 `rebase --abort` |

- **WinError 2 修复**：从资源管理器启动时找不到 `git`，改为自动探测 Git 安装路径。
- **`626886a`**：工作区干净但有未推送提交时，提交按钮不该再强制要求说明——只有**真的要创建提交**时才校验 `message`。
- **`f111635`**：没有创建提交时，错误信息不再冒用「已提交到本地」的前缀，改为如实报「无法连接 GitHub / 推送失败」。

### 2.8 诊断与资源索引刷新（`0a44fa7`）

更新 `tools/` 下兼容性探针与资源索引（`client_compatibility_profiles.json`、`dx11_resource_compat.*`、`local_resource_index_*`）；`transport.py` / `local_session.py` 提高 memory1 诊断上限并保留本地脚本 spawn 转储（**行为不变**，输出仍在 `state/launcher` 下）。

---

## 三、之前的修复（229 个提交）

> 这一段是索引而不是正文。仓库 `docs/` 下已有 **118 份**按日期命名的说明文件（`*_20261019.md` 5 份 … `*_20261024.md` 16 份），每一项改动的自检、验收边界、渠道快照都在里面。本节只做主题归并，方便定位「哪类问题那时候修过」。

### 3.1 归属与权限校验（贯穿全程，数量最多）

这是整个项目的隐性主线：**每个写操作都要证明「这个角色/账号此刻真的拥有它」**。典型提交：

- `#149` / `#151` / `#153` 拒绝已删除或待处理角色的物品、邮件、分解操作
- `#136` / `#137` 神物操作绑定当前会话与事务账户归属
- `#307` 城镇传送绑定当前角色，并在提交前复核编码
- `560aec4` 校验职业请求的当前身份、阶段与提交边界
- `#160` 普通与神器鉴定绑定当前认证 owner

**价值**：这类修复不产生可见玩法，但决定了存档不会被跨角色污染——是后面所有功能接通的前提。

### 3.2 副本场景退役线（本批 2.2 的上游）

这条线从 10-23 一直修到 10-25，本批的 class-103 判定是它的**收敛点**：

| 提交 | 内容 |
|---|---|
| `#205` / `#206` / `#204` | 接收 34170 / 34180 / 34190 / 34090 的原场景退场 |
| `#201` / `#202` | 拉比、莉缇娅 9319：**拒绝普通死亡误推进** |
| `#200` | 接收原生 tunnel summoner 退役 |
| `#258` | 接受 34320 组队控制器退役 |
| `#232` | 把 source7524 退役绑定到原生控制器身份 |

规律很清楚：**先逐个副本登记「谁退役才算数」，再回头统一判定逻辑**——本批 2.2 就是把 `ISACTIVE` 这个错误前提从判定里拿掉。

### 3.3 任务 / 史诗 / 转职

- `a10d92b` 补齐 **249 项**当前史诗后继与原生任务目标
- `#374` / `#372` 账号史诗 26780 / 26750 的原生对话与契约书、两件奖励
- `#230` 账号一次性 ERP 券任务 53520
- `f5d5246` 领奖 F5 携带当前保存的职业与账号共鸣
- `595cb7f` 限制任务普通经验有效增量，避免 F5 越界

### 3.4 铁匠 / 炼金 / 强化 / 分解

- `#319` 铁匠首次选择与存档（本服 400 初值）
- `#337` 支持无锤强化；`#380` 单次消耗选中的强化锤（事务内）
- `#327` 分解持久化经验与重试状态
- `#321` 按明确沿用规则补齐炼金制造经验收益
- `#138` 重铸 ED 券收窄到三个已核模板

### 3.5 物品 / 仓库 / 商城 / 卡带

- `#346` Tenebros 账号容量扩展（原子 ED + 惰性回执）
- `#382` / `#386` Tenebros 初次鉴定、选项选择
- `#289` / `#291` / `#293` / `#295` 卡带注册、装卸生命周期、D54 单级培养
- `#279` / `#273` 历史时装券的历史持有准入
- `#129` 放开 234 种已核发型的原生染色
- `#236` GM 绑定兑换码与原生商城单次领取

### 3.6 ERP / 共鸣 / 技能页

- `#16` 原生 ERP 页面与复现的考勤 / 在线事件
- `#146` 普通 ERP 代币准入与旧回执重放
- `#339` 共鸣书当前 actor 权威
- `#357` / `#393` 普通 ED 技能页开通、购买后立即展开
- `#225` 普通技能页布局按当前认证 actor 持久化

### 3.7 钓鱼 / 家园 / 公会 / 组队

- `#385` 原生鲁本钓鱼场 1500 的准入、保存与返回
- `#422` 钓鱼来源与交易链；`#403` 手持鱼兑换；`#411` 钓鱼装备穿卸与冷登同步
- `#405` 七日家园契约首用与冷登同步；`#426` 有限家园房间与 26770 任务
- `#424` 原生公会成员与 35630 任务
- `#343` 普通组队招募；`#418` 组队挑战事务与生命周期边界

### 3.8 启动器 / 部署 / 资源

- V29 → V36 各版本启动器源归档（`#2` `#85` `#95` `#401` `#428`）
- `#45` V31 启动诊断在运行时准备前可用
- `#109` DX11 拒绝遗留 B6F 方向；`612b619`
- `8440a98` 隔离 CI，并记录私有分支保护的局限

### 3.9 记录类提交（28 个）

`Record accepted … / docs: … / Reconcile … / Archive …` 这类提交**不改代码**，只把「本地已验证 + 线上已验收」的双端快照、渠道指纹、来源清单写进仓库。它们的作用是**让每次改动可追溯**——这也是为什么 `docs/` 会有 118 份文件。

---

## 四、测试

**运行方式**（需要 vendor 里的 pycryptodome）：

```bash
cd tests
PYTHONPATH="../vendor;..;." python -m unittest test_scene_actor_native_expiry test_lithia_memory3_retirements \
    test_lithia_stage1_barrier test_seal_quests
```

**结果**：

| 测试模块 | 用例数 | 结果 |
|---|---|---|
| `test_scene_actor_native_expiry`（新增） | 6 | ✅ 全通过 |
| `test_lithia_memory3_retirements`（新增） | 4 | ✅ 全通过 |
| `test_lithia_stage1_barrier`（改造） | 8 | ✅ 全通过 |
| `test_seal_quests`（+3 用例） | 19 | ⚠️ 7 失败 / 1 错误 |

**新增用例覆盖的关键不变量**：

- 声明为 active 的 class-103 花能正常退役且**不给奖励**；普通战斗 actor **仍然拒绝** native 过期；
- source-pinned 控制器**不会**被通用路径吞掉；外部 owner 的伪造报告仍被拒；
- 9310 退役 → 28110 计分 + part 结束；9470 迟到报告只确认；9470 先到不结束 part；重放幂等；
- 转职任务后 career 上下文被重建（job quest 与莉缇娅第一转职两条路径）。

**关于那 8 个失败**：在改动前的 `32fd679` 上建独立 worktree 做对照，`test_seal_quests` 同样 16 个用例、**同样这 8 个失败**。即这些失败**在本次改动之前就存在**，与这批提交无关（新增的 3 个用例全部通过）。

---

## 五、遗留问题与风险

| 级别 | 问题 | 说明 |
|---|---|---|
| 高 | `test_seal_quests` 8 个既存失败 | 本批未修也未恶化；涉及奖励失败码、死亡去重、背包回滚等断言，建议单独立项 |
| 中 | 提交信息 `69e42c4` 为「测试提交」 | 实际含 class-103 判定重构 + 转职上下文 + 5 个测试文件，信息与内容不符，追溯困难 |
| 中 | `main` 只允许 squash 合并 | 合并后 5 个提交被压成 1 个，本地历史与远端分叉，需同步一次 |
| 中 | 本机 `github.com:443` 不通 | 启动器的推送/拉取在此环境仍然失败，需代理或走 API |
| 低 | `ELS_TUTORIAL_ALIAS` 未经实机验证 | 已默认关闭，不新增路线/奖励，风险可控 |

---

## 六、附录：本批变更文件清单

**服务端逻辑**

```
els_server/domain/dungeon_flow.py                  退役确认 + class-103 判定
els_server/domain/dungeon_spawns.py                场景控制器家族登记（四重守卫）
els_server/domain/dungeon_routes.py                ELS_TUTORIAL_ALIAS、npc_initialization(native=)
els_server/domain/lithia_memory1_retirements.py    stage1 终点改为 9310
els_server/domain/local_session.py                 脚本 spawn 转储
els_server/domain/quest_flow.py                    转职后补发 career_notice
els_server/domain/story_controller_retirements.py  重构：source_pinned + 规则表
els_server/domain/tutorial_dialogue.py             序章对话
els_server/storage/seal_quests.py                  class_changed / retire 类型
els_server/transport.py                            memory1 诊断上限
```

**启动器**

```
launcher/__main__.py    Git 自动探测
launcher/app.js         仓库同步页面、提交按钮校验调整
launcher/service.py     repo_state / repo_commit / repo_pull、错误信息如实化
```

**工具与配置**

```
tools/client_compatibility_profiles.json
tools/dx11_resource_compat.js / .json
tools/local_resource_index_compat.py / _probe.js
tools/local_shortcut_totals.py
tools/local_stack_limits.py
tools/probe_updated_client.py
```

**测试**

```
tests/test_scene_actor_native_expiry.py     （新增）
tests/test_lithia_memory3_retirements.py    （新增）
tests/test_lithia_stage1_barrier.py         （改造）
tests/test_seal_quests.py                   （+3 用例）
tests/test_lithia_native255_guard.py        （调整）
```

---

*本文档基于 234 个提交的实际 diff、118 份 `docs/` 说明与实测结果整理；测试结论经改动前后对照验证。*
