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

## 00:49 UTC：GM 列表批量读取增量复核

combined-latency-v6 只增加 gm_runtime.py 的两个读取助手及 Runtime.players 调用调整；生产调用为已认证 GM RPC 的 status 分支1处。现有身份、角色归属、生命周期检查继续复用 public_identity_views，不缓存玩家资格或余额。余额只批量读取已初始化且保持原实现的 LocalAccount／RewardState，沿既有 snapshot_connection 新鲜只读事务读取，保留原 validate_balances 全字段检查。冷状态、实例覆盖和非标准余额表仍执行原方法；SQL参数只用占位符。原 GM 写入、审计、认证、经济提交和 ACK 路径没有改动。

实际25个原生在线角色的完整 GM 行与旧实现一致，整库 SQL 没有因列表读取变化；另一个 writer 更新角色级别和 ED 后立刻显示新值。账号归属变化、余额缺失／非法值保留原拒绝；冷初始化、覆盖的读取／初始化方法及余额 view 的原读取分支已验证。实际 worker 诊断中位数24.279→0.953毫秒；这不是整服容量承诺。107个实际模块加载来源和 GIL 状态已核。此窄增量尚无已复现的安全问题，作者自审不构成 GitHub 人类审批。

## 01:51 UTC：共享身份、单人切换与被动读取增量复核

combined-v7 的 Characters 把原批量身份查询提为同事务助手，并由 public_custom_group 复用；保留原 owner、账号、生命周期与非标准 schema／覆盖实现分支。没有跨请求身份缓存。25 个原生角色的公开视图及编码报文、完整 SQL 一致，SELECT79→5；LuCiel 状态、重复／失效／外属角色及称号、定制过期和返回值独立性均通过。延迟中位数仅4.594→4.232毫秒，不据此声称解决整体尾延迟。

combined-v8 的 solo_transition 只改变普通 routes 目录下原单人382／91／67的调度，调用位置为 candidate、worker_scope 与 Application 分派。精确原会话／原事件类型、原阶段、非队伍和非挑战／特殊房间限制保留；原处理器的资格、票券、疲劳、经济和报文检查未移除。路由选择之后仍进入原账号／队伍作用域，worker_scope 再读取当前归属；真正共享目标保留世界锁和邮箱锁。复用既有准备槽2，不加线程。原共享请求及处理后世界段保留。控制实验阻塞原库存读取时，父版阻塞其他城镇22B，候选允许其正常中继；原生双LuCiel组队及连续三个不同运行代次、45死亡／45拾取／三次回城均通过。

titles.state 新鲜只读路径保留原快照结果；仅检测到已有非零失效装备时进入原写事务，再读并条件清除，完成持久提交后返回。不能用只读预览提前承诺经济写入。无装备、零装备、有效和失效称号、未知归属、完整 SQL 与原返回值及真实竞争写锁均验证。

GuildExpedition 空成员／空远征只读路径保持原 guard、60秒／周边界时钟及投影；正远征继续新鲜写事务、原授权与奖励逻辑，并进入已有 writer FIFO。原生远征12阶段、奖励／回放、失败回滚及跨周归档通过。GuildServices 只有普通 Town／DG 路径改为新鲜只读连接；实际公会基地仍保留原访问资格写入。实际504访问、原3A3、离开基地回城及有效个人效果读取在真实竞争写锁下均通过。

此验证发现并修复此前私有周期优化漏掉 guild_agit_ready 的缺陷：原候选只过滤出城镇和已同步副本，遗漏基地周期效果通知。现仅补回该原有效阶段，Town／DG 条件不变。失败证据保留。旧大场景的周计时精确事件数量断言在父v7与候选都失败，未声称该大场景通过；本次直接相关效果路径已独立原生验证。最初未采纳的称号原型误用BASE导致缺少已保留批量助手，已由原生测试发现并纠正，最终版本其余顶层AST逐项一致。上述为作者自审，未发现未处理的新权限／经济绕过；真实容量和安装仍待完成。

