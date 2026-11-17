# 结算统计候选：独立只读审查

审查对象：`candidate` 相对 `releases/online/native-player-feedback-repairs-20261106-v1`。精确文件 SHA 在 `independent-review-identity.json`；这是非 Git 发布树比较，没有用不存在的 commit/blame 证明交付。审查中作者继续修改候选，本报告以该 SHA 清单为边界。

## 结论

现有候选的 9E 解析、伤害本人 UID 切片、C1 统计布局与既有原生证据一致。已发现的共享结果冻结问题已修正，并用独立 fixture 验证。随后作者自查发现 CD 的取值方向错误，独立原生证据确认此项；候选现已删除错误CD投影，保留原报告，未将未知跨观察者汇总规则猜填。结论为 **CONDITIONAL**：可以继续相关隔离验证，不能据此宣布自然客户端 Hook、局内实时 TAB 或完整原版结算已完成。

最终已只读核收作者自有原EXE上的实际加载、dispose和reload成功，组合pin未在该次安装中冲突。实际original9E调用为0；此结果证明安装生命周期，不证明自然BB/471、TAB或战斗已验收。9份自有private stores已清理，9源文件及manifest/patch归档与先前冻结SHA一致。

| 当前确定问题 | 数量 |
| --- | ---: |
| Critical / High 未修问题 | 0 |
| Medium 未修问题 | 0 |
| 本轮发现后已修正或撤销错误实现 | 6（含作者自查的两处组合pin冲突） |
| 重要未验证边界 | 原生 Hook 自然发送；局内 TAB 消费链；CD跨接收者归因；原版贡献/Rank/MVP |

审查指定源文件及随后必要关联文件，其中 transport 已恢复为父版本，实际 9 个业务/支持/兼容性profile文件发生变化，行数及精确版本以 SHA 清单为准。另读一层路由、worker、共享结算、来源回执及原生调用链。没有访问玩家库、附加进程、启动游戏或发布；没有编辑业务实现。

## 已修正的问题

1. **冻结后离场换角改变既有结果名单。** 初稿在复用已冻结 `room.dungeon_result_rows` 前，仍读取 `room.members` 中实时的 `m.account.uid` 并比较原 participants。`FriendsDungeons.detach` 保留原 room.members，而原 LocalSession 的角色选择会替换同 Session.account；余下队员重播 C1 会因此抛错。现 `seal()` 仅首次封存核名单；同 epoch 直接读既有 rows。作者相关测试已覆盖换 UID；独立 fixture 再核相同结果字节。

2. **socket 投影读取跨 worker 可变 Session。** 初稿在 transport.send 中首次构造 rows，不在 dungeon domain 内。现 socket 层已无改动，`Application._worker_call` 的 `invoke_scoped()` 在 domain 内执行业务、随后 finalize。封存早于共享 domain 释放，不依赖各连接邮箱送达时间。重要的是 finalize 位于 `capture_native_sources` 的回调内：现有 `SessionSources.sent()` 对整批 Event 用 `is` 验证，不能在 capture 返回后替换 C1 Event。现代码已保持这一顺序。

## 原生接线核对

**后续确定修正：CD 不能套用伤害的本人 report/本人 UID 切片。** 初稿 member_payload 使用 `own_report.cooldown.get(ownUID)`；8FE730:589-597仅在sourceUID非0且不等于本机UID时向本机actor1B5D0写该source键，因此此写法正常永远得0。当前已删除该错误投影，CD保持未完成。作者曾提出对各接收者报告反向按sourceUID合计；来源方向正确，但是否每份map只含该接收者的独有CD仍需额外证明：11BCD50→194EBD0以传入target的skillslot为对象，8FE730最终写全局本机actor，未见target==本机条件。若远端槽也维护有效remainingCD，观察者副本可能重复。此项不能仅凭统计保存在本机actor就判定可无条件跨report求和。

