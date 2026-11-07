# 共享 sender 候选独立审查

**结论：最新固定字节的代码审查通过，两项发现均已修正；已读取主任务同字节宿主与自有原生核收成功回执。没有剩余已识别的源码阻断。** 本轮审查者仅只读核代码、摘要及已有回执，没有运行测试、启动进程、修改候选或生产。正式 V105 和已完成 PR948/PR949 交付保持原状态；本原生候选尚未签名发布。

## 固定输入

| 文件 | 最终 SHA256 |
| --- | --- |
| tools/native_send_serialization.js | fd12ae7eee4459565e652779a177f460575fe827976a1eb339d9073f85b3cdfe |
| tools/native_send_serialization.py | f4bdd3a281c82adb98f7b51c3299e679e5d0a79701a21541661a9b0ec5ac6133 |
| tools/probe_updated_client.py | ccbde4b8d759ed2ceb93cfff4d2c93326b88039675e9afb44e9943ac5d90106e |
| tools/client_compatibility_profiles.json | 8bbbb89d91b163dde4d6c14c3cd925a8f319080ee14f98363053b81eb249ce25 |
| repair-v10/composed-native-login.js | 554cd384f2763aa3beb9f0a299e2e0b208cd834722cb2482cc2aa94c6cc63c7a |

已用实文件摘要与 `repair-v10/native-composition.json` 对照，输入父版来自 `repair-v10/parent-inputs`。主任务原宿主结果是 528 包；修正动态取消后增加一个必要场景，最终为 704 包，本审查复用这些结果而未重跑。

## 两项发现及修正

1. **原 probe SHA33665… 的启动阻断。** 新 artifact-ready 事件分支比相邻事件分支多缩进一格，在单行 if 后形成 unexpected indent。主任务将其对齐并做 compile 校验；审查者再次读取最终 207–209 行确认缩进正确。首次退出失败保留为 `repair-v10/first-owned-startup-failure-*`，没有把未启动游戏当成实机通过。
2. **原 JS SHA57692… 的取消语义错误。** A 的入口回调取消尚未执行的 B 时，快照仍会执行 B.onEnter，随后又因 inactive 跳过 B.onLeave。最终循环在进入前检查 active，修正为不调用 B；新增宿主场景得到 B 0 enter/0 leave。已进入后再 detach 时仍按原 Gum detach 语义跳过其后回调，由原组件 dispose 处理自身清理。

## 实际实现核查

- **物理容量。** 完整生成脚本中 sender 仅两处物理 attach：原生 C 锁与 JS dispatcher。四个主 compose 站点和 artifact 第五站点都改为逻辑注册；自有 QA 两个观察器也走该 API，未为核收再挂第三个 listener。逻辑注册与 detach 不增加 Gum 槽。
- **锁与重入。** C listener 先安装，原生等待不取得 JS 引擎锁，递归 CS 覆盖原序列化、计数、加密与队列。仍执行原生 sender；result-stats 的原始 9E 嵌套发送维持现有 Gum 重入抑制及原有 writer scope，没有伪造报文、禁用服务端序号校验或替换 EXE/KOM。
- **状态与 getter。** dispatcher 每次入口保存快照，每 handler 单独创建可写状态；thread/previous/bound 等字段不共享。`Reflect.get(native,key,native)` 保持原生 opaque receiver，errno/lastError 写回原 IC。原 args/retval 按注册顺序传递；返回使用对应快照及状态。只覆盖当前已使用的 Frida 回调契约，不宣称任意外部脚本都能直接追加物理 hook。
- **异常。** 每 handler 的异常被转交 `setImmediate` 重新抛出，其余 handler 仍获得入口/返回机会；原生 Script error 通道保留，未吞错伪装成功。主任务宿主收到唯一预期测试错误，正常原生运行没有协议错误。
- **生命周期。** 两个物理 listener、CModule 与 lock 保存在单一进程级 controller；重复安装返回同一个 controller，没有活动进程内销毁 CS 的路径。逻辑 detach 只改变 registry，不卸载原生锁；关闭仍在自有进程结束后 detach。
- **Artifact 同 realm。** 完整原 artifact 闭包装入主脚本，按 `item_test` 在 startup pin 成功后启用；独立 create_script 及旧 startup_artifact 变量已删。ready 事件仍触发原报告字段；artifact 的 30d0660 hook 保留，正式 COMMON_FLAGS 下该地址仍共两处。只改变登记与加载位置，组件正文与原生计算继续复用。

## 读取并复用的相关核收

`repair-v10/shared-sender-host.json`：物理 2，四个不同场景各 176 包，共 704 包，均无重复且严格有序；raid/result 各 352/352、artifact 176/176、late 264/264，独立原生 getter 均匹配，剩余状态 0、锁递归 0、动态 detach 与预期错误报告通过。宿主计数通过局部 Interceptor 参数观察，没有修改全局只读 API；原先试图修改全局 API 的夹具失败已保留。

`repair-v10/V105-owned-native.json`（由主任务从当时 owned-native.json 保留）：实际原游戏、自有临时认证服务器、实际组合支持加载；7 个逻辑观察器（5 业务+2 QA），sender 源码物理 2；250 个锁内 entry/250 个普通 JS return，32 秒自有场景运行，锁归零，artifact/raid-power/result-stats 就绪；协议错误 0，重复安装同实例，自有进程退出及 detach 完成，原 EXE 不变、未改 KOM，未控制玩家进程。

这证明新共享候选在本次相关调用链与自有加载核收中修复了回调丢失回归。就绪事件不扩写为完整自然团本结算或所有角色的自然 artifact 恢复；过去十次重复序号的逐例自然归因、具体 JIC 覆盖地址/指令仍未证实。旧超额 listener 变体的失败和早期误判均保留。

代码可进入主任务的签名与交付准备；本独审不代表已经发布、GitHub 人工审批或新 head 的合并许可，正式签名包升级及实际安装结果仍由发布负责人记录。

后续当前父版升级为 V106，相关 raid 输入与新 compose 另见 [V106 补审](shared-sender-V106-supplement-review.md)。新父实机是独立的 249/249，未拿本页旧 V105 的 250/250 代替。