## 03:33 UTC：后台检查点与 Windows 文件身份读取复核

C9 增加一个应用持有的 WAL 检查点线程，连接以 mode=rw 打开现有存档，仅执行 PASSIVE；开监听前完成首次检查点。原 FULL 提交、1000 页自动阈值、经济结果在物理提交之后才确认的路径保留。线程不持有角色／世界队列，异常通过启动 Future、请求入口及正常关闭显式传播；关闭在写线程退休之后 join。实际旧读事务、前台写入、下一次检查点、缺文件和第二轮 I/O 失败用例通过。100ms 间隔未改善线上结果，当前保持经测试的250ms，不隐藏失败。单线程连接仍绑定配置中的存档；没有声称它逐次重新打开文件，也没有自动恢复数据。

C11 仅将普通单人 mode1 的原7D4预备读取纳入既有准备通道，原处理器及其共享世界段保持。原始疲劳读取阻塞时，另一原生城镇角色可以移动；双LuCiel原生组队、门、死亡和复活流程通过。模式、队伍、特殊图的类别限制没有扩宽。

C13 只更改 _ReadScope.locate 的 Windows 文件元数据来源。每次调用均以 FILE_READ_ATTRIBUTES／OPEN_EXISTING 打开一个自有共享句柄，跟随当前重解析点，从同一句柄取完整内核路径和卷号／128位文件ID，finally 关闭；不缓存文件ID、玩家资格或读取结果。仅复用原先已确认的路径前缀转换；冷转换不一致显式失败。现有角色归属、生命周期、SQL、data_version前后检查、返回值复制及经济 checked_paths 入口／出口检查的 AST 保持。非Windows原路径仍保留。

120组生成路径覆盖绝对／相对／父路径／缺文件／中文空格／显式前缀；文件替换、相同硬链接的父目录改向、目录移动后同ID、符号链接重定向、长路径以及内核失败关闭句柄均通过。卷号与完整文件ID同时在本机和线上自有只读文件中与 Python stat 一致；1000次调用前后句柄数一致。真实WAL独立writer可见、只读拒写、放弃事务回滚、并发线程连接独立和关闭检查通过。Python3.14t实际副本三次运行45死亡／拾取／回城，以及双LuCiel组队过门、死亡成员加载和复活通过。此窄增量未发现新的已复现安全缺陷；当前正式20人混合延迟仍在测试，未据此承诺容量。作者复核不代替 GitHub 精确 head 人类批准。

## 04:33 UTC: retained C14 scope and actual signed package

The native single-handle path/ID experiment C13 is excluded: short ONLINE latency did not improve. Current read_scope.py is exact C11. C14 changes only the existing app-owned PASSIVE checkpointer thread to Windows THREAD_MODE_BACKGROUND_BEGIN, with checked native return values and an actual -4 priority readback. Foreground threads and process remain unchanged; FULL economic commits, WAL automatic threshold1000, interval250ms, owner/receipt rules and before-ACK commit order are retained. No new thread, schema, gameplay or player snapshot cache is introduced. Unit held-reader/foreground-write/next-pass/failure/join proofs and actual packaged native transitions pass. No new actionable security finding in this increment; this is author review, not human Git-head approval.

Actual C14 signed v12 launcher V82 build EXE 1caae3815d7172b34e2e57f6ae74ce0ff22cb25cedb2de11f0a6d9ea54d6eab2 selects payload d3a1a9277ca23c808b61d7a67bf63dd74906fe180ab669c8beb89e95da474cf7. All2786 signed member hashes, current V81cache upgrade691files/repeat0, actual endpoint CPU32/IO2, reuse and normal stop pass. It is private and uninstalled. Native ONLINE15Town5DG physical-path short passed economic/SQL/ACK/source/cleanup and WAN steady/burst; one B3 waiting P99=19ms fails15ms, so long-capacity qualification remains pending. Earlier direct-WAN labels excluded SSH tunneling but used the OS TUN route; no claim that old proxy-path failures are server-only. Current physical route proof is socket-local IF8, with no system route/proxy/firewall changes.

