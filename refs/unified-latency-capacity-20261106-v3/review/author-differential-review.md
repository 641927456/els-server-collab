# ELS 并发与通知候选差分复核 — 2026-11-06

## 结论

自审范围为冻结 102 个覆盖文件之后新增的 10 个改动文件，目标为 combined-latency-v2 的 106 文件完整覆盖包。不是整个 1069 文件业务树的完整安全审计，也不是 GitHub 审批或发布许可。

| 项目 | 数量／结论 |
|---|---|
| 当前可复现的未修复安全问题 | 0 |
| 自审发现并修复的功能问题 | 1（P2） |
| 改动文件阅读 | 10 / 10 |
| 直接改动函数未找到相关验证 | 0（无行覆盖率统计） |
| 风险 | MEDIUM；涉及并发与奖励事务，按 HIGH 入口展开检查 |
| 建议 | CONDITIONAL：相关功能验证通过；线上延迟尚未合格，不能据此发布 |

目标清单 SHA256：`bad36d5cc793d8bbdf242c9995e45c6e133e8e3cacd10fa98926ff25fc7c5890`。旧候选 combined-latency-v1 与私有 launcher-preview-v3 已被替代，未上传线上候选，未安装或发布。修正版采用新的冻结清单，旧清单未回写。

## 改动

| 文件 | 新增行 | 删除行 | 入口风险 |
|---|---:|---:|---|
| storage/clock_writer.py | 28 | 4 | HIGH |
| domain/growth_guide_flow.py | 3 | 2 | HIGH |
| storage/title_levels.py | 3 | 2 | HIGH |
| storage/master_presets.py | 3 | 2 | HIGH |
| storage/online_2026_delivery.py | 10 | 5 | HIGH |
| domain/online_2026_display.py | 35 | 18 | MEDIUM |
| domain/online_2026_campaign.py | 16 | 11 | MEDIUM |
| application.py | 3 | 0 | HIGH |
| dungeon_workers.py | 18 | 1 | HIGH |
| storage/online_2026_progress.py | 3 | 2 | MEDIUM |

合计 +122/-47 行。逐文件前后 SHA、有效来源及统一差分见 [review-evidence.json](G:/els/analysis/town-dungeon-latency-20261105-v6/experiments/combined-latency-v2/review-evidence.json) 与 [security-diff.patch](G:/els/analysis/town-dungeon-latency-20261105-v6/experiments/combined-latency-v2/security-diff.patch)。基线优先采用当前冻结 candidate 文件，缺少的文件采用已固定线上父版，父清单 SHA 为 `4fe573786b8c4646b5292dde08ee0ed42e82a3e372a8f8729b5cb58bf78ce0f6`。

## 发现及修复

### P2，已修复：写事务复核转为未达标时，通知误用空的读取结果

旧候选 `domain/online_2026_campaign.py` 的 display 分支总调用 synchronize_view；实际写事务返回 not_ready 时没有 read view，且事务已经结束，会抛出 Caller read snapshot required。只读预检查为达标不等于实际发奖授权，原实现允许写事务重新得出未达标。

已用同一个真实原生登录角色和隔离 SQLite 库复现：预检查达到 1800 秒，在写事务获取前变更该自有测试库的历史区间，写事务重新判定未达标。旧候选报错；修正版只在存在当前只读 view 时复用，否则保留原实现的提交后独立读取。修正版事件与完整 SQL 和冻结原实现一致，奖励未发出。见 [online-notification-recheck-tests.json](G:/els/analysis/town-dungeon-latency-20261105-v6/online-notification-recheck-tests.json)。

这是对事务结果完整处理的功能修复。复现需要修改隔离存档，不能据此声称普通网络玩家能删除线上账本；没有构造虚假经济漏洞。修正后未发现可达的重复发奖、未提交 ACK 或跨存档写入路径。

## 验证与覆盖

