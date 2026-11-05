# 登录组合器修复独立审查

结论：源码的一项精确 trace 指纹补登记合理，未削弱 EXE、内存、锚点或逆向组合校验。原“运行包只改一个成员”的交付合同存在已复现的启动阻断；本目录已给出必要的第二个清单元数据变更。完成签名与实际加载核收后才算交付。

## 范围与风险

审查对象是不可变发布文件，以完整 SHA 对比，未切换或修改共享 Git 工作区。没有可用于这些发布树的直接 Git blame，历史依据采用原签名清单、V75/V78 精确输入及交接验证。审查覆盖两个生产成员、实际兼容性选择入口及未来公会组合器；没有新增 Hook、业务、资源或数据库变更。

该改动触及支持代码的身份准入，按高风险入口检查。新源码只增加规范化 trace SHA a155d2c5b8ab7197340eae32364a48d598ec6b7bffbe5523c443f9f1f0a20a08；删除该常量赋值后，父版与候选完整 Python AST 相同。旧四个 trace 均保留，所有函数体及外层组合顺序均未改动。

## 确认的交付缺陷

严重级别 P1，影响正常用户启动。父版 tools/client_compatibility_profiles.json 将 tools/native_cache_sync.py 固定为 e64195b3235c6f40a62c31dd7e5bcfcb22add2ed9be7b68a5d48745a96477085。原合同仅替换该 Python 文件为 c83eb42b71c4e37ac5f72cf2e53c7fce2e093f718429b7f6cf48bb537a2dbcb7，client_compatibility.select 的逐成员校验会先抛出 “Client compatibility dependency changed: tools/native_cache_sync.py”。

该结果已通过实际 select 入口、完整当前 profile 依赖集合复现。把清单中唯一的旧 SHA token 换为候选 SHA 后，同一实际入口通过。清单其他字节保持一致，校验逻辑没有改动。

| 成员 | 父 SHA256 | 候选 SHA256 |
|---|---|---|
| tools/native_cache_sync.py | e64195b3235c6f40a62c31dd7e5bcfcb22add2ed9be7b68a5d48745a96477085 | c83eb42b71c4e37ac5f72cf2e53c7fce2e093f718429b7f6cf48bb537a2dbcb7 |
| tools/client_compatibility_profiles.json | 03cc130f3f3c6bd4ada7eaab3e016552687ce93d70788521553bce5300deb7ed | 2e454cf89dbfec8c02008a18881be2b66cc75a98cc6ac66fa623a1d135dc9f76 |

## 入口、影响和对抗检查

直接生产调用者为 tools/probe_updated_client.py:108-109，它在启动客户端前先完成磁盘预检，再执行组合。该 probe 由 launch_client.py:225 的共享启动流程调用，两种模式使用共同组件。错误会阻断两个模式，不能用签名成功替代完整启动结果。

普通用户改动 trace、EXE 或内存时，新增的一个精确 SHA 仍不匹配；相应拒绝由未改变的身份与 trace 条件执行。新增值只允许已审核的 bootstrap 127.0.0.2 trace。原组合锚点唯一性、替换后的逆向校验及全部支持模块调用均保留，没有扩大为任意模板接受。

## 验证与复用

原 repair-v1/verification.json 的精确 SHA 为 63584bede4f8c03a3bcdd54f9dccf4f7bf6a890414c4e63bac0e04a03d11667e；其 22 项同输入成功结果直接复用，未重跑。它覆盖完整 121693 字节组合、当前和旧 JS 语法、错误 EXE/内存和篡改 trace 拒绝，但没有覆盖替换后的 profile 预检，因此才出现上述交付缺口。

本次新增两个必要场景：旧 profile 加候选 Python 的实际预检失败；更新单一 pin 后实际预检通过。其余断言是输入与文件 SHA、AST、归档及复用条件核对，verification.json 的 107 个断言不代表 107 个业务场景。首次搭建 G 盘测试输入视图时，C 到 G 的硬链接因跨卷失败；未启动游戏或写正式文件，改为经 SHA 核对的现有 G 盘自有输入硬链接后通过。

## 未来公会候选保留

未来公会叶 705c244e2130d2087b8d8751bb76c805f5311c1e6b913e343433a70aea48368d 已包含同一批准指纹，其 trace 集合与本次登录修复相同，profile 也已匹配该 SHA。与本次登录修复相比仅保留既有 guild_native_power import 和外层 guild_compose，无需增加任何新行；冻结副本在 future-preserved/，不得用独立登录叶覆盖它。

未来叶精确身份还匹配根会话两次实际游戏资格回执：普通角色及露／希尔均完成原生 CP 序列化、持久化及自有 Job 退出。该既有结果直接引用，未为无变化叶重跑游戏；不把它当作本次独立签名运行包已发布或已加载的证据。

## 交付要求与未验边界

发布负责人使用 current-overlay/ 的两个成员构建，保留其他 2119 个当前成员字节及文件集合；同步启动器已有 profile 元数据绑定。原签名、正式运行包、current、玩家／账号库、本地私有存档均未由本审查修改。

旧启动器升级后选中这两份新 SHA、签名包实际加载、完整自有隔离启动与正式发布仍由发布负责人核收。本审查不是 GitHub 人工审批，不授权主干绕过，也未声称自然游戏画面核验完成。
