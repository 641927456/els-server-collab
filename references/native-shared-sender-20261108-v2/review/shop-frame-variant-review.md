# ED 商城动态帧监听同类审查

**已确认遗漏与缺陷：此前只核启动时主脚本与 artifact 的两个 30D0660 listener，没有覆盖商城操作时的动态注册，不能把“2”当作全程上限。** `local_ed_shop_bridge.js` 的 ebQueue 和 ebScheduleToggle 会在正式商城路径临时 attach 同址，已有两处之上至少再加一个，触发固定版本两槽缺陷。旧 PR951 head 的 CI 通过不覆盖此新输入；按主任务当前记录，它未获新许可、未合并或发布。本轮只读，不改候选、运行测试、启动进程或操作生产。

## 注册与运行条件

ebScheduleToggle 先调用 ebStopFrame/ebStopToggle；其帧回调先解除自身 toggle hook，再执行原生 toggle，随后 ebQueue 注册等待 UI/catalogue 的 frame hook。通常是两个动态站点切换，不能把两处静态代码简单加成同时两个；但任一动态 hook 活跃时，主 town-frame 1 + artifact 1 + shop 至少 1 已达 3。

正式 COMMON_FLAGS 启用 shop_test 与 item_test，因此商城 bridge 会在 startup 就绪后装入独立 Script；动态 frame hook 则到商城开关/初始化时才激活。lightweight-play 不禁用该独立商城加载。物理监听器数不能只在启动就绪时采样。

## 其他独立启动脚本的四地址筛查

已以四个十六进制地址及相应十进制值搜索 candidate/tools 的 JS/Python，再沿 probe_updated_client 的实际加载分支区分：

| 地址或来源 | 正式入口结论 |
| --- | --- |
| 680B50 | group-wear 与 raid 各 1，未发现启用的独立启动脚本再加第三处 |
| 1AB7AC0 | PvP 与 result-stats 各 1，未发现启用的独立启动脚本再加第三处 |
| C231C0 | dungeon/gate/population 均 true，互斥后为 2，不能将三个静态站点全相加 |
| 30D0660 | 主分支与 artifact 启动时 2；确认商城触发时至少 3 |
| fatal / initial-resource / resource-dialog 脚本 | 未发现四目标 attach |
| prepared index/digest/config/stack/shortcut 与 hit-count | 四目标搜索及加载链未见新增 attach；hit-count 使用其他地址 |
| 商城 preview / quantities | 改的是其他地址，没有额外四目标 hook；但必须作为完整商城包一起迁移 |
| startup_inventory | Python 的 a.lightweight_play=True，正式入口不启用；worker 改 JS 常量不改变此 Python 条件 |
| 可选 startup_observer / run-local extension | COMMON_FLAGS 不启用或需要显式外部文件，不属于本次正式自动启动闭集，不能据本报告为任意外部脚本担保 |

本结论覆盖既有已知启动源码与给定参数，没有把 pin 表、NativeFunction 调用或未执行分支误算成物理监听器。

搜索校准先匹配 `Interceptor.attach(ebM.base.add(0x30d0660),`，命中 bridge 两个已知动态站点；再按四地址扩大到整个候选 release 树的 JS/Python，而非仅商城模块。命中包含 pin 表、原生调用、compose 文本及互斥分支，逐一按加载链扣除，不能把静态行数当活跃监听器总数。扩大过程未出现其他目录中的四目标调用；后续读到开发中的共享 frame helper 不作为已冻结 v2 的资格证据。

本项严重度 **P1**、源码/正式入口可达性置信度高：用户正常开 ED 商城可触发固定 Gum 两槽之外的第三个 listener；历史具体 JIC 覆盖指令及某次玩家闪退的直接因果仍未证。其余三址当前不是新增 P1，属于已核的两处容量边界；可选扩展不在闭集则保留信息级边界。

## 拟议共享帧方案审查

将 30D0660 收拢为一个 JS 物理 dispatcher，并保留 sender 的 C+JS 两个，是针对容量根因的合理最小方向，不需要全局修改 Interceptor.attach。需转换两处互斥主 frame 站点、artifact 一处、shop 两个动态站点；所有逻辑 observer 和自有 QA 都使用共享 API。

完整 `bridge_source()` 原顺序是 bridge + preview + quantities，必须在同一闭包中保留：quantities 引用 ebM/ebOwnedUi；bridge 的 NativeCallbacks、原始 trampolines、计时器和上下文互相闭包引用；preview thunk 与 quantity selector 原有 globalThis 引用要继续保留。按 shop_test 在正确 pin/startup 成功后启用一次，移除 probe 独立 create_script，并保留 bridge、preview、quantity 三类 ready 事件及原报告字段。不能拆散其中一段或在启动 pin 尚未满足时提前执行。

ebFrame/ebToggleFrame 返回的 handle 仍须提供幂等 logical detach。回调内 ebStopFrame/StopToggle 解除自身后，当前回调余下的原生流程继续执行；取消尚未进入的 observer 不得再进入，新增 observer 从后续帧开始。每 handler 独立 this.state 及每次调用快照必须沿用已修的 active 检查，避免 artifact/shop 状态互盖。原 native getter receiver 与 args/retval 只在对应回调内使用。

原生开关商城、category/cart 初始化、catalogue 身份与 generation 检查、超时及 ebRecover 语义应保持。它们调用 NativeFunction，不应被改成伪造 UI-ready、OS 输入、经济请求重放或异步替代成功。原有 preview 运行时 thunk 只迁移生命周期，不扩大 ASM 或修改原 EXE/KOM 文件。

## NativeFunction 发送锁边界

shop 帧 onLeave 会调用 ebToggleOriginal、ebEdRequest 等原生入口。已知 Gum listener 内 NativeFunction 重入可以抑制 sender listener；结果统计的 9E 有外层 sender 锁保护，但帧回调外层未必持该锁。具体商城原生链是立即进入 sender 还是稍后排队发送，本轮未追到原生指令，**不能把这项条件推断写成实证绕锁或历史闪退归因**。

下一步核收应沿既有发送观察/锁计数对应商城普通读请求，不新增第三个物理 hook。若确认商城 native-call 发包在抑制区直接发生而未持原 CS，需要明确同一临界区如何覆盖；不能仅凭 frame 槽数修正宣布全局发送竞争全部覆盖。此处是源调用链边界，未实施任何锁变体。

## 实现后最小验证建议

只补受影响输入：共享 frame 的动态进入/自取消/取消后续 observer/下一帧加入、独立 this.state 与错误报告；一轮自有原游戏正常打开 ED 商城、等原生 catalogue/UI-ready、正常关闭，观察动态 logical count 收回、frame 配对、sender 锁归零及既有 artifact/raid/result 就绪。保留 preview/quantity 的原资源身份，未变数值与经济主路径不重跑、不发经济重试。

当前为方案审查，最新 v2 字节和实际核收尚未交付独审，不能将旧 sender-only 的通过冒充本动态商城路径已经合格。PR948/V105 与 PR949 已完成交付不重开。

回归约束应纳入既有 compose 验证：正式 flags 下主 Script 对共享 frame 只物理 attach 一次，artifact/shop 的原动态站点转换到逻辑 API，probe 不再独立加载这两组 Script；sender 物理 C+JS 仍为两处。仅搜索地址会误把 pin/NativeFunction 算成 attach，不能作为 CI 失败规则。本只读任务未创建或执行新的 CI 检查，具体实现由主任务在冻结字节中完成。
