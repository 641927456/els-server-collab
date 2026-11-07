# v2 最小 Hook 最终独立审查

**固定 v2 候选的最小 Hook 独立审查通过，当前审查范围内无剩余阻断。** 静态接入、既有宿主及本次自有原游戏 Town/ED 商城证据一致。该结论是项目“客户端支持”要求的独立技术审查，**不是人类 Git 审批、精确 head 绕过许可或发布授权，也不表示已经签名安装。** 本轮仅读候选、组合、QA 源码与原始私有回执，不运行测试或改候选。810 锁核心及异常/LastError/失败等待审查复用，不重跑。

## 固定输入

| 对象 | SHA256 |
| --- | --- |
| tools/native_send_serialization.js | 283de2a4d2dfbdfe0da7db3b7af6cbf3d4b636d12bd6367f5c74eb9d57790a48 |
| tools/native_send_serialization.py | 4900d883e6a7a5ab79324cfcf37462c5c38dba1c2e052e3e6f0bf44eaf4f2eb7 |
| tools/probe_updated_client.py | ded6a3348860139b56a4b6faa976b4179d9edb6399a373ef6b229724052cc831 |
| tools/client_compatibility_profiles.json | 63c9a5d0aba198659fc3999ee433aac3040c3142197be51673e78cb4d815626b |
| repair-v11/composed-native-login.js | a6a6de77af46dc212e500f48e7d8aedf26494ca1a4cdb9db129a2c22aa45c971 |
| 已审原型完整文件 | 810e14c9eb289714da28d76e2bc5b7d798e44f2d8057a60c660ac29354fc0512 |

读回与 native-composition.json、profile 记录一致。按函数起止文本比较，候选内 `installElsNativeCryptoLock` 函数体与 810 原型完全相同，仅文件顶注释变化。V106 raid 父输入仍为已审 `2fb90926…`，其余未变部分复用前审。

## 安装、flags 与注册

prepare 外层先检查已有 controller，再做原生 pins；因此同一实例在 crypto entry 已被合法 fast patch 后重复调用，不会拿原 entry pin 再拒绝自己。返回 factory 内再次检查 controller，避免之前取得的 factory 被后续重复调用。失败的 crypto 尝试由原 lifetime guard 阻止重装，成功 controller 复用同一 CS/TLS/CModule。

helper 验固定 EXE 与 runtime SHA，并新增原 cleanup entry pin。最终 outer compose 在主启动 guard 成功、clearInterval 后立即安装 crypto/dispatcher，早于 Challenge/Wear/cache/raid/result 等初始化。独立 Noah timer 已有 `noahVerifiedSenderReady` 门控，避免共享 API 尚未建立就注册；它不依赖已被修改的 sender entry 重新验 pin。

common sender 的旧 C listener 已删除，只留一个共享 JS dispatcher；30D0660 也只有一个。两处 native fast replacements 是独立 crypto/destructor 地址，不在 sender 叠加监听器。主 sender 四处与 artifact 一处变成逻辑注册；主 frame 两个互斥站点、artifact 一处及 shop 两处动态站点也变成逻辑注册。不能把 frame 五处静态站点同时相加。dispatcher 每次保存快照、给各 handler 独立 Proxy state，native getter receiver/errno/lastError 转发不变；entry 前与 leave 前都检查 active。

shop 的 bridge + preview + quantities 仍完整、原顺序位于同一函数闭包，ebM/ebOwnedUi、NativeCallbacks/trampolines、计时器与 global 保活没有拆散。按 shop_test 和 item_test 分别替换两个布尔占位，只在主 startup 成功末尾安装一次；probe 不再独立 create_script 装 shop/artifact，原 bridge-ready 报告字段保留。shop 的动态 `.detach()` 变成逻辑幂等注销，当前 onLeave 自注销后其余本体仍继续，新 observer 从后续 frame snapshot 开始；取消尚未进入的 observer 会被跳过。

这保持原商城 NativeFunction 开关、catalogue 身份/generation、native-ready、超时/恢复、preview/quantity 计算，不新增 OS 输入、购买或经济重放。异常仍走原 Script error channel，receive_native_login 将其作为实际启动失败，不吞成总成功。

## 新入口宿主证据

`original-cleanup-entry-host.json` 与源码表明是原 constructor、真实 19 字节 `3B7D620..633`、原尾链及同 RIP 相对布局，使用 810 核心真实 replaceFast 返回。空 inline-string 路径 len=0/cap=15、锁与统计零。它仅验证原短入口重定位和空串正常尾链，不证明 allocator/free 分支或原游戏加载。先前“13 字节”已更正，TDZ/变量遮蔽夹具失败保留，不把失败归给 crypto 机制。

## 自有 QA 读回与待验项

