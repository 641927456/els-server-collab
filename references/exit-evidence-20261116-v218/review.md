# 退出证据上报独立审查

2026-11-16。候选通过独立审查，可以进入整合。未发现本次增量引入的阻断项。

候选为 `exit-evidence-candidate/tools/gameplay_error_reporter.py`，SHA-256 为 `92f886ad4467f54517d9fb514506abf98141c524f1901292c7e9300bc2f348cd`。父版取自 V217 `runtime/combined/tools/gameplay_error_reporter.py`，SHA-256 为 `6ba9b004d993ebb98cd897dc2b978f99c628034716c0f353f2ce6f1f844b11f2`。两项均与 `change.json` 相符。

差异只有一段字段复制。`abnormal_exit` 和 `observer_crash` 观察记录增加 `latest_observed_exit`、`exit_caller_module`、`latest_observed_exit_api_return`、`latest_instrumentation_detached`，沿用 V217 `RunContextJournal.snapshot()` 的结果。

这四项由 journal 的固定字段选择产生。退出 API 限于已知名称，地址为最多 16 位十六进制，模块名和实例标签最多 128 字符，线程、时间、返回值均经过原有类型与数值范围检查。调用者模块来自保留的加载范围。缺少退出记录时仅保留 unknown 模块状态，不生成退出地址。

复制后继续经过 `diagnostic_sanitize()` 和 `clean_values()`。实际测试确认凭据值与带秘密字段名的内容被脱敏，原始堆栈和内存字段仍被摘要化。恶意原始事件中的任意附加字段先被 journal 丢弃。典型异常退出记录为 1804 字节，observer crash 为 1807 字节。最大合法字段样例为 2817 字节，其中新增四项增加 2108 字节，低于现有单记录处理阈值。

字段名称保留“最近观察”含义。候选没有把最近的退出 API 返回与退出请求自动配对，也没有据此生成根因结论。对其他错误信号的输出与父版逐字段相同，正常原生提示继续过滤，正常 exit 0 且无其他错误时不新增退出报告。

独立执行了 10 项定点测试，全部通过，覆盖以下路径。

- 两种目标信号保留四字段，空 journal 的 unknown 状态保持可见。
- 其他信号与父版等价，正常提示和正常关闭行为保持。
- journal 字段边界、恶意附加字段、凭据及堆栈清洗。
- 实际 `GameplayErrorReporter.close()` 写本地 JSON、生成 ZIP 并通过 `validate_archive()`，以及 observer crash 路径。
- 发送函数失败后仍保留本地退出证据并记录失败回执。

测试使用正式 V217 journal、候选 reporter、临时合成记录和替代发送函数。实际运行结果保存在 `exit-evidence-independent-tests.json`，逐项日志在 `exit-evidence-independent-tests.log`，测试源码在 `test_exit_evidence_independent.py`。本次没有启动游戏、访问玩家进程或执行网络上传。原生故障原因仍需结合新增证据判定。
