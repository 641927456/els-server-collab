# 两处 fast crypto 原型独立审查

**结论：固定原型的现有宿主输入通过，核心 TLS/锁/原指针发布未发现新的必修阻断；它尚未取得真实候选或签名发布资格。** 审查对象 `repair-v11/native_crypto_lock.js` SHA256 `57650c171a7b6aaa571e4e681f712b0b19b2a0855de5346de4da599a34759c3e`。本轮只读代码和既有回执，没有重跑测试、启动进程或修改候选/生产。

## 实现核查

- Held 为进程 heap 分配的节点，保存 ctx 与 previous，不借用已返回的 wrapper 栈。节点在调用原 crypto 前进入当前线程 TLS；同线程新 ctx 会保留外层。release 只在当前 top 的 ctx 匹配时 pop，未匹配的同类 destructor 仅 passthrough，避免误释放外层。
- 每次成功进入对应一次 recursive CS 获取。release 先恢复 previous、计数、LeaveCS 并释放 Held，再调用原 destructor；所以 destructor 自身抛出不会漏掉该次锁。原 native crypto 的 unsigned-char 返回值继续传回，原调用/异常没有被捕获并伪装成功。HeapAlloc 或首个 TlsSetValue 失败走明确 false 返回且记录 failed，未进入原 crypto；这一 OS 故障分支是静态核查，非本宿主已注入验证。
- CModule writable 数据均在 extern Memory cells，原 refs、CS/TLS/event/heap/metrics 与 CModule 由 lifetime 全局保活。hook 前的函数表检查若失败还没有安装；安装后即使第二步失败，已装 release 及其 original ref 仍保留可执行依赖。
- release replacement 先装并写其 original ref，再装 acquire 并写第二 ref。两个 wrapper 都在读取这些 ref 前等待同一 manual-reset ready event；finally 在 release 已装时置位事件，覆盖第二 replace 被拒绝的情况。SetEvent 调用可能提交待生效补丁，但此时所有成功返回的 ref 已写入，等待路径不持 JS 引擎锁。
- 生成函数的每个 call-return PC 都检查 RtlLookup 的实际 Begin/End 覆盖，避免仅查首字节而误判 TinyCC body 的 unwind 表。CModule、refs 和函数表内存没有热卸载路径，符合本原型的“进程先退出，再 detach”前提。

在上述前提内没有发现 TLS 节点失效、匹配清理漏锁、release-only 空原指针调用或现有 C++ 异常越不过 wrapper 的新源码阻断。该结论不包括外部提前释放 TLS/event、任意改变原生函数的生命周期或任意 native-body 取号后再重入；这些都不属于本原型/原静态调用链已证明的输入。

## 实际回执与夹具一致性

`test_fast_crypto_host.py` 使用真正 MSVC RAII DLL：八个原生工作线程各调用 sender 与 field，JS sender onEnter 又 NativeFunction 发一次、field onLeave 再 NativeFunction 发一次，共 240 包。`fast-crypto-host.json` 记录无重复、有序、counter 241；sender 与 field 各 80/80 返回。false、crypto 抛前/取号后抛、dtor 抛、同线程嵌套 ctx 五场景结果分别为 -1/102/103/104/1；累计 246 encrypt=246 cleanup，active/failed/RecursionCount 均零。最后的未知 ctx 清理未改变计数。mode 5 在外层取号之前完成内层，不能据此宣传取号后任意原生递归也有序。

回执列出 16 个 body call-return PC 的有效函数表，并且真实 C++ throw 穿过 CModule wrapper 后由 MSVC RAII 清理/捕获，关闭了“只有源码支持、尚未实际跨帧”的该宿主边界。它是独立 DLL，不是原游戏异常注入，也没有证明硬件 SEH。

安装失败夹具通过局部 Interceptor 参数令第二次 replace 抛错，finally 后 event 已置位、release ref 非空、crypto ref 仍空、lifetime 仍保留，随后未知 ctx destructor passthrough 完成。这个夹具没有在置位前制造并发等待者；它证明失败结束后的 signal/passthrough，不应扩大称为并发安装压力测试。原空 field 函数不可 attach 的首次夹具失效由主任务报告留在工具记录，不把它记成 crypto 机制失败或成功输入。

输入读回与回执一致：