| 改动入口 | 相关证据与边界 |
|---|---|
| ClockWriter 的非最终让路、错误隔离和最终提交 | 实际物理提交被事件阻塞时立即返回 BUSY，回调未执行；最终 stop 等待提交；原始双计时账本／游标恢复、后续区间补齐及物理提交失败回滚测试通过。修正版额外验证错误存档不打开、错误类型不被 BUSY 掩盖、异常不保留 actor traceback、关闭后拒绝。 |
| 三个冷写入入口使用共享 FIFO | 原生 SQL BEGIN 来源对照、成长指引／等级称号完整结果与 SQL、编码失败回滚；大师预设 6 种真实角色存档状态、触发器失败回滚、后续空槽选择及重开通过。 |
| 同一次通知的进度读取复用 | 空进度、900 秒、1800 秒、资格不足、重放、编码失败及重试、后续归属变化、真实 EXCLUSIVE 锁通过；负预览历史查询 2→1，正预览仍在写事务重新检查。修正版补齐上述写事务变负分支。 |
| 普通城镇移动减少共享锁 | 原处理器／作用域对照的世界锁进入次数 4→2；结果、广播字节、坐标和无效输入拒绝一致。队伍、竞速房间／队列／offer、交易、公会、照相区、挑战及其他包保留原路径；实际竞速等待消费者仍忽略移动。XYZ 阻塞写盘、业务读取屏障、board/progress 持久化后广播及退出清理通过。 |
| 时长覆盖索引替换 | 25 个 SQL 99 级自有角色、90000 个合成区间：原进度完全相同、原始行未改变；只保留一个二级索引，重复初始化结构一致；新库与定义校验失败的 DDL 保存点回滚通过。 |
| 组合实际运行 | v1 组合原生 Town25 15000 次移动及 DG20 五分钟 3300 次死亡／拾取、220 次循环，冷账本与 ACK 完全一致；v2 修正后的实际加载 106 文件及 DG20 885 次死亡／拾取、59 次循环通过。后者只是功能验证，不是线上容量凭证。v2 两名 LuCiel 原生组队／切换／死亡／过门／复活，打包解释器实际副本流程也通过。 |

原生协议自有探测不等于自然 GUI 实战。当前线上冻结 102 文件长测的 P99 曾达到 82 毫秒，超过 80 毫秒目标；新 106 文件修正版线上容量对照尚待执行。测试证据保存在本任务目录，不包含凭据或原始日志的共享附件。

## 影响范围

在 1069 个有效业务 Python 文件上统计下列静态引用。数量是限定表达式或导入的匹配位置，不冒充完整动态调用图；具体文件与行已保存。

| 入口／引用种类 | 静态位置数 |
|---|---:|
| ClockWriter.constructor | 1 |
| ClockWriter.commit | 1 |
| ClockWriter.lifecycle_refs | 1 |
| ordinary_town_move | 2 |
| worker_scope | 1 |
| read_preview | 2 |
| synchronize_view | 1 |
| master_presets.imports | 3 |
| title_levels.imports | 1 |
| growth_guide_flow.imports | 7 |
| OnlineTitleProgress.imports | 5 |

传输层绑定的 FriendsSession.handle 经自有 actor 作用域进入业务，ordinary_town_move 仅服务于普通城镇 22B。共享副本／队伍和经济写入的原始路径仍保留。ClockWriter 的生产调用为双计时事务提交器，BUSY 结果继续经过它现有的游标恢复逻辑；不影响 CoinWriter 或 DeathWriter 的最终持久提交确认。

## 访问边界与对抗检查

假设攻击者只有普通已认证客户端及其自己的报文；不能直接调用 Python 私有方法或提供服务器 SQLite 路径。验证了无效／非有限移动输入、已有竞速等待消费者、角色归属变化、错误存档绑定、重复计时／发奖、编码拒绝、部分与整体提交失败。

进入普通移动快分支前，原有账号启用、已释放连接、社交溢出与合作错误检查仍执行；LocalSession.handle 继续原解析、坐标保存及依赖失效，_after_local 继续在世界锁内广播／排邮箱。文件并未修改认证、MAC、序号或 CNG 算法。

进度 view 只由同一个只读事务产生并直接消费，没有跨请求授权缓存。正预览从不代替实际奖励事务中的 owner／period／policy／receipt 检查。普通计时遇忙的回调没有提前写入，两个游标在既有逻辑内恢复并补记；退出仍同步等待物理提交。奖励、拾取与死亡 ACK 没有改成异步成功。

## 历史、回滚与局限

