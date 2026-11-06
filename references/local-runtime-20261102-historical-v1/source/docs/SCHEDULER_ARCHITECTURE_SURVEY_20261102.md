# 调度器架构调研（11-02）：五个红模块各自要什么、风险在哪

`dungeon-lag` 包的「核心」装不进现代码树的结论已写进 `docs/repairs/20261102-performance-hot-paths.md`。
本文把五个 import 失败的测试模块逐一拆开：每个模块缺什么、源码在哪一行归档里、
接线要动哪些文件、风险在哪。

> **进度（11-02 下午）**：第 ①② 层已落地，见
> `docs/repairs/20261102-business-queue-and-sqlite-timing.md`。
> `test_peak_business_concurrency` 除一条依赖 `periodic_batch` 的用例外全绿；
> `test_quest_lock_boundaries` 已可运行，剩 4 条卡在 `quest-business-locks` 那一整批
> （惰性写锁、`epic_followups.deferred_write_possible`、`reward_state` 计时）。
> 第 ③④ 层未动。

## 总览

| 测试模块 | 卡点 | 缺的东西 | 源码在哪 | 接线要动 |
| --- | --- | --- | --- | --- |
| `test_quest_lock_boundaries` | 缺 `sqlite_timing` | `storage/sqlite_timing.py`（61 行，完整） | `references/quest-business-locks-20261027-v1/` | performance 换 online 变体 |
| `test_peak_business_concurrency` | 缺 `business_queue` | `business_queue.py`（96 行，完整） | `references/peak-business-concurrency-20261027-v1/` | `Application.call` 走队列、加 `app.business_queue` |
| `test_architecture_scheduler` | 缺 `periodic_scheduler` | `periodic_scheduler.py`（129 行，完整） | 包内 `refs/dungeon-lag-.../normal/shared/` | **transport 主循环重写**、`Application.periodic_batch`、`preparation`、账号两阶段 |
| `test_character_slow_paths` | `read_scope` 缺符号 | `inventory_projection`（时间戳缓存） | `references/character-read-boundaries-20261027-v2b/` | **read_scope 整个换代**（80 → 154 行） |
| `test_path_projection_boundaries` | `read_scope` 缺符号 | `checked_paths`（路径白名单解析） | 同上 | 同上 |

新增代码合计约 **330 行**，全部有完整归档，不需要手写。真正的成本在**接线与回归**，
不在抄文件。

## 一、最浅的一层：`sqlite_timing` + performance 换代

`test_quest_lock_boundaries` 只 `from els_server.storage.read_scope import committed_reads`——
这个符号**现在就有**。它真正缺的是 `els_server.storage.sqlite_timing` 的
`write_transaction` / `commit_write`：把 BEGIN 的等待、COMMIT 的等待、BUSY 次数、回滚次数
分开记到 `worker_timing(sample)` 里（`sql_begin_wait_ms` / `sql_finish_wait_ms` /
`sql_busy` / `sql_finish_busy` / `sql_rollbacks`）。

但归档版 `sqlite_timing` 调的是 `sqlite_observed(wait=..., held=..., finish=...,
busy=..., finish_busy=..., rollback=...)`，而我们 11-02 装的 local 变体**没有 `finish` /
`finish_busy` 两个参数**。`diff` 显示 local 与 online 变体只有两处不同：

1. `sqlite_observed` 的签名与计数键（online 多 `finish` / `finish_busy`，`snapshot`
   多聚合 `sql_finish_busy`，p95 键多 `sql_finish_wait_ms`）。
2. `local_auxiliary_noop` 的判定（online 版只认 `account is application.account`，
   local 版另认 root 绑定的角色账号）。

