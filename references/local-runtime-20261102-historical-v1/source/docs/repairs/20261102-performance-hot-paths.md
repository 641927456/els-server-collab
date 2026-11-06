# 11-02 从 `dungeon-lag` 包里摘出来的三处纯性能改动

## 来源与判定

`refs/dungeon-lag-integration-20261101-v1/` 是上游交付的一个「卡顿整改」候选包，
`source.patch` 共 44 个 hunk、19 个文件。逐条对着现代码树比对的结果：

| 归类 | hunk 数 | 能否直接装 |
| --- | --- | --- |
| ① 定时任务改成「每连接 FIFO 排队位」 | 主体 | **装不进** |
| ② 后台写库 `timeout=10 → 0`，遇 `SQLITE_BUSY` 立刻放手 | 若干 | 部分能装，依赖 ① 的队列 |
| ③ 去掉重复校验、收窄读路径 | 少量 | **能装，本轮摘的就是这部分** |

能对上的只有 12 处，29 处上下文不符，另外 3 个文件在**我们的运行树**里根本没有
（`els_server/periodic_scheduler.py`、`els_server/performance.py`、
`els_server/storage/pet_support_periods.py`）。

这里要分清「仓库里没有」和「运行树里没有」：仓库里全都有。`periodic_scheduler.py`（129 行）
和 `pet_support_periods.py`（72 行）这个包里就带**完整文件**
（`refs/dungeon-lag-integration-20261101-v1/normal/shared/`），`performance.py` 见下节，
`sqlite_timing.py` / `business_queue.py` 则只存在于更早的
`references/peak-business-concurrency-20261027-v1/`、`references/character-slow-paths-20261027-v1/`、
`references/quest-business-locks-20261027-v1/` 等归档里（这个包本身不带）。

真正的缺口不是文件，是**接线**：上游那套调度器来自
`references/server-structure-20261029-v1`，比我们的树晚一代。我们的定时任务是
`LocalSession.periodic_notifications()`（`application.py:125`）一个函数内联跑完，
靠 `now >= self.next_periodic` 做 1 秒闸门，每会话各算各的；上游是把到期任务登记进
每连接 FIFO 排队位、由 `PeriodicScheduler` 统一驱动。`application.py` / `local_session.py`
这次**不在补丁里**（包里没有它们的新版），所以「把文件放进去」并不能让任何东西生效——
必须改主循环本身。这就是 44 个 hunk 里 29 个对不上上下文的原因：不是代码丢了，
是它假设的行号和周围代码与我们不同代。

所以本轮只做 ③，全部是**行为不变、只减少重复工作**的改动。

## 一、`els_server/performance.py`（新增，123 行）

源：`references/character-slow-paths-20261027-v1/engine/local/els_server/performance.py`，取 **local**
变体。选 local 的依据不是猜的：`LocalSession.handle` 的 `co_names` 里没有
`local_auxiliary_noop`，说明本地路径永远不会调到那个函数，两个变体在本地等价。

导出 8 个符号：`capture_calls`、`captured_calls`、`worker_timing`、`projection_loaded`、
`registry_checked`、`sqlite_observed`、`OperationMetrics`、`local_auxiliary_noop`。

装了它之后 `tests/test_auxiliary_worker_activity` 7 条转绿（另有 1 条 skip）。

## 二、物品编码器去掉重复校验（`els_server/domain/inventory_items.py`）

原来的 `inventory_payload()` 把每件物品**校验两遍**：先 `_checked_items` 全量
`validate_item`，再在 `item_body(i)` 里又 `validate_item` 一次。约 16% 的编码时间花在
第二次校验上。

改法与上游 `source.patch` 逐字节一致（local / online 两个变体的这三处 hunk 内容完全相同）：

```python
def item_body(item):
 return _item_body(validate_item(item))

def _item_body(item):
 # Internal encoder for the canonical item returned by validate_item.
 ...

def _checked_items(items):
 ...
 return checked

def inventory_payload(items):
 checked=_checked_items(items)
 return struct.pack('>I',len(checked))+b''.join(...+_item_body(i)+... )
```

`inventory_restore_map()` 同步改成 `checked=_checked_items(items)` + `bodies={uid: _item_body(i)}`，
这样「穿在身上的物品也要过线包校验」这条既有语义被保留（原来靠 `inventory_payload(items)`
顺带校验），但只编码一遍。