- **682D80 message layout**：独立反编译 `680B50` 直接读取 message+10 的 u32 event ID、+34 的 u16 kind；与 `C68F80` 的 stack message、event 202/kind9E 一致。当前 JS 使用 args[1]、+10/+34 正确。
- **原生生产与发送**：`1AB7AC0 → Game v358/1AB6EB0 → C509E0 → C68F80 → 682D80` 是 9E。BE 仅小整数/map 包，候选未再将其当作统计。Hook 在 BB/471 进入 682D80、原包序列化和发送队列之前递归发送 9E；busy 排除自身重入。静态调用顺序支持 9E 在原 BB/471 前进入发送路径。
- **序号不能误读**：C68F80 在建 message 时写 +5E/+62，682D80 将其赋给 payload stream 配置；独立 680B50 并不将它们序列化为 event 字段。没有证据将这对值认作 TCP 外层 sequence，也没有据此报告“注入导致帧序倒退”。实际 NativeInbox 严格要求连续外层 sequence；仍应由隔离发送验证覆盖。
- **字段布局**：C1 row397、header31、原单人总长516 与 DA5DA0/DA64C0 一致。本人总/Boss/Normal、扣除其他人加伤后的自身三段、加伤贡献、减伤、HP/MP/自身HP/自身MP和 i32 承伤均与独立字段记录一致。CD字段位置正确但取值方向错误，见上。没有把 DTO+D8 的恢复计数误投到承伤；承伤来自9E+2C/actor1B478。
- **不重复累加全队**：1C37A00/1C39F70 把各来源 UID 的统计写当前本机 actor map，一份报告可能已有全队值。候选从每个本人 report 仅取本人 UID，不相加观察者副本。原生 writer/reader 测试含第二 UID 的非零干扰值。
- **所属代次**：保存值按 reward_run_id/stage/part 绑定，切阶段/换 run 不再使用旧快照。入口验证活动阶段、已同步、当前 lease、事件身份和正 sequence；clear 后新 raw 不覆盖封存结果，已有同代快照时合法递增序号重发只确认。同 raw 重复保持幂等，低序不同 raw 拒绝。9E 协议自身无 run ID，因此这证明服务端当前接收状态绑定，不证明客户端任意旧字节能在无 token 情况下被识别。
- **PvP**：`statistics=False` 保持默认调用和8192大小界限，PVP1最大HP处理保留。dungeon 统计显式开关增加地图数据收集且上限沿用现 transport 1MiB。FriendsSession 先调用 PvP 路由；DungeonWorkers 的 isolated 条件还要求 dungeon accepts。JS 还要求 DungeonGame vtable41BFD28/mode2，不会仅凭kind9E切入PvP。

## 共享提交与投递

`FriendsDungeons.end_part` 等齐 r.ended 全员 BB 后才结算，因此普通成功路径的每人 9E 已先于其本人 BB 进入并处理。不是首人 BB 立刻冻结其余全零。

三个共享 writer 都在 `_worker_call` 返回到 finalize 前完成全员状态采用：普通 `pve_economy_flow.clear` 全员 `_adopt`；raid `raid_economy_flow.settle` 全员 `_ADOPT`；challenge `storage.group_settlement.settle` 核全员 clear_notified+receipt 后提交和投递。正常疲劳共享加载分支同在原 worker/domain 内串行执行各原处理器。全员已 clear 时 finalize 即使当前仅返回 BC、其他 C1 尚在 mailbox，也先封存 rows；后续 C1 只读相同 rows。未将缺 receipt 任意伪装成失败，仅显式 dungeon_failed 采用失败 row。

`independent-review-fixture.py/json` 独立验证：只返回 BC 时已封存两人结果；之后同连接另一人换 UID、换 run、清 receipt，剩余人的 C1 字节不变；全员显式失败的两行 C1 能构造。这是源代码 fixture，不是实际多连接 TLS 时序观测。

## 验证证据与边界

作者 `statistics-verification.json` 为6项通过，含原生 DA2F50 writer → Python parser → DA64C0 reader，以及超过PvP 8192界限的完整技能报告。独立审查没有为未变输入重复跑整组测试。独立 fixture 如上通过。自然GUI/natural battle/production mutation 都为 false。

已读作者最新 `transport-verification-latest.json` 的 `tls-d18d682ca3`：实际认证、角色选择、lease、dungeon workers、9F、mailbox C1 与native reader通过，run/clear明确由QA state fixture提供，native source failures两端均0；此证据覆盖服务端接线而非自然战斗。新输出已撤销错误CD（DTO160=0），并确认合法late9E只ACK而不替换封存统计。旧`tls-48fc0e9de1`不能再代表当前CD/late9E；没有为新客户端线程谓词重跑未改服务端。

后续作者已改善重试确认：同generation已经有before-clear snapshot时，合法的新递增sequence late9E仅ACK0且不替换snapshot/封存rows；旧序冲突仍拒绝。已读当前实现确认先处理旧序，再处理clear。现有原生证据不要求对这种合法重发返回2005。原1AB7AC0每次重新构造完整DTO，HP等非统计字段可能变化，因此“clear后whole raw必须相同”不能代表自然BB/471重试不变。该调整合理，仍保留无旧snapshot、不同代次、结构/lease非法的拒绝条件；后续针对性测试由作者核收。

下列事项没有被这些测试证明：