只读核对的现有协作仓库 HEAD 为 `6b27a8a11e467e6172e4f9c2a8f7314a09a5ef1c`，工作区未修改。只有 online_2026_display 的有效基线 blob 与该 HEAD 完全一致，其移出渲染逻辑的 blame 为 `91fed547c0997bf98b3d7f74bb30b4ccbfad73d1`；其余 9 文件无法把当前发布覆盖版本诚实映射到该 Git HEAD，使用逐文件 SHA 固定比较，未借用不匹配的 blame 宣称历史无回归。

索引更新不改玩家行或发奖规则。回滚旧代码不会自动恢复数据库；旧查询没有 INDEXED BY 的名称绑定，旧初始化可以重新创建旧二级索引。双端候选仍为同一服务端／签名运行组件，私有配置与存档路径分开；原游戏 EXE/KOM 未改。

本次为作者自审，未委派代理，也不构成要求的 GitHub 人类审批。对直接改动和已复现路径信心较高，对真实高峰性能的结论仍取决于后续固定输入线上长测。完成相关构建核收与容量测试后再决定发布，不扩大为全项目重测或无关清单。

## 23:25 UTC：启动调度增量复核

combined-latency-v3 只在已审 v2 上更改 `els_server/__main__.py`。新增 `_normal_scheduling()` 仅由 `serve()` 启动调用一次，`psutil.Process()` 选中当前游戏进程，设置并读回 Windows Normal CPU32／I/O2。没有 PID、优先级或路径来自玩家报文；不修改管理进程，不增加线程／资源配额，不改变身份和经济事务。非 Windows 返回原流程；Windows 设置失败明确抛错，未吞掉。静态调用位置为1，实际统一入口的私有编译启动测试验证了 BelowNormal／Low 父进程下的32／2及重复启动复用、正常退出。该窄增量没有发现新的可复现安全问题，性能仍须线上测试确认。

## 23:56 UTC：疲劳凭据与坐标批量增量复核

combined-latency-v4 在 v3 上更改 normal_fatigue_flow 与 normal_fatigue。`_operation_digest`、`_replay` 是原 `_apply` 验证／凭据分支的机械提取，原物理写入分支未改。新的 `stage_replay` 只有 `_loaded_replay` 一个生产调用位置，并且只处理 BB。其连接来自既有 `snapshot_connection` 的 `mode=ro` URI；该 API 的只读保证不依赖 `PRAGMA query_only` 值。读取与生成响应保留同一个新鲜 SQL 快照，未增加跨请求资格缓存。B3 仍包含随机任务写入，明确保留原写入入口。

只要整个队伍有一个凭据缺失，就放弃所有只读结果，重新执行原来的全队写入事务；没有把已有成员的读结果和新成员的写结果拼在一起。原 actor、账号归属、生命周期、存档路径、关卡来源、NPC 输入及编码检查保留。其他已提交归属变更、编码拒绝和读取期间目标 NPC 改变均实际拒绝；缺失凭据的实际写入回滚、下一次仅扣一次、再次读取不重复扣除通过。原报文和完整 SQL 相等；另一个真实 SQLite writer 持锁时只读重放完成。双人 LuCiel 原生入场／死亡／过门／复活及连续690次死亡、690次拾取、46次过门已通过，未冒充自然 GUI 战斗。

combined-latency-v5 另外把 PositionWriter 已有位置专用批量上限由16扩大到64。没有增加线程、等待窗口、回调、经济事务或异步成功路径；100毫秒窗口以及场景、面板、进度、退出时的持久屏障保持原样。50个自有角色的真实阻塞 writer 测试中，原4次提交减少为1次，所有 SQL 行、revision 和已完成 Future 的结果一致。原生移动在 SQL 阻塞时可广播、后续移动不等旧提交、业务读取等待最新坐标、面板／进度先持久后广播、退出保存和缓冲退休均通过。

唯一同时变更的传输日志仅增加系统 errno／winerror 与 OpenSSL 固定 library／reason 字段，供调查30人短测的 SSLError；不记录报文或凭据，不更改异常处理、认证或发送路径。上述4文件增量尚无新的已复现安全问题；真实高峰能力仍未核定。私有5M QoS规则和校准只属于 QA 工具，没有加入服务端业务包或修改云控制台、公共服务配置。GitHub 人类审批与安装仍未完成。
