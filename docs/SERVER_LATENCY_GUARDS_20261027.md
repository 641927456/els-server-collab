# 服务端辅助请求减负和分段遥测

Issue #556，父版为 #555 的精确 Clock 双端引擎。范围为线上 6 叶、LOCAL 7 叶，只有 LOCAL 的原 `LocalSession.handle` 增加已绑定本地会话的 7D0 快路。LOCAL 包中的 FriendsSession 复用已交付线上守卫，保留身份禁用、单账号租约、原始报文形状及 mailbox 排空。

本地守卫要求 Application 创建的活会话、当前 LOCAL Application/account/store UID、一名有效 game 会话、正确阶段及精确九字节 DX11 辅助封套。释放、换 actor、重复游戏连接、加载阶段及任一报文形状差异都回原路径。独立周期的到期/任务/同步出口保留，Application 活动时钟照常观察。没有客户端或经济规则变化。

`Accounts.enabled` 复用同线程只读 autocommit SQLite 连接，每次 SELECT 当前已提交值，不缓存许可结果；外部禁用立即生效。文件身份变化重开，跨线程调用使用独立短连接，关闭在原串行 worker 排队完成。写入、事务、超时和单 worker 模型保持。

每次 Application 调用记录 queue/handler、角色投影加载/复用与 enabled 查询耗时，固定四类、各最近 256 条样本及累计计数/错误/最大值。每分钟在活动连接中输出摘要。transport 对普通请求、慢辅助请求及每 64 个辅助请求记录连接锁等待、队列/业务、投影、编码和 socket drain 耗时。它们是服务端时间，不是客户端 RTT；投影耗时包含投影函数，不能当作全部 SQL 时间。失败由 Application 错误计数及原异常日志记录，发送失败仍有已执行部分耗时。

运行日志移到有界 4096 条后台队列，正常网络路径不写文件/stdout。满队列只丢四类低价值遥测并输出按类丢弃计数；错误及其他运行事件保留原同步 fallback。极端磁盘阻塞下关键错误仍可能等待日志写入，不能宣称所有 I/O 阻塞风险消失。关闭排空并等待日志线程，兼容原双重 close。

验证入口：

```powershell
python -B tools/verify_server_latency_guards.py
python -B tools/materialize_formal_runtime.py --manifest channels/server-latency-guards-20261027-v1.json --channel local --output G:/work/els-latency-local
```

守卫、外部撤权、只读连接、跨线程、角色投影、排队分离、异常、取消中已开始 SQL 的提交、关闭排空及日志过载均有定向回归。精确叶变更之外的全部父文件保持。自然界面、真实客户端往返及多人实战需在最终部署版本上另验；本源码候选自身不代表安装完成。

后续架构顺序：先用这些数据识别瓶颈，再将静态/只读投影分出业务串行队列；保持事务命令与会话状态的单写者。周期调度可按 deadline 合并及按地图/房间管理，但须先覆盖移动、组队、到期和断线顺序。业务 dispatcher 拆分应随独立场景测试逐步推进。当前不扩大 worker 数或批量重写上千行 `LocalSession`。
