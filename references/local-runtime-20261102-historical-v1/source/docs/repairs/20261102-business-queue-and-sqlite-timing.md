# 11-02 第二批：业务队列 + SQLite 计时（调度器四层里的第 ①② 层）

前一份 `docs/SCHEDULER_ARCHITECTURE_SURVEY_20261102.md` 把五个红模块按风险分成四层。
本文记录第 ①② 层落地情况。第 ③（`periodic_scheduler` + transport 主循环）与
第 ④（`read_scope` 换代）**没有动**。

## 装进来的三个文件（逐字节照抄，未手改）

| 文件 | 行数 | 出处 |
| --- | --- | --- |
| `els_server/business_queue.py` | 96 | `references/peak-business-concurrency-20261027-v1/online/els_server/business_queue.py` |
| `els_server/storage/sqlite_timing.py` | 61 | `references/peak-business-concurrency-20261027-v1/online/els_server/storage/sqlite_timing.py` |
| `els_server/performance.py`（换代） | 116 | `references/peak-business-concurrency-20261027-v1/online/els_server/performance.py` |

`sqlite_timing` 有两份归档：`quest-business-locks-20261027-v1` 那份 42 行、没有
`commit_write`；`peak-business-concurrency-20261027-v1` 那份 61 行，是它的超集
（多 `_busy`、`commit_write`、以及 `write_transaction` 里的 COMMIT 等待计时），
`test_peak_business_concurrency` 的 `SQLiteTests` 要 `commit_write`，所以取后者。

`performance.py` 换代只差两处（`diff` 全文只有这两个函数）：

1. `sqlite_observed` 多 `finish` / `finish_busy` 两个参数，`snapshot` 多聚合
   `sql_finish_busy`，p95 键多 `sql_finish_wait_ms`——`sqlite_timing` 需要它们。
2. `local_auxiliary_noop` 判定收紧成只认 `account is application.account`。
   **本地不可达**：`session_auxiliary.py:31` 先查
   `'local_auxiliary_noop' in LocalSession.handle.__code__.co_names`，本地为假直接返回，
   函数体永远不执行；`test_server_latency_guards` 里真正调用它的三条也带同样的
   `skipUnless` 守门。换前换后行为一致，`test_auxiliary_worker_activity` 仍 7 绿 1 skip。

## `application.py` 的接线（唯一手写部分）

```python
self.business_queue=BoundedBusinessQueue(self.executor)   # 16 许可准入闸门
self.performance=OperationMetrics()

async def call(self, function, *args, **kwargs):
    return await self.business_queue.run(
        partial(self._worker_call,function,args,kwargs,time.perf_counter(),captured_calls()))
```

`call()` 原本是 `run_in_executor(self.executor, invoke)`，现在换成队列 `run()`。
`invoke` 的内容原样搬进 `_worker_call`，只加了计时：

- `queue_ms`（提交到开工）、`handler_ms`、`domain_ms`、`clock_before_ms` /
  `clock_after_ms`（活动时钟前后观测）、`after_reply_ms`；
- `worker_timing(sample)` 包裹，SQL 的 BEGIN/COMMIT 等待与 BUSY 由 `sqlite_timing`
  写进同一个 sample；
- 每个 sample 交给 `performance.record(函数名, sample)`，`capture_calls()` 时另存副本。

计时字段的写法取自 `references/shared-request-latency-20261031-v1/local/`（10-31 代），
但**没有**引入它同代的 `request_category`、`native_session_sources.capture`、
`business_queue.run(timing=...)`——那些要连带换 `business_queue` 与另外两个模块，
本轮刻意不做。所以本轮队列仍是 10-27 代签名，只有 `run(function)`。

`close()` 里先 `business_queue.close()`（取消尚未提交的等待者），再
`executor.shutdown(wait=True)`（已开工的 SQL 仍允许提交/回滚）。

## 两处写事务接上 `write_transaction`

`test_quest_lock_boundaries` 会 `patch('els_server.domain.tutorial_quests.write_transaction')`
与 `patch('els_server.storage.item_expiration.write_transaction')`，要求这两个写入点走计时器。

- `domain/tutorial_quests.restore_initialization`：`with closing(connect(...)) as db,write_transaction(db):`
  （原来是 `as db,db:` + `db.execute('BEGIN IMMEDIATE')`）——同一点、同一个
  BEGIN IMMEDIATE、同样的提交/回滚语义，只多了计时。
- `storage/item_expiration.remove_due`：先做只读探针（`BEGIN` 读一次再 `rollback`），
  确认有到期物品后才进 `with write_transaction(db):`。没有到期物品时**不碰写锁**，
  `test_idle_expiry_and_circuit_preview_do_not_reserve_writer` 因此通过。

两个文件本来就是 CRLF，改写后行尾保持 CRLF，`git diff` 只有真实改动
（`tutorial_quests` 4 行、`item_expiration` 57 行含缩进）。

## 验证

### 端到端冒烟

`Application(ServerConfig(profile='bootstrap'))` 起得来；`call(lambda: 42)` → 42；
带关键字参数 → 12；20 个并发 `call` 全部返回且 `business_queue.maximum == 16`
（闸门生效、无丢失）；返回后 `inflight == 0`。

### 六个手工模块（门禁白名单不含它们，必须单独跑）

`test_peak_business_concurrency` 现在能加载：`QueueTests` 6 条里 5 条绿、`SQLiteTests` 6 条全绿、
`GrowthIdentityTests` 1 条红。两条红各有归属，都不在 ①② 范围：

