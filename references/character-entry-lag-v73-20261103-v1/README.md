# V73 角色进入模板查询修复

已发布版本 `launcher-character-entry-lag-20261103-v73-v1` 的源码补交，关联 Issue #772。基线为 `a9a3e805d8b013ae7ecbfb4e2286b1abc26eb102`。本 PR 不重新部署或改变任何 current。

首次模板查询曾全量遍历 181836 个模板。V73 继续调用原生二分查询，仅在返回已批准、归属正确且可写的模板时调整现有堆叠上限；保留单件、未批准、缺失模板及已有更高上限。没有新增挂点，既有查询挂点为 `0x6d56c0`。

运行增量仅 `tools/local_stack_limits.js` 和兼容性 profile，两个已发布文件均按精确字节归档在 `support/tools/`。根目录继续保留原开发入口和 profile，避免破坏历史运行清单的冻结 SHA；本版本归档不激活根目录运行时。精确组件差异见 [source-contract.json](source-contract.json)。

启动器 141 个构建输入只有 `AutoUpdate.cs`、`UIScrollRuntimeCohort.cs` 和 Friends 签名资源变化。[构建输入](launcher/compile-inputs.json)逐文件映射本目录三份增量与 Git 内已有的 V72 源码，逐 SHA/尺寸锁定，不重复复制其余 138 份。按 source_path 物化这些文件后，沿 V72 的编译参数、资源名、引用和外部图标构建。现有签名信封原字节保留，不包含签名私钥；此 Git 归档尚未重新编译或重新签名。

复用 [八项模型检查](evidence/stack-adapter-tests.json)、304 项原生查询回放、独立 Hook 审查和公网 V72→V73 签名升级结果。[脱敏摘要](evidence/qualification-summary.json)保留原证据 SHA：1804 文件核验、2 文件下载、1802 文件复用、再次下载 0，公网观察 120.79 秒。原生首次查询 212ms→低于 1ms，连续 10000 次查询 106/106/107ms→93/93/94ms；这些局部结果不证明整段长停滞全部消失。完整自然 GUI 选角仍未核收，两次先前隔离 GUI 失败不转为成功。

原模型检查脚本保存在 `evidence/test_stack_adapter.cjs`，运行时从其所在目录的 `client-parent/tools/local_stack_limits.js` 与 `candidate/tools/local_stack_limits.js` 读输入并写结果；复现须在临时目录布置 Git 基线和本次 JS 后运行，不能覆盖冻结证据。本次核归档字节、SHA pin、构建输入和提交守卫，复用未变化的游戏、经济与原生测试结果。首次 CI 因直接替换根目录 JS 触发历史清单尺寸核验失败；最终提交改为独立版本归档，保持历史入口和清单原字节。

游戏服务端和 LOCAL 载荷不变，无存档迁移，不含玩家库、凭据、原始抓包、运行日志、原游戏 EXE/KOM 或发布二进制。需要恢复时由发布负责人按既有流程选择已签名 V72，不恢复玩家数据库。未随包提供的原始交付证据由维护者核私有原件。