**换 online 变体的安全性**：`session_auxiliary.py:31` 的
`if 'local_auxiliary_noop' not in LocalSession.handle.__code__.co_names: return False`
守卫在 import 之前，本地 `LocalSession.handle` 里没有这个名字，函数体永远不会执行——
所以两个变体在本地都不可达，换过去不改变任何行为。`test_server_latency_guards` 里
真正调用 `local_auxiliary_noop` 的三条测试有
`@unittest.skipUnless('local_auxiliary_noop' in LocalSession.handle.__code__.co_names, ...)`
守门，本地照样 skip。需要复核的只有 `test_auxiliary_worker_activity`（11-02 刚转绿的
7 条）——换完重跑即可。

风险：**低**。改动 = 覆盖 `performance.py`（123 → 116 行）+ 新增 `sqlite_timing.py`（61 行）。

## 二、中层：`business_queue` + `Application.call` 改走队列

`BoundedBusinessQueue`（96 行）是给现有单 worker 线程池加一个 16 许可的准入闸门：
256 个生产者排队时 `inflight == 16`、`len(waiters) == 240`、线程池积压 ≤15；
取消风暴不得提前还许可；已在跑的 SQL 被 cancel 也要跑完提交。

接线点（`application.py`）：

- `__init__` 加 `self.business_queue=BoundedBusinessQueue(self.executor)`；
- `call()` 的 `run_in_executor(self.executor, invoke)` 改成 `self.business_queue.run(invoke)`；
- 测试还要 `app.call` 支持**关键字参数**（`test_queue_wait_is_distinct_from_handler_and_keyword_arguments_work`）。

`Application.call` 是**所有**会话操作的必经之路（登录、交易、制造、副本结算全走它）。
加闸门本身不改变语义（容量 16 > 现实并发），但任何排队/取消的边角 bug 都会放大成
全服卡顿或丢提交。归档版对取消竞态处理得很细（`state['abandoned']` + `add_done_callback`
+ `asyncio.shield`），建议**整文件照抄，不手改**。

风险：**中**。改动小，但影响面是全部操作；用全量门禁 + 双跑对比兜底。

## 三、深层：`periodic_scheduler` + transport 主循环重写（本轮判定「装不进」的主体）

`PeriodicScheduler`（129 行，包内完整）替换的是 `transport.py:154` 这个循环：

```python
# 现在：每条连接一个协程，自己掐点
async def notify_periodically():
    while True:
        ...
        await send(await self.application.call(business.periodic_notifications), ...)
```

改成：连接注册进 `scheduler.serve(session, operation_lock, send)`，由统一的
`_run()` 按到期时间挑最多 16 个、调 `application.periodic_batch(sessions)` 一次跑一批。
测试锁定的语义：

- 64 连接分 4 批、每批 ≤16、迟到者不丢（`test_sixty_four_peers_...`、`test_staggered_deadlines_...`）；
- 操作锁被占的连接**跳过本批**而不是堵住整批（`busy_skips`）；
- 慢发送者不拖别人（`test_slow_sender_does_not_block_...`）；
- 断线时等在途工作做完才解锁（`test_disconnect_during_worker_...`）；
- `WorkerBatchTests`：一批内每成员**各自**进 `committed_reads()` 作用域、房间 poll 只跑
  一次、`performance.snapshot()['periodic_notifications']['count']` 按成员计数。

除了 `periodic_scheduler.py`，还需要：

- `els_server/preparation.py`（45 行，`BoundedPreparation`/`PreparationBusy`，在
  `references/server-architecture-20261027-v1/`）和 `app.preparation` 属性；
- `Application.periodic_batch()` 方法（归档 `application.py` 里有现成实现，但我们的
  `application.py` 与它差异很大，只能摘方法不能整文件换）；
- `app.performance` / `app.business_queue` 属性（`_run` 里直接取用）；
- `scheduler` 的创建与每条连接的 `serve()` 接线——这部分归档里的 `transport.py` 我们没有
  完整对照，**要自己写**，这是唯一没有现成字节的地方。

风险：**高**。断线/慢发送/锁竞争路径全变；现有 389 条门禁里副本与抓包校验不覆盖这些
路径，只能靠 `test_architecture_scheduler` 自己 + 手工压测。这就是它被单列一轮的原因。

