# 已交付双端源码整合

main 中的源码选择、开放 PR 与实际双端安装来源分散，本次从 `b063dcf` 整合已经交付的来源、测试和回执。默认仍选用 `native-skill-source-runtime-accepted-20261028-v1`，运行字节与 PR606 `eff17d5` 完全相同；本次不重新发布服务。

## 来源取舍

- PR589 的 28 个来源文件、PR596 的 21 个来源文件已经在 main，保留更新的工作流、CI 和版本索引。
- PR598 的五被动修复已由当前双端原字节保留。补齐其 22 个原始测试、归档与历史 profile，并将四项独立回归接回完整 CI；历史 profile 不替换当前选择。
- PR608/609 的 Master 刷新和三个原力边界文件由 PR606 来源保留；补回 PR608 最后收尾说明和回执。
- PR610 的 80 叶消耗品阶段及全部 LOCAL 差异保留。补回原始历史 accepted profile 和交付回执，不用旧选择覆盖后继来源。
- PR606 的 13 个已有文件和六个来源模块维持已交付范围。229 个完整属性研究文件继续只作 reference，当前两端 profile 选用其中零行；全部已有研究测试和核验门禁保留。完整属性、Actor 就绪及 106 实用联动仍未完成，`attribute_delivery_admission=false`。
- PR597 整树不采用。经限定审查采用的修复已经通过 PR600/601、603/604 进入 main，其余失败及未采用范围保留；Git 无文本冲突不代表业务合格。

恢复文件的原提交、SHA 和大小见 `references/accepted-dual-source-integration-20261028-v1/restored-original-files.json`。冻结来源保持原字节；`.gitattributes` 仅补相应历史 CRLF 声明。CI 原有门禁保留，不使用旧 PR 的整份脚本覆盖新检查。

## 当下安装核对

2026-10-28 的独立只读复核确认：线上 1293 个业务文件、本地 1318 个业务文件及完整 1771 个运行文件逐 SHA 与当前来源匹配。线上实际服务 ready/owned/running，本地已安装但当时未运行。原 EXE/KOM 和 V40 保持，current 指针前后未变。既有 120 秒以上观察来自原交付，本次只读核查没有重新进行发布观察。

脱敏摘要见 `references/accepted-dual-source-integration-20261028-v1/installed-verification.json`。本次未停服、安装、写玩家库、控制游戏或新增客户端 Hook；已包含相同运行字节，无需重复安装。

## 合并边界

源码整合、独立审批、main 合并和实际安装分别记录。main 仍要求独立审批并以 squash 合并；本次不修改规则、不使用管理员绕过、不把子代理审查冒充 GitHub 审批。旧 PR 先保持，待整合合并并确认覆盖后再按维护流程收口。

Refs #611。自然 GUI、全技能战斗和完整属性计算没有因本次源码整合新增验收结论。