- `test_application_periodic_and_direct_calls_share_capacity`：要 `Application.periodic_batch`
  （第 ③ 层）。
- `test_finalizer_uses_current_owned_identity_without_full_dto`：要
  `selected_2026_growth_runtime` 的 finalizer 改读 `character_identity()` 而不是全量 DTO
  （窄读改造里的一处，独立于调度器）。

相对改动前：

| 变化 | 条目 |
| --- | --- |
| 修好 3 条 | `test_quest_lock_boundaries` 由 import 失败变为可运行；`QueueTimingTests.test_queue_wait_is_distinct_from_handler_and_keyword_arguments_work`、`test_exception_is_counted_and_does_not_poison_next_operation` 转绿 |
| 新露出 4 条 | `test_quest_lock_boundaries` 的 4 条（见下），此前被 import 失败整体挡住 |
| 未变 | `test_auxiliary_worker_activity` 7 绿 1 skip（`_worker_call` 存在后
`test_worker_reports_activity_stage_costs` 解除 skip 并转绿）；`test_selection_business_*`
与 `test_server_latency_guards` 的注册表/日志类红均为改前既有 |

`test_quest_lock_boundaries` 剩下 1 条红（原先 4 条，另有 3 条见下节已修）：

1. `test_existing_tutorial_read_does_not_reserve_writer_or_change_wire`：要求
   `restore_initialization` **不写就不占写锁**。我们的实现一直是无条件
   `BEGIN IMMEDIATE`（改前也如此，只是那时模块 import 失败看不出来），
   上游是整代重写才做到惰性写入——它得先把 `ensure()` 的建表、`load_character`
   等也挪到只读阶段，属于重写而非接线，本轮不做。

## 后续小件：`reward_state` 计时 + `epic_followups.deferred_write_possible`

上面那 4 条里有 3 条只是缺两个东西，已补：

- **`storage/epic_followups.deferred_write_possible(db,uid)`**：从
  `references/quest-business-locks-20261027-v1/` 原样追加（18 行，纯新增，不改任何现有函数）。
  它只做「保守排除」——返回 True 也不授权接取，真正的接取仍走 `restore_deferred` 的全部校验。
- **`storage/reward_state.RewardState.grant` 接入写锁计时**。本地这份与归档版差一代
  （236 vs 259 行，整文件 497 行差异），所以没有整文件替换，只改三处：

  ```python
  acquired=None;committed=False
  try:
      if transaction is None:acquired=begin_write(db)       # 原 db.execute('BEGIN IMMEDIATE')
      ...
      if transaction is None:
          db.commit();committed=True                        # 两处提交都标记
  finally:
      if transaction is None:
          try:db.close()
          finally:
              if acquired is not None:end_write(acquired,failed=not committed)
  ```

  三条测试锁定的语义都保住了：
  - `test_manual_reward_busy_is_preserved_and_observed`：`_connect(timeout=.02)` +
    外部占写锁 → `begin_write` 抛 `OperationalError`，`sql_busy==1`、
    `sql_begin_wait_ms>10`；
  - `test_manual_reward_error_rolls_back_and_retry_stays_once_only`：编码失败 →
    `sql_rollbacks==1`，存档不变，重试只生效一次；
  - `test_shared_reward_writer_is_not_committed_or_timed_as_a_new_writer`：调用方传入
    `transaction=db` 时既不 begin 也不 commit，`sql_begin_wait_ms` 保持 0——
    写锁归属仍归调用方。

  与归档版的一处有意偏离：归档用 `failed=sys.exc_info()[0] is not None` 判定回滚，
  这里改用显式的 `committed` 标记。原因是 `grant` 内部有被吞掉的异常分支，
  `exc_info()` 可能在成功路径上残留非空值，从而把「已提交」误记成「回滚」。

结果：`test_quest_lock_boundaries` 12 条里 11 绿 1 红；
`test_reward_state` 全绿；`test_initialization_readers` 仍是既有的 5F/10E。

### 存档写路径回归组（11 个模块）

`test_item_expiration`、`test_reward_state`、`test_seal_quests`、`test_region_quest_flow`、
`test_region_quests`、`test_quest_expiry_regressions`、`test_initialization_readers`、
`test_request_read_scope`、`test_inventory_reward_acceptance`、
`test_reward_relogin_acceptance`、`test_durable_reward_acceptance`：

改动前后都是 **23 红**，`FAIL:` / `ERROR:` 清单 `diff` 完全一致。写路径没有回归。

（`test_inventory_rewards` 在 import 期就 `AssertionError: Full bag grant accepted`，
是既有的装配期断言，与本节无关，跑这组时要排除，否则整批中断。）

## 回退

```
git checkout HEAD -- els_server/application.py els_server/performance.py \
    els_server/domain/tutorial_quests.py els_server/storage/item_expiration.py
rm els_server/business_queue.py els_server/storage/sqlite_timing.py
```

`business_queue` / `sqlite_timing` 只被 `application.py` 与两个写入点引用，回退干净。

## 下一步

第 ③ 层（`preparation.py` + `periodic_scheduler.py` + `Application.periodic_batch` +
transport 的 `serve()` 接线）尚未开始。其中 `periodic_batch` 还依赖
`FriendsSession.periodic_notifications` 接受 `_rooms` 参数以共享房间轮询——这一处
归档里有实现、我们树里没有，是 ③ 里除 transport 之外的第二个手写点。