**实测**（同进程内对拍 15 轮）：

| | 中位 | 最小 |
| --- | --- | --- |
| 改前 | 23.42 ms | 18.49 ms |
| 改后 | 19.21 ms | 14.24 ms |

约 −18%。四个角色的 `inventory_payload` 字节指纹**完全未变**——这是硬要求，线包一个字节
都不能动。

## 三、`observe()` 的 Artifact 窄读（`artifact_flow.py` + `characters.py`）

原来 `observe()` 每批回复都走 `s.account.character()`，那是**全量投影**：`characters.get()`
一次要跑十几个子查询（生命/体力、共鸣、称号、任务、自定义、EP、技能页、背包容量、职业
状态……），而它真正只用到 `uid`、`master`、`unit_type`、`artifact` 四个字段。

改成：

```python
character=s.account.characters.artifact(s.account.uid);a=character.get('artifact')
```

`Characters` 新增两个方法：

- `_identity(db, uid)`：从 `identity()` 里抽出来的窄读（含 `character_lifecycle` 已终结删除的
  边界判断）。
- `artifact(uid)`：一个只读快照里同时取「身份 + 神器」，避免把新神器配上旧的所有者/等级。

### 与上游的一处偏离（有意）

上游 `artifact()` 用的是 `read_scope.snapshot_connection()`，而**当前树的 `read_scope.py` 里
没有这个函数**——它属于上面说的调度器架构（`_ReadScope.files` / `_ReadScope.readers` 那套
「按文件 inode 失效」的机制，当前版本只有 `data_version`）。为一个窄读引入整套架构不划算。

替代做法：用一条独立连接 + 显式 `BEGIN`，两个查询在同一读事务里，一致性语义等同；
`closing()` 退出时连接关闭、只读事务自动回滚，不留悬挂事务。

另外上游 `_identity()` 会往返回字典里塞 `account_id`，本轮**没有**加——`identity()` 的返回结构
被 `local_session.character_identity()` 直接透出，加字段属于无必要的形状变更。

### 验证

在存档副本上（不打真存档）跑通：`identity()` 返回结构逐字段不变、`artifact()` 多出且只多出
`artifact` 一个键、`artifact_wire()` 编出 40 字节、`0x201/0x904` 通告能构造、未知 uid 仍
`ValueError: Unknown character`。

## 本轮没做的

- `els_server/periodic_scheduler.py`、`els_server/business_queue.py`、
  `els_server/storage/sqlite_timing.py`：属于调度器架构，缺它们导致
  `test_architecture_scheduler`、`test_peak_business_concurrency`、`test_quest_lock_boundaries`、
  `test_character_slow_paths`、`test_path_projection_boundaries` 五个模块连 import 都过不去。
- `read_scope` 的 `inventory_projection` / `checked_paths`：同上。
- `boosting_2026_quests._participant` 的窄读：该文件 5 个 hunk 上下文全部不符，
  `test_initialization_readers` 里 5F/10E 就是卡在 `t=self._store(db)` 那行（测试的 fail 断言
  要求「判断资格时不许构造奖励/档案 store」）。要改得先对齐它当时的版本。
- `inventory_state.py` / `bank_state.py` 的窄读：依赖 `snapshot_connection`，同上。

## 门禁

全量 `python tools/run_release_tests.py release-tests.json --server`：**389 条 / 23 失败 / 61 错误
/ 1 跳过**。上一轮基线（10-31 交接文档记录）是 23 / 62，即失败数持平、错误数少 1。

失败数持平不等于同一批，所以另做了一组对照实测（同一目录法，只回退本轮这 3 个文件、不动
另一会话的 13 个未提交文件）：

| | 测试数 | 失败 |
| --- | --- | --- |
| 回退到 HEAD（`test_decomposition` / `test_potion_moves` / `test_bag_capacity` / `test_bag_ui_moves` / `test_equipment_moves` / `test_session_clock`） | 28 | 9 |
| 装回本轮改动 | 28 | 9 |

两份 `FAIL:` 清单 `diff` **完全一致**，说明这批红是既有的，与编码器/窄读无关。

## 回退

三处互不依赖，可单独回退：

```
git checkout HEAD -- els_server/domain/inventory_items.py   # 编码器
git checkout HEAD -- els_server/domain/artifact_flow.py els_server/storage/characters.py
rm els_server/performance.py                                # 该文件是本轮新增
```
