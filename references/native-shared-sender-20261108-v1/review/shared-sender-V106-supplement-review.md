# V106 新父输入补充独审

**结论：受影响输入的静态补审通过，未发现与共享 sender 的新冲突；已读取主任务一次新父自有原生核收 249/249 的成功回执。** 其余独审及不变宿主结果复用，没有重跑测试、改候选、启动进程、操作生产或合并 PR950。

## 固定边界

父版为已安装的 `native-achievement-guild-banner-power-20261108-v1`，manifest SHA256 `43410f5b300f1e0840f13c1d418daeb9c3240f4dab6760d954a28e5b3f34af41`。主任务的 `V106-parent-integration.json` 核过 2873 个父文件，保留 8 项新父改动；本补审只检查相关 native 输入，未重复核全部父文件或重审另外六项服务器业务。

主任务 `V106-parent-Git-binding.json` 记录 PR950 源 head `ff83bc2f5cef207a7dd57689175c4c1589a2f21c` 的真实归档字节与已安装 raid 脚本相符。本补审不代替 PR950 审批或合并；该 PR 未由本会话合并。

| 输入 | SHA256 |
| --- | --- |
| 旧 V105 raid_native_power.js | 28879678bbe97ecaf84ad9041c43161289311be4eb769f9b6d1c2cc24cd2fd94 |
| V106 父版与候选 raid_native_power.js | 2fb90926b79bdc7720b3333524c49995279d1a6f2a0331b48b6e26298f911caf |
| 新完整 compose | a0782e8ac26eec1991b4a66510d2bd3fac374cb92edc309b73eca18ede6594ae |
| 新兼容 profile | f78c124086ac511a65b3c9e198029b792874e7f2b74d3509e6a597d164749bbd |

核心 JS `fd12ae7eee4459565e652779a177f460575fe827976a1eb339d9073f85b3cdfe`、helper `f4bdd3a281c82adb98f7b51c3299e679e5d0a79701a21541661a9b0ec5ac6133`、probe `ccbde4b8d759ed2ceb93cfff4d2c93326b88039675e9afb44e9943ac5d90106e` 均实读确认未变，原两项缺陷修正和 dispatcher 宿主资格直接复用。

## raid 父差异与整合

新父 `capture()` 将 Engine+C0 作为共享句柄，核对其 pointee 与本次 sender，并保存/比较 owner 与 control。它们保存在既有 bound 普通对象中；sender hook 的 `this.thread/previous/bound` 字段及配对恢复代码未变，Proxy 不会把新增字段转发到原 IC。

同一观察器的 kind 集合加入成就快照 0x6BE，其基础 payload 必须为零长；新增 `if(length)` 避免零长原始 buffer 拷贝。它继续沿原生 build/store、既有 encoder 与 CP 附加格式，没有新增物理 attach、逻辑 handler、递归分发或数学公式。新 owner/control 在计算前后复核，与共享调用生命周期兼容。

新完整 compose 中 sender 仍只有 C 锁和 JS dispatcher 两个物理注册，五个业务逻辑注册（artifact、raid、result、trace、Noah）均保留。raid 父的新 0x6BE 分支位于同一个逻辑注册里，encoder 680B50 路径未增加监听器；artifact 同 realm 与独立状态、NativeFunction 重入抑制、正确原生 getter receiver 等约束均未变化。新 profile 同时固定新父 raid 字节与已审核心字节。

## 一次新父实机结果

本次读取 `repair-v10/owned-native.json`，run `20261108-024451`：真实原游戏与自有临时认证服务器，相关组合支持加载，249 次锁内 entry/249 次普通 JS return；7 个逻辑观察器、源码物理 2。32 秒自有场景，协议错误 0，锁归零，artifact/raid/result 就绪，同进程脚本重复安装幂等，自有进程正常退出及 detach，原 EXE/KOM 不变，未控制玩家进程。

旧 V105 的 250/250 回执另存 `repair-v10/V105-owned-native.json`；它不是此次新父结果。原 704 包宿主的输入核心未变，未重复运行。此结论只覆盖本次整合及相关自有原生核收，不扩写为 PR950 全业务审查、历史重复序号逐例自然归因或具体 JIC 覆盖指令已证实。

可继续主任务独立签名/交付流程；尚未发布的事实和精确 head 的审批要求不由本补审代替，已完成 V105/PR948/PR949 不重开。