owned_native_worker 只在两个真实物理 observer 构造点加 note，其余 QA 全通过共享逻辑 API。私有导出调用原 `ebScheduleToggle`，snapshot 只读 native open/ready 与当前 generation 的 initialized；不会直接写 ready 位。每 handler 的 this.state 经 Proxy 隔离。原生 open→ready→延迟 close 仍由 frame 驱动，不购买、不发 OS 输入。测试改动取消“sender entry 必已持锁”的旧断言是必要的：新锁到 crypto 才获取；改为核 encrypt/cleanup 及 active/failed 才对应新职责。

新 prepare 脚本检查一次原游戏的开关完成、sender 配对、crypto 统计、field 配对、物理两个 JS 地址、现有组件 ready、同一实例重复 factory，并按原自有过程退出后 detach。本次 `20261108-042432` 结果及其原始私有证据已在下节核对。

静态阶段提出的动态注销核收已由同一运行关闭后样本解决：prepare 现明确断言最终 closed 且 logical field=3；原始 trace 中 peak 为 4，关闭后的 57 个样本全部为 baseline 3。没有为此重新跑成功输入。

## 本次实际原游戏与 dispatcher 核收

候选五个文件及组合 SHA 再次读回与上表一致。`owned-native.json` SHA256 为 `33b8c3a91508e6a06ff3ba21f5292bed3d2de025d1855b8557f20d08cf12585b`。本独审直接读取其对应 trace、probe 与私有服务端事件，仅在这里保留脱敏结论，不复制原日志、账号、原报文、进程/线程标识或私有服务数据：

- 自有隔离认证服务确在 town_ready；原客户端加载本次组合，32 秒正常场景观察。sender 285 enter/285 leave/285 leave-only；crypto 290/cleanup 290、active/failed/CS 递归零；field 1918/1918。sender 与 crypto 计数职责不同，NativeFunction 路径可不触发普通 sender observer，不强行要求两者相等。
- crypto wrapper 实际记录 22 个调用点函数表，同一 Script 重复 factory 返回同一实例。物理 JS 地址只有 sender 与 30D0660 各一处；逻辑 sender 为五个业务加两个 QA。
- 原 trace 顺序包含 catalogue 应用、home 初始化、native UI-ready、QA 原生 open/ready 核实、原生 close 完成及 closed 核实。临时 field logical peak4→闭店3，关闭后 57 个样本一致，最后样本保持闭店、配对与锁零。原 artifact/raid/result/bridge/quantity 组件就绪。
- Frida Script errors 为零；协议类 protocol_error/worker_error/notification_error 为零。最终服务端尾部另有两条 bridge ConnectionResetError，随后 connection_finished；记录为结束阶段传输事件，不宣传“所有传输错误为零”，本次没有据此认定协议或新 Hook 业务失败。
- probe 的 EXE 前后 SHA 均为 `6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709`，自有进程已退出且当前 PID 不在。原游戏 EXE/KOM 未修改；没有控制其他玩家进程、写玩家库或操作正式渠道。

`shared-dispatcher-host.json` SHA256 `90d66af9e5a4346fce4291859368178a7dfb90c1a494384ceb9f1a6572f68723` 绑定当前 JS `283de2…`。读回夹具明确复用实际 dispatcher、stub 掉已独立核过的 crypto，不冒充再测 crypto。真实 Frida 下主/artifact/result 与 field 三类 handler 各四次，独立 this/native getter 转发正确；late 下一次才进入、取消未进入 handler 为零、shop self-detach 仅一对且收回三 logical fields，remaining scopes=0，预期逻辑错误确由原 error channel 报出。

## 失败保留与未验边界

Town 早期 `041723` 仍是失败：首个合格 frame 即发 toggle，没有 catalogue action/80D，原 toggle 返回后 native UI/catalogue timeout；早期未采样 availability 位，不能说该位当时已经实证为零。“早于 availability 的 QA 时序前提”是结合调用时机与后续差异作出的推断。两次都是 town_ready；后续仅 QA 等首个 owned field 两秒再调用，生产源码/compose 未改。成功运行 open snapshot 实证 selector=1、availability=1、entryState=0，再走完整 native 结果。另存的 dungeon-fixture 失败也未删除或泛称通过。

通过范围是固定 EXE/runtime、Frida 17.23.3、当前依赖/组合及自有 Town 商城正常开关、相关宿主并发/异常/生命周期输入。没有自然复现历史那十次重复序号的原报文，不把它们全部直接归因此设计；没有定位某次实机 JIC 覆盖的确切地址/指令。宿主通过不等于完整自然多人战斗/团本结算，原入口 host 的空串成功不等于已跑原 allocator/free 分支。任意取号之后的原生体内递归发包顺序、硬件 SEH、热卸载及所有 Windows API 故障仍不在本次资格声明中。

此前 704 包、V106249/249、新 240 包/247异常宿主与本次 Town 回执分别保留输入边界。没有新增无关检查。源码合并、签名安装、实际双端交付和真实 head 审批由主任务按既有流程处理，不能消费任何旧许可；已完成服务端交付不重开。