另注：`CredentialTests` 五条要账号注册改成两阶段
（`prepare_registration` / `prepare_password_login` / `finish_*` / `_finish_credentials`），
等于把 `accounts_gateway.py` + `storage/accounts.py` 一起换到那一代。**建议不做**，
让这五个模块红着这两条即可。

## 四、最深：`read_scope` 换代（80 → 154 行）

`test_character_slow_paths` 要 `inventory_projection(account, inventory, load)`——
带 `time.time()` 时间戳的缓存（测试 patch `read_scope.time.time` 100→101 验证失效）；
`test_path_projection_boundaries` 要 `checked_paths()`——路径白名单解析器，还要
`patch('els_server.storage.read_scope.snapshot_connection', ...)` 能打上（说明它 import
时就引用这个符号）。

归档 v2b 版（154 行）相对我们 80 行版多出：`_ReadScope.files` / `readers` 两个字典
（按**文件 inode** 失效，而不只是 `data_version`）、`snapshot_connection()`、
`inventory_projection()`、`checked_paths()`。

风险：**高且面广**。`read_scope` 是所有会话读路径的底座，`role_projection` 的缓存语义
从「`data_version` 变了就重算」变成「同文件 + TTL 内直接复用」，现有测试的时序假设
可能大面积翻车；而且 11-02 刚提交的 `Characters.artifact()` 用的普通连接也可以顺势
换成 `snapshot_connection`。**建议最后做，或与调度器同一轮做**——`snapshot_connection`
本来就是调度器那代的东西。

## 建议执行顺序（风险从低到高，每步独立可回退）

1. **performance 换 online 变体 + `sqlite_timing.py`**（约 60 行新增）。
   收益：`test_quest_lock_boundaries` 可 import；`test_peak_business_concurrency` 的
   `SQLiteTests` 六条可跑。风险低。
2. **`business_queue.py` + `Application.call` 改队列**（约 100 行新增 + 5 行改动）。
   收益：`QueueTests` 六条 + `test_peak_business_concurrency` 全绿。
3. **`preparation.py` + `periodic_scheduler.py` + `periodic_batch` + transport 接线**。
   收益：`test_architecture_scheduler` 的 `SchedulerTests` / `PreparationTests` /
   `WorkerBatchTests`。风险高，做之前先出 transport 接线草案。
4. **`read_scope` 换 v2b + 窄读消费方**。收益：剩下两个模块。风险最高，单独一轮。
5. **不做**：`CredentialTests`（账号两阶段）。

每步做完跑一次全量门禁（约 13.5 分钟）对比红绿清单；任何一步清单变长就停下回退。

## 附：各源文件字节出处

| 目标文件 | 行数 | 出处 |
| --- | --- | --- |
| `els_server/storage/sqlite_timing.py` | 61 | `references/quest-business-locks-20261027-v1/online/els_server/storage/sqlite_timing.py` |
| `els_server/business_queue.py` | 96 | `references/peak-business-concurrency-20261027-v1/online/els_server/business_queue.py` |
| `els_server/performance.py`（换代） | 116 | `references/peak-business-concurrency-20261027-v1/online/els_server/performance.py` |
| `els_server/preparation.py` | 45 | `references/server-architecture-20261027-v1/engine/online/els_server/preparation.py` |
| `els_server/periodic_scheduler.py` | 129 | `refs/dungeon-lag-integration-20261101-v1/normal/shared/els_server/periodic_scheduler.py` |
| `els_server/storage/read_scope.py`（换代） | 154 | `references/character-read-boundaries-20261027-v2b/online/els_server/storage/read_scope.py` |
| `Application.periodic_batch` | — | `references/server-architecture-20261027-v1/engine/online/els_server/application.py`（摘方法） |
| transport 的 `serve()` 接线 | — | **无现成字节，需自写** |
