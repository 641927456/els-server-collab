# V59 签名包装构建器独立审查

结论：**PASS，可以进入构建/签名及既定运行核收。** 当前没有未解决的代码阻点。本审查没有执行 builder.main、签名、编译、安装或发布，也没有修改候选源码、生产、锁或 current；不是 V59 已升级成功的回执。

审查者 `/root/ground_hook_review`；构建器 `build_launcher_v59.py` SHA256：`9cfc0dd81290f9b6a2e038a843cb7f7e4aca84d90252fef5fbaec010519425b5`。V58父构建记录SHA：`890f2a7417ad7e6babe539864905fadd07b4077491657a106a5089bac4c1ffe4`。审查沿用 differential-review 方法，仅核本次必要闭包、前驱升级和恢复边界。

## 发现与处理

发现过一项确定的交付清单不一致：LOCAL business索引仍保留 cache/profile旧SHA，且没有登记两个新支持文件；构建器原有 `business ⊆ runtime` 严格断言将拒绝构建。负责人已修交付准备器，保留修正前metadata，并把所有7叶纳入business；没有删除或放宽构建器断言。

已独立重核修正后的1433个business条目全部等于runtime对应行且匹配实际文件；runtime仍1887，payload行未变。bundle manifest SHA为`3b6e734b2c6552d75db50707ff4917487dc4d81c70bbb901a42f9f0d1647a64d`，business manifest SHA为`041fd5b6334374bc766b3cc6289cca0de27b3c38932981ccf9c63d205fc2cf94`。相同payload的已完成观察可以复用。发现已解决，无残余阻断。

## 闭包与选择检查

- signedLOCAL以实际rawLOCAL1887为输入，精确核7叶delta和实际manifest；相对V58的其他差异被严格限制为最新邮件3源，检查了这3源实际SHA。生成时保留LOCAL原签名mode/config/入口，继承所有已装业务及两新支持。没有玩家数据库进入构造过程。
- signedFriends从自己的V58父定义出发，只改变3个支持文件和自身profile；独立投影核得1798行，其他组件和全部mode文件保留。没有把LOCAL profile或LOCAL mode文件覆盖给Friends。profile中的依赖SHA按各自最终文件集绑定。
- 86个V58源输入和59个既有资源逐SHA核对；新资源名4个与旧名无交集，最终资源63个。构建器先复制旧源，再仅修改选择接入/版本/新资源，并新增RegisteredGround类；旧GroundFashion类仍存在并用于旧方向识别。ComponentRuntime正常默认和Accessory LOCAL均选择RegisteredGround；新类中没有遗留 `Version==58` 条件。AutoUpdate.Version唯一改为59，其余升级/公钥能力保留。
- 旧资源签名/envelope/archive/文件行由构建器使用既有发布密钥对应的公钥和固定SHA核验；新输出继续使用原签名机制。新包定义、C#cohort和资源hash均从同一实际构建结果生成。

## Bootstrap与恢复检查

执行了构建器的**纯内存转换函数**进行AST差异核对，没有调用main或任何写候选/签名函数。新增函数仅 `registered_ground_v58_predecessors`。旧函数中仅 `repair_policy`、`managed_is_old` 和 `repair_guarded_documents`发生变化：前两者增加精确V58前驱/策略；第三者只把1885/1887计数对应改为1887/1889。其余旧函数AST不变。

新前驱同时绑定文本长度/文本SHA、base64压缩内容SHA、8MiB解压界限、envelope/metadata身份、旧文件数/归档SHA和formal rows/key；保留原14项传递前驱并只加V58精确key。新bootstrap所需前驱资源由LocalBootstrap按同名文件及固定hash写入，旧前驱资源继续保留。

四个原guard payload及其原始源字节完全保留：relationships、couple_closures、identification_ui、fixed_cubes。`repair_original_restore_allowed` AST仍只有 `return False`；没有重开bare parent或数据库恢复。运行数量、support overrides/additions及排除metadata的完整行hash按新闭包更新，没有借计数更新弱化原读者保护。

## 边界

只读核查结果见 `launcher59-verified-inputs.json`。审查时目标rawLOCAL尚未promote；构建器仍要求实际readback成功和current精确指向目标后才构建，不能把本报告当作替代证据。V58→V59真实Run、repeat、自有typed存档、Friends实际选中、source compose和公网上的正式签名分发仍由负责人后续执行与记录，本报告未标记这些验证通过。

纯转换源码中的set字面量顺序可能随Python进程变化；本审查比较常量语义及函数AST，实际BootstrapHash必须绑定实际构建字节，不能把一次独审生成的辅助source SHA硬填入正式构建。构建器当前正是对实际生成字符串求hash并写cohort。