1. **Hook 原线程条件已补，原生执行仍待自然验证。** 追加修改向installer传入`()=>mainThread!==0&&Process.getCurrentThreadId()===mainThread`，与既有native_cache_sync.tick设置的同一变量闭包相连。匹配BB/471后、任何currentGame/actor/report NativeFunction调用之前检查该谓词，未创建线程来源或缓存Game指针。`verify_hook.cjs`的Frida fixture核非原线程不执行report；它不等于实际1AB7AC0执行。该原sender还修改engine80+198待9F容器及engine80+18F8对象+159，自然调用线程/ACK路径仍待验证。初始化失败闭包生命周期问题已按末节修正。
2. **自然 BB/471→9E→9F→BB/471 时序。** 静态顺序成立，但尚无本审查自己的真实发送/ACK或外层 sequence 观测。原生9F待答状态机和重复BB的自然行为不由payload codec回放代替。
3. **局内 TAB。** 已证明本机 actor 在真实伤害/辅助/恢复路径生产统计，也证明 C1 →3156C90→1046F20/2E055C0→37ABAF0→37AD010 为结算消费者。但没有找出局内实时 TAB 的按键入口、消费数据对象、刷新和是否另需同步包。DamageRecordArea 的唯一已核 xref3620A50属于训练 UI，不能拿来证明副本TAB。新增HOOK只补终端BB/471前的报告；不能仅凭C1结果已还原就宣称局内TAB正常。
4. **原版 Contribution/Rank/MVP。** 候选尚未还原相应计算。C1 DTO+174/+17C/+17D 的存在和显示已核，原版系数/阈值/CP归一化未核。现有 local_artifact_rules 的耗时预算评级不能替代现代贡献Rank；用户已明确继续原版，此项必须保持未完成，不可自填权重。

详细原生证据复用 `independent-findings.md`、`independent-rank-cd-counter.md`、独立 Ghidra bracket 产物及字段 SHA 清单。此报告不是发布/合并批准，也不将上述未验证项写成已通过。

## 追加定向复核：线程谓词与重装生命周期

只读`tools/dungeon_result_stats.py/.js`、`tools/native_cache_sync.py`及其JS主线程上下文，随后定向读完整`generated-native-source.js`的prepare/install/既有Hook组合顺序；复用作者7项hook fixture和Node语法检查结果，没有新广扫或重跑服务端。

词法作用域/初始化顺序正确：composer最终把调用放在同一native_cache_sync函数初始化成功末尾，位于`let ... mainThread=0 ...`声明和`groupWear=installGroupWear(api)`之后；闭包每次取该变量实时值，原tick先设置mainThread、后续异线程不能更换。显式`controller.dispose()`先active=false、detach自有hook并删除global singleton；之后重装采用新谓词，重复dispose也不会删除后来controller。现fixture已覆盖这种主动销毁重载。

**已修复 [P2]：cache中途初始化失败后重试仍引用旧mainThread。** 追加修改的初稿安装点在cache初始化中段，之后原有`Interceptor.attach`、emit、`installGroupWear`均位于同函数返回之前。既有`ready()`只有`installElsNativeCacheSync()`成功返回才给real赋值；后续初始化抛错时real保持null，下次会创建新cache词法作用域和mainThread。但stats已写globalThis.elsDungeonResultStats，下次installer幂等返回旧controller；旧predicate仍引用失败那次的mainThread（未进入tick，保持0）。因此新的cache.tick即使已确立主线程，stats仍一直拒绝匹配BB/471。

独立`independent-thread-closure-fixture.cjs/json`复用现Frida API fixture复现上述已被替代的中段安装顺序：第一次安装后模拟cache后续失败，第二次cache变量已就绪仍拒绝report；主动dispose再重装恢复。无游戏进程或服务器操作。作者随后把安装移到`groupWear=installGroupWear(api)`完成之后、`return api`之前；已读最终composer确认stats安装后仅return，cache先前步骤失败不会提前留下该singleton，消除了此生命周期问题。最终源SHA已更新。没有因这项客户端小改重跑服务端，也没有启动新的测试进程。

### 兼容性profile的必要接线

`tools/client_compatibility_profiles.json`相对父版仅有三个artifact pin变更：更新`tools/native_cache_sync.py`为`244780537a73f88bd40d97382def39d8338cacd965447bce273e0e80435e44a4`，新增`tools/dungeon_result_stats.py`为`3064a03e8fced86599795e9b8c90bc384dfa025509a0fd543ac1388881a842d1`，新增对应JS为`859f8a0644ce2b65f3c51750493514a8f796965e4f4c573cf62c296abf9c61ae`。三个SHA均与最终候选文件一致。原EXE/runtime/native_contract、catalog及资源证据未变，没有批准其他客户端版本，也没有放宽路径/哈希规则。原client_compatibility.py逐一resolve并校验所有artifact，因此必须更新既有composer pin并纳入两个新依赖。

作者报告原生加载预检v2在启动前因隔离catalog符号链接超出runtime路径边界被拒、已物化自有路径；v3未取得别人的测试锁而停止。本审查没有启动进程，也不把这些启动前拒绝写成原生Hook/自然GUI通过。现有Frida mock和生成完整JS的Node语法检查仅支持脚本结构与拒绝条件，完整客户端自然路径边界继续保留。

