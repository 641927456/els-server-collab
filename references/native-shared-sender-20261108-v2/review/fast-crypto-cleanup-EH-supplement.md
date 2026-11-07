# crypto/cleanup 方案 EH 新证据补审

本补审只覆盖主任务新增静态 EH、constructor/destructor 和事后输入绑定。**C++ EH 的同 ctx 清理映射已取得静态证据；实际 wrapper 展开、TLS 与安装仍未资格通过。** 原方案报告保持历史快照，本补录不代表实现或发布许可。

已读 `repair-v11/original-sender-EH.json`（SHA256 `49d8f05cd2babc7c33da296b101593ac28c2b23b70a20f3b54b770a927bc1759`）、`inspect_sender_EH.py`（`42690c4fbe3c763dd09994b45cf62a117ab488fdb377f18a9c448e81f5613f7b`）与本机 MSVC 14.29.30133 的 `ehdata4_export.h`（`5238200f91179f8411f5518d1bdee143833bc35e5f869bfb3631983c747e3566`）。逐段对照表明 Python parser 的 0x28 header 字段顺序、压缩整数长度/移位、UW byte-offset 回退、type 1 对象语义及 IP delta/state-1 均符合该头格式；这是源码/数据复核，未执行 parser 或编译测试。

十个 UW entry、二十一个 IP entry 中，crypto 起至 cleanup 前的四十三个 call 均经 state 6：action `3B7D620`、type 1 (`DtorWithObj`)、frame offset `D0`。原 prologue `rbp = preSubRSP - 10` 后减栈 `110`，所以 constructor 的 `rbp-30` 正好为 `postRSP+D0`。本机 vcruntime `frame.cpp` 的 FH4 action 也确实按 frame 加 object offset 传对象地址；不是再解引用一个对象指针。对这些原调用点，只要 C++ unwind 正常进入原 sender handler，同一个 ctx 的 destructor 是有依据的清理入口。

后续已补读 `sender-EH-frame-binding.json`（SHA256 `c892ce27865f7759c524758a263f54925153187c0e0c77819a5d4a226852cf12`）：RUNTIME_FUNCTION 为 `682D80..68364B`，UNWIND_INFO 为 `443B074`，FrameRegister/FrameOffset 均零，基准为 postRSP。所录 codes 的 ALLOC_LARGE `22×8=110`、七个 push，以及 RBX SAVE `2C×8=160` 与原首条 `[entryRSP+18]` 的保存槽相符；同 ctx 的 `D0` 基准已闭合。这仍是静态证据，不覆盖硬件 SEH：header 的 EHs 位已置，主任务也明确没有宣称该范围。

`compile-EH.log` 记录 C++ 官方 decoder 编译因本机缺少 `crtdbg.h` 而失败，未运行微软 decoder；主任务改用按已固定头格式的独立 Python 解码是如实替代，不能写成微软可执行结果通过。

## 改为 destructor 入口先释放

原 `3B7D620` 的真实边界是前四条指令：写 ctx vtable、把 rcx 加 8、尾跳 `16FA20`；之后的 int3 padding 与 `3B7D640` 是另一个函数，不应纳入 destructor。正常队列调用已经在 `683585` 返回，随后 `68358E` 装载同 ctx，`683592` 才进入 destructor。

后续已补读 `cleanup-tail-chain.json`（SHA256 `845b6d37cc7c56a9150a194dae5ebaf2ce99e2a4c2187cb6bd2f2c54cd0d0966`）的精确边界：`16FA20` 写 ctx+8 的 vptr，再加 8 尾跳 `1527C0`；后者完整 pdata 范围只处理 string 的 ptr/size/cap、必要时调用 `4F40A0` free、重置空串，坏分配路径 failfast。它没有回到 SAS/队列状态。原来的无 pdata 截断产物混入邻接 padding/下一个函数，额外范围不能作为 destructor 证据。

若最终 wrapper 只在匹配该线程/ctx 的持锁记录时先弹出该记录并 LeaveCS，再调用原 destructor，则锁内发送已结束、原 destructor 后续不返回也不会再漏掉这一把锁，原先后置释放依赖的设计阻断可以解除。仍须保留原调用及异常语义；未知 ctx 的清理仅 passthrough，不能释放其他活动记录。本结论没有宣称全局 allocator 绝无任何扩展回调，而是核定这条原清理链不再处理发送状态。

## 未关闭的实现边界

实际 CModule wrapper 在原 crypto 抛出时的 Windows 函数表查找、跨 wrapper 展开，以及 EH action 真正经过 fast entry，还需主任务后续相关宿主验证；本审查未运行它们。固定 TinyCC 的生成器回填 prologue 后才记录 unwind entry，实际检查不应仅查询 wrapper 入口：应查询调用原 crypto 后用于回溯的 body 返回地址与相应 Begin/End 范围，避免把入口查询空值误判成整帧无 unwind。

后续精确原型 `57650c…` 已在主任务的真实 MSVC RAII 宿主取得上述跨帧/函数表结果，并经[原型独审](fast-crypto-prototype-review.md)读回；本段保留前一时点，原游戏集成资格仍未取得，不将后续宿主等同原游戏加载。

TLS 记录跨 wrapper 返回仍有效、嵌套保留外层、release 前后错误状态、原 trampoline refs 在 hook 生效前发布、成对安装及模块保活，继续沿原方案报告逐项核实际代码。本轮没有新的源码变更，不能据静态 EH 通过代替这些实现结果。

主任务拟以 private ready event 在 release 端先挂、两个 original refs 写好之后放行，能针对自动 flush 的发布窗口；实际代码尚未在本补审中取得。安装失败时也必须处理已经进入 wrapper 的等待线程，不能保留永久未置位的事件等待。冷启动/不热卸载有助于收窄生命周期，但不代替该失败路径与进程退出前保活的实现核查。

## gap 输入绑定补录

`gap-input-binding.json`（SHA256 `95875422d0ff465583aec62620b276622168bae81712ab48ec4245eee230d98c`）明确注明事后绑定。独立读回 `gap-inputs` 两个文件的 SHA 与附录一致：JS `fd48b70fe840ffb0edc825b65f3f75175f35dc010f9a55c364508d1ada292530`、helper `c9e4a09da78ab2ad9f7bcacfe7e0c03f31b705c0fa56d5b4c556afc29841e7c3`。附录所述无间隔改动来自主任务工具时序，不伪装成夹具运行时自身记录的摘要，也未归因旧 fd12 逐字节失败。

没有实现、运行测试、启动宿主/原游戏、修改候选/生产或重新部署。旧有限输入成功、PR951 未发布与既有服务端交付完成状态均保留。
