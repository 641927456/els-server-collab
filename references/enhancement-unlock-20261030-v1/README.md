# 强化解锁效果修复候选

Deemo1四件+11赤血魔影防具的强化等级正常，但服务端没有生成EIST_UNLOCK_ENCHANT（组3），原版实例的强化解锁向量为空。现在统一item_body按已核资源映射和当前强化等级生成组3。旧存档、换装、强化ACK和重登共用这一入口；降级或损坏后的数据也重新派生，不修改玩家库存或增加状态表。

599个模板与10个规则组直接来自本目录两份已解码原生资源。它们只恢复已有物品的效果输入，不开放新获取入口。599不是已逐件实战验收数量。组3不作为用户镶嵌输入或持久化选项开放，原验证拒绝保持；炼制组13、影子组25等继续使用原通道。

国服官网赤血魔影说明（四件合计）：+10给BOSS伤害+20%，+11适应力+4%，与当前资源每件43510/+5%和99266/+1%一致。死龙136186没有固定强化解锁效果，应保持组3为空；其效果变换池不在本次范围。

来源：

- https://els.ztgame.com/game/000-1641-0032d-522387.shtml?ms=805&mt=813 （赤血魔影，持续更新的系统指南，2026-10-31查询）
- https://els.ztgame.com/game/00a-1742-003e3-537032.shtml?ms=805&mt=995 （死龙，持续更新的系统指南，2026-10-30/31查询）
- UnlockSocketItem.lua及UnlockSocketItemData.lua；EXE SHA6c6b5180…、data036.kom SHA56bb739e…；来源SHA在数据目录中锁定。

修复基于main 13fe9de。根els_server中的8行差异用于协作源码；正式双端分别使用candidate.json指向的父版文件与候选，不得用根目录旧实现覆盖正式文件。双端各3叶：inventory_items.py、enhancement_unlock.py、enhancement_unlock.json。current及已验历史profile均未修改。

验证见validation.json和native-verification.json：19项直接相关断言测试成功，42个候选报文经原版D9A550/7EBC80/7EB0D0解码与重建成功。未执行自然GUI、Actor最终属性或实战。旧测试中的7项失败已在未改父版复现，保留为旧测试与现有会话预览/强化规则不一致，未改这些断言或资格。

候选需由项目指定负责人按docs/release-flow.md选择性整合、审批和发布。当前未合main、未安装双端、未更换启动器组件、未取得新的发布权限；不得报告Deemo1线上已恢复。
