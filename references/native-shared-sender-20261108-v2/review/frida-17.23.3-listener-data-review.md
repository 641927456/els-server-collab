# Frida 17.23.3 监听器数据槽只读审查

本轮只读源码、启动参数和已有脱敏回执，没有运行宿主/原生测试、启动游戏、修改候选或生产。PR948/V105 双端交付和 PR949 合并已完成，本审查不重开该交付；原生锁仍未发布。

## 版本固定与已证实缺陷

固定到 Frida 17.23.3 对应 Gum 提交 `1208a1266e9d28e6c958b6a167b6d944ebefaf47`；主任务已通过该发行版的 submodule gitlink 核定，本地现存包元数据也是 17.23.3。本轮未用 main 替代，也未做二进制与源码重建比对。

该提交的 [gumdefs.h](https://github.com/frida/frida-gum/blob/1208a1266e9d28e6c958b6a167b6d944ebefaf47/gum/gumdefs.h#L452) 将每函数 invocation-data 槽数固定为 **2**、每槽 1024 字节。[guminterceptor.c](https://github.com/frida/frida-gum/blob/1208a1266e9d28e6c958b6a167b6d944ebefaf47/gum/guminterceptor.c#L128) 静态分配此二维数组，添加 listener 却可无限追加；入口和返回都以完整 listener 序号直接取槽，无序号边界检查。因此第三个及之后的槽访问在这份源码中确定越界。仅验证 `required_size<=1024` 不限制 listener 序号。

这不是“只允许两个 JS listener”：C、JS、entry-only、leave-only 只要各自是一个 Gum listener，都会占列表位置。源码中的槽是每线程/每次调用的数据，不是跨线程共享一个 JIC；不能把两线程同时进入直接等同于数据槽碰撞。

## 为什么 paired 与 leave-only 可以不同

[gumquickinterceptor.c](https://github.com/frida/frida-gum/blob/1208a1266e9d28e6c958b6a167b6d944ebefaf47/bindings/gumjs/gumquickinterceptor.c#L1199) 在入口保存 JIC；有 onEnter 的返回处理若拿到空 JIC，会直接跳过。leave-only 则自行取得新上下文。因此现有“paired 返回缺失、leave-only 仍执行”与坏槽/错误槽一致，不能由 leave-only 成功证明旧 JIC 完好。该 getter 实现要求原生 opaque 对象作为接收者，后续共享分发器不能直接用普通派生对象冒充它。

**没有直接观测到实机 `state->jic` 的读写地址或清零指令。** 已确定源码容量缺陷与实际超额注册；“具体是哪一次越界覆盖导致全部 paired 返回丢失”仍是高度相关推断，不能写成已在实机逐指令证实。

## 动态注册与调度的解释范围

添加 listener 会压缩旧列表的空洞，入口/返回又分别读取当前列表，故在途调用可能发生序号换位；单纯末尾追加不会改变已有无空洞 listener 的序号。它能解释部分 late 注册现象，不能独自解释注册稳定后的持续 252/0。

[gumquickcore.c](https://github.com/frida/frida-gum/blob/1208a1266e9d28e6c958b6a167b6d944ebefaf47/bindings/gumjs/gumquickcore.c#L1951) 的 cooperative 调用释放/恢复 JS 锁并结束/重开事务；正常成功路径没有直接清空 JIC。它会改变可重入和注册生效时机。Gum 栈是可移动的 GArray，回调跨 JS scope 时保留原始数据指针，嵌套扩容/移位也是待排除因素，但现有回执未证明发生过。C/noop/全 JS 都失败已排除“只有 CModule 才可能出问题”的解释；不能据此认定 cooperative 契约无效。

## 实际 sender 注册清单

| 来源 | 物理 listener | 启用条件 / 作用 |
| --- | ---: | --- |
| trace 主发送观察 | 1 | startup pin 成功后；只读记发送 |
| Noah 返村观察 | 1 | startup 后独立 timer pin 成功；角色检查在 callback 内，不能据角色不符扣掉注册数 |
| raid native power | 1 | 缓存首次初始化；成对恢复 thread/previous/bound |
| dungeon result stats | 1 | 缓存初始化；BB/471 前重入原生 9E |
| artifact restore | 1 | `item_test && login_hooks_ready`；原来另一个 Frida Script，记录 0x227 时间 |
| 自有诊断 paired + leave-only | 2 | 测试器额外挂接，正式产品不包含 |
| 发送锁候选 | C-only 1；split 2 | 所有变体均未发布 |

已有两次真实 trace 的脱敏顺序一致：main hooks ready、Noah ready、自有 observer loaded、artifact ready，然后才有首个 owned sender enter；raid/result 两组件稍后 cache 初始化成功。故无 gate 自有基线首包前至少 **5** 个、缓存后至少 **7** 个；全 JS split 再加 2，为至少 **7/9** 个。正式入口不含自有诊断，但有 artifact，仍为 **3/5** 个。不同 Script 的 listener 也汇聚同一个 Gum function context，不能分别按 Script 计算容量。

baseline 250/250 是事实，但其注册也已经超过源码容量。越界环境偶然工作不证明安全；新增 gate 只是改变排列、越界落点和时机，不能把 baseline 的成功当作源码缺陷不存在。反过来，也不能只凭越界源码抹除实机逐槽归因尚未闭合的边界。此前超过 2 个物理 listener 的宿主成功，同样不能继续作为安全资格；原始观察记录保留。

## 其他地址按真实参数核算

`COMMON_FLAGS` 令 dungeon、gate、population 均启用，且 item_test=true。worker 仅把脚本 lightweight 常量改为 false。`formal-V105-composed.js` 的行 1494 否定分支不执行，因此：

- c231c0：执行 dungeon 分支的两处，实际为 2；其中 offline 回调虽可能立即返回，也占物理槽。
- 30d0660：启动时主 dungeon 分支 1，加 artifact 1，共 2；先前未覆盖的商城操作会再动态注册至少 1，达到至少 3。此处不是全程上限，已由 [ED 商城同类补审](shop-frame-variant-review.md) 纠正。
- 680b50、1ab7ac0：现有静态清单各两处，没有本轮确证的第三处。

不能把 c231c0 的三个静态站点全算成正式入口执行数。非正式参数若 dungeon=true 且 gate/pop 任一关闭，前述否定分支与 dungeon 分支可同时执行，另有 3 的可达性；这不是本轮真实启动组合的已运行结论。

## 最小方案与下一步诊断建议

“一个原生 C 锁 listener + 一个 JS 共享 dispatcher”能在结构上守住 2 槽，方向可接受；当前尚未实现或取得资格。共享化必须覆盖主 compose 的 4 站点、artifact 的第 5 站点以及自有 QA 注册。不能为核收再额外挂第三个观察器。

将完整 artifact 闭包装入主登录脚本，按 item_test 在 startup 成功处启用，并移除其独立 create_script，能避免跨 Script globalThis 不共享的问题。保留 pin、ready 事件、报告字段和唯一加载；其 pin 使用函数体地址，不依赖 sender 入口原始字节。初始化时机提前到原生 startup 回调的差异须在下一轮核收说明。

分发器应保存每次调用的 handler 快照及每 handler 独立状态，沿注册顺序传原 args/retval，不复制或重造协议。`this.thread/previous/bound` 不能跨组件串用；原生 getter 应以原 IC 为 receiver（如 `Reflect.get(ic,key,ic)`），普通状态保存在独立对象，原 IC/args 只在回调内有效。保持现有 NativeFunction 重入抑制和原生计算；C 锁先取得，再进入 JS callback。异常沿既有错误出口报告，不能吞错或让已进入组件丢掉返回清理。

建议下一步只做一个最小差异对照：相同共享 JS dispatcher、相同逻辑组件与自有诊断，A 仅一个物理 JS listener，B 在它之前加入一个 C 锁 listener；两者都不越 2。若 A/B 都恢复配对，才得到针对实机的容量解释支持；若仅 B 失败，则需继续查锁/调度因素，不能宣布根因已完全闭合。本轮只提出此建议，没有执行。

随后必要验证限于物理 2 的独立状态/动态注册/原生 9E 重入宿主，以及一次自有原生同 sender 多线程、回调配对、artifact/CP/结算支持和正常退出。旧超额 listener 的宿主通过不代替这些新输入验证。原生发布阻断保持，已完成 Git/双端交付不受影响。