### 最终组合顺序与原指令pin

作者随后从实际组合源码发现两处合法Hook会改写旧pin：既有PvP installer在1AB7AC0入口attach；generic trace在682D80入口attach。最终代码将纯prepare与安装拆开，已定向核对以下顺序（行号对应下述生成源码SHA）：

- `generated-native-source.js:915`在原native-cache identity guard之后先调用`prepareElsDungeonResultStats()`，`:917`才调用`installElsPvpHpSource()`；后者在`:396`挂1AB7AC0。因此原sender prologue在prepare时尚未被该合法Hook改写。
- prepare只核固定pin、构造NativeFunction并缓存install工厂，不调用currentGame/actorOf/report；工厂缓存只捕获module及函数包装，不保存Game/actor/线程谓词。cache后续初始化失败重试时复用已经核过的工厂，不重新拿被PvP改写的1AB7AC0入口比较原字节；也不留下失败cache的mainThread闭包。
- `:1089`完成groupWear安装，`:1090`才安装stats并传本次cache的mainThread谓词，随后return api。显式dispose/reinstall会给同一prepared工厂传入新谓词。
- 既有generic trace在`:1311/:1481`对682D80入口attach，且可能早于lazy cache ready；故该site改为核同函数+20h的固定body `682DA0` 16字节，Hook仍挂原682D80。其余159670/8571D0/1AB7AC0/1AB6EB0的pin保留。完整组合源码没有682DA0 body写入，也没有对另三处getter/producer的attach/replace；没有发现剩余的已知pin/Hook顺序冲突。
- PvP的1AB7AC0回调仅对vtable4183DD0捕获；本次DungeonGame为41BFD28，故不会给这份dungeon9E附加PVP1。generic682D80日志回调可能先记原BB再记递归9E；这不是实际wire顺序证据。原BB本体仍待回调返回，递归9E本体先执行，后续自然验证应读真实wire/服务接收序。

仍使用同一固定EXE SHA与runtime SHA。682DA0的body pin不是多版本接受或未知不匹配兜底；实际Frida对prologue改写的范围及自然执行仍未由本审查进程观测，现结论是组合源码层没有剩余已知冲突。已读作者7项Frida fixture结果，包括prepare无Hook、随后模拟PvP改1AB7AC0后仍能安装；未重复运行旧测试或启动新的测试进程。

最终生成源码SHA为`1110481615d5294090d7d8e56356733f224e9cc9f8a2dc4bb3daf8973f44a3dd`，profile SHA为`75cc36b8cd1991e21368b23c7788b4796d0e9552d6fc8a4cc118810f30fe5054`；全部文件及验证产物已重新固定在`independent-review-identity.json`。局内TAB、CD跨报告归因、原版Contribution/Rank/MVP与自然客户端发送的未完成边界不因本次组合修正而改变。

## 最终实际加载结果核收

仅只读`native-verification.json`、`native-load-v6/isolation-receipt.json`、该次trace的必要事件及cleanup小receipt，未重跑测试或启动进程。实际trace路径为`native-load-v6/native-log/20261106-223320/trace.jsonl`，SHA `19d7a4debc978d3608d019d42384c3b476df98e1b94e14c021a8e01e8552f760`与receipt一致；JSON行均可解析，没有script `type:error`消息。先出现既有PvP/cache就绪，再出现两次`dungeon_result_stats_ready`；loaded/reload各一次，reload为removed=true/new_controller=true，reports均0。实际原EXE及该组合的安装/销毁/重装成功，更新了先前仅静态与mock验证的安装边界；没有扩大为原sender自然调用已成功。

所有权receipt中的client PID/create-time与出生Job成员一致，记载新建挂起原EXE并在同自有Job内运行、未附加已有进程、物理输入0；结束后Job为空、服务closed、自有锁释放、桌面未切换且私有桌面句柄已关，原EXE SHA保持。选角为自有QA原生回调，不属于自然GUI验收。独立审查按这些小receipt核收结果，没有重新操作或查询运行中的游戏。

`owned-store-cleanup.json`的9个自有private目录均已不存在，没有访问玩家库。`candidate-source.zip`内为9份源文件加`candidate-manifest.json`和`candidate.patch`；9份源码逐项匹配manifest、当前candidate及本审查之前冻结的SHA，嵌入manifest字节相同、patch SHA匹配manifest。归档SHA为`f413ccff4d10b3276de58e9d705f5df71576c2a9632f190df545023ab1c96aad`。归档和manifest仍明确标记候选未完整、未合并/签名/发布。

本次核收摘要保存为`independent-native-acceptance.json`。actual_report_calls=0、natural_BB_471=false、natural_battle=false；实时TAB、CD归因和原版Contribution/Rank/MVP边界保持原结论，至此收口。