| 文件 | SHA256 |
| --- | --- |
| test_fast_crypto_host.py | e93b88c4934981e91babaf44b28c87563dd91dfea78de45b3ff8ff769e1a8c9a |
| fast-crypto-host.json | 882ad52845c84c826f51ed115540874ac1c763e7bf2006acaaa0e55c89a0896c |
| crypto_eh_fixture.cpp | 3ecc231935324ad062aafa61addbc52c8d22e1537a959e300688da84ad9a7ab7 |
| crypto_eh_fixture.dll | 1bd22000a84601c11ce9c460155399683f749bdf2b6fd1cc1fc3e8c72753958c |
| test_fast_install_failure.py | 5c7ccedc9c625482321f32b469add68dd004fb5d52622577de1feb75b9f628ca |
| fast-install-failure.json | 7f05d49171872d1c5a1a99fe34faeeb2bf6097b4f0621427b12ae801d97028ad |

## 候选接入仍需核的变化

原型自身对重复调用明确 throw，不能把它称作幂等；最终外层 controller 是否复用同一实例需随实际集成审查。它也没有原游戏身份/pin 检查，不能脱离最终 helper 的固定镜像、原 callsite/destructor tail/EH 身份验证独立交付。真实两个入口可重定位/无别的占用、移除旧入口锁而保留单一共享 sender/field 分发、完整商城同 realm 生命周期，以及原游戏首次/重复加载与退出，只核接入后受影响输入。这里没有建议重跑不变的 240 包及异常宿主。

原型刻意将 native 资源保留到进程退出，不提供热卸载或失败后反复重试。Initialize/TLS/Event/CModule 早期失败的资源回收、Wait/SetEvent 的 OS 故障与 release 时 TlsSetValue 的失败没有被本回执故障注入；不能声称“所有 Windows API 失败都已测”。不因这些未触发 API 故障另加通用兜底，但最终生命周期不能释放仍使用的句柄/索引。TlsGetValue 确会清 LastError，原型并未保持该错误状态；当前已核原游戏调用链没有依赖它作为返回结果的证据，不据此捏造既有玩家问题。[Microsoft TlsGetValue 契约](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-tlsgetvalue)

原未发布候选的有限输入成功及新增覆盖缺口均保留。PR951 仍没有在此审查中取得精确 head 许可；已完成服务端双端交付不重开。

## LastError 与真实等待线程补审（后续原型 810e14）

新原型 SHA256 `810e14c9eb289714da28d76e2bc5b7d798e44f2d8057a60c660ac29354fc0512` 仅增加 Get/SetLastError 透明性处理。crypto 与 cleanup 入口保存调用方值，在 Wait/TLS/heap 等私有操作后、调用原函数之前恢复；正常返回后没有再覆写原函数新值。read_stats 也在完成私有锁操作后恢复。TLS/ctx 栈、先 release 再原 dtor、refs/event 发布与保活逻辑不变，复用前述审查，未找到新增核心阻断。此前“原型不保持 LastError”只适用于 57650c 旧字节。

更新的 MSVC fixture mode 6 在原生代码设置 777，原 crypto 观察到 777 并置 888，原 dtor 观察到 888 并置 999，最终仍为 999；`lastErrorPreserved=true` 与源码断言相符。受影响宿主主任务已重跑一次：正常 240 包无重复且有序，原异常与嵌套结果保持，增加该场景后累计 247/247、active/failed/锁递归零。函数表记录从 16 增到 22 个 call-return PC，符合三组 Get/Set 调用新增六处的代码变化。本独审未重跑。

新安装失败夹具在第二 replace 的局部 shim 中先 flush release，再启动真正原生 worker 调用未知 ctx destructor；finally 前该线程 wait 返回 TIMEOUT，置位事件后线程完成并执行 CloseHandle。回执 `waiter_blocked_before_finally` 与 `waiter_completed_after_signal` 均真，支持该失败安装输入下的等待与放行，不再仅是 finally 后调用。没有采样该线程 PC，因此按“置位前未完成、置位后完成”记录，不扩大成任意并发安装的压力证明。

新输入摘要：host fixture `aa43fdb1eb509111cd8c406c1cdd563d189281a840aa8614123d993d9a1517d0`，host 回执 `78452161b191c41217ef8d6b4f24f96d182d3c2fe3e101f437f94ea8f22ba96c`，C++源 `d26d817a365b9707892499d8f60fc858628eb281e6f7226b6cab37c2f3fd19b7`，DLL `21ad98f5b3573142e52c21b46090d911078a5a0acd7048e77d03cb37bae9d494`，失败 fixture `602f3840de84962493288fea619bd0d16db9440d8c5d97576276ea1d945ffc28`，失败回执 `ddf5140602fba3395381b1e185d8c0392a6b1771c6eef021d04c0967eaa155da`。

仍未接入真实候选/原游戏；外层幂等 factory、新原生入口实际重定位和完整商城生命周期由后续变化决定，本补审不授签名/发布或 head 许可。