## 05:02 UTC: C15 guarded readonly stage receipt reuse

C15 changes only normal_fatigue_flow.py and normal_fatigue.py. The BB reader already opens one fresh readonly SQL transaction and runs the complete current room/source/actor/writer guard before and after receipt reads and native/mailbox encoding. Its inner wrapper redundantly repeated those same writer/actor queries three times. C15 removes the unused wrapper and reuses the existing receipt helper between the unchanged outer guards. The private receipt helper permits no callback only for that readonly caller; _apply still invokes its original callback before reaching the helper and retains the after-encoding callback on its early replay path. B3 and missing-receipt paths retain the original durable writer. No economic transaction, FULL/WAL setting, ownership source, native packet or commit-before-ACK rule changes.

Actual C14 native oracle comparisons preserve exact Events and full SQL; held real WAL writer does not block the readonly replay. Encoding rejection leaves SQL and actor adoption unchanged, target NPC mutation is rejected by the final full guard, foreign owner is rejected, missing receipt uses the original writer with rollback/one success/no second debit, native BB completes. Actual two-LuCiel party admission, AD, dead-member door and peer HP sync pass. All110 current import origins and GILfalse pass. The actual ONLINE20mixed diagnostic retained exact1650AD+ED/110returns and finances/ACK/coordinates/accounting/cleanup; glass P95/P99=74/89ms vs prior88/101ms, with network variation explicitly separate. Death64/81ms still fails P9560; no long capacity claim. This is author review, not exact-head human approval.

The expiry-reader optional item-memo tracking trial is excluded: 800 redundant bookkeeping PRAGMAs became0 but local P95 worsened. C15 read_scope.py remains exact C14/C11; all original file/path/generation guards stay unchanged. No data cache or new player authorization result is adopted. Current signed v13 package preparation binds C15; private and uninstalled pending actual build/selection/runtime tests and capacity qualification.

## 05:24 UTC: C16 reuses the same verified canonical save path

reset_authority keeps its complete original authority-check AST, including checked_paths entry/end checks of path and file identity, current owner/lease, live registry, App/root graph and UUID. It now returns its already validated canonical game-save Path after the checking context completes. All25 existing call sites ignore its old return value. Only normal_fatigue_flow._binding consumes the new result, removing the immediate duplicate resolve of account.store.path; its separate reward-store binding and every before/after SQL/actor check remain. No cross-call/player-state cache, TTL or weakened file/generation guard is added. Actual old-C15 Events/full-SQL comparison, missing-receipt durable path and rollback/replay, encoding rejection, source mutation, committed foreign owner, held WAL writer and actual two-LuCiel party AD/dead-member-door/HP synchronization pass. All111 concrete import origins and GILfalse pass. Parent builtin file normalization is explicitly text/AST-equivalent (LF versus CRLF), with the actual full-parent SHA recorded; no fabricated original byte hash.

Actual ONLINE C16 balanced18 short (9Town+9persistentDG) completes1485AD+ED/99doors+normalreturns/15750moves125853relays, ledger/receivedACK/finalSQL/accounting/source/cleanup all exact. Server death55/85ms, pickup23/43ms, glass67/90ms, B394/107ms, Town14/36ms, allcriticalwaiting targets pass. WAN96/124ms, steady96/127ms, burst96/117ms pass. All400server-side TCP closures accumulated:18356retransmittedbytes,0timeout episodes; per-connection detail is bounded but totals complete. The prior C15 balanced18 short failed glass85/100 and WAN107/848, and had an incomplete256-detail TCP diagnostic; those failed results remain immutable. Network variability is not attributed solely to this source change. C16 still needs higher stairs and hour qualification; current20short is underway. Author review does not replace exact-head human approval.
