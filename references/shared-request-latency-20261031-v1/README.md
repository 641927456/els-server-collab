# 辅助包公共 worker 开销修复候选

关联 Issue #647。基于 main `13fe9defdcaae33ec2d25fe00aeacc8ca4d3ab53` 及已核双端九叶来源，只改变每端 `application.py` 和新增共享识别模块，不选择或安装候选。

原有辅助包快速分支只跳过业务处理器，外层仍执行两次活动在线计时和一次通知检查。候选只让当前合法辅助包跳过这些工作，继续调用原处理器鉴权和投递待发消息；活动周期、普通业务、换角、断线计时保持。真实业务 worker 增加 `clock_before_ms`、`domain_ms`、`clock_after_ms`、`after_reply_ms` 四段计时。

旧版在新回归中复现辅助包触发活动工作的失败。候选 online 11 个相关用例、LOCAL 24 个相关用例通过，均无跳过；含双账号真实 TLS 辅助包突发、外部撤权、角色归属、活动区间周期提交及最后关闭不丢失/不重复。首轮新夹具因 SQLite 连接未关闭而清理失败，修正连接生命周期后只重跑该用例；断言未放宽。

验证入口：`python -B tools/verify_shared_request_latency.py`；运行测试须先使用现有物化器创建隔离 runtime，再以该 runtime 的模块运行 `test_auxiliary_worker_activity`、`test_native_auxiliary_latency`、`test_current_latency_tls`，LOCAL 另含 `test_local_auxiliary_roles` 和 `test_server_latency_guards`。完整命令和脱敏运行结果保存在维护者 `G:/els/analysis/title-sacrifice-diagnosis-20261031-v1/`，原始玩家库及运行日志不随包。

历史请求的 6 秒具体热点尚未被旧日志证明；这是已证公共开销的修复及分段观测补齐，不能称线上延迟已恢复。未合并、未双端安装、未自然 GUI 核收；安装后需按新增分段耗时核对真实请求，并在仍有尖峰时继续处理对应慢段。由指定发布负责人选择性整合，保留实际父版与 LOCAL 差异。
