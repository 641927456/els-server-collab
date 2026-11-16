# V228 发布审查

在实际 V227 父版上冻结 10 个相关文件：服务端 2 个，签名客户端支持 8 个，其中 3 个为新增构建辅助文件。共享服务端保持同一套源码；客户端支持沿统一签名组件交付，不覆盖线上服务器遗留且不由该运行入口使用的客户端分析附件。

账号周任务接取的单一原生比较阻点已独立审查。原管理器查找、任务 ID/对象归属、账号属性、原请求生产者及响应等待均保留；仅在四项已实装普通账号周任务上改变该次比较的操作数。服务端任务容量修复保留角色任务 20 项上限及原等级、账号共享、周重置与奖励事务。

组合核验发现候选遗漏 native_support.py 的固定模板 SHA 和兼容性清单的绑定，已同步更新这两层，完整校验机制保留。实际兼容性选择器用现有游戏 EXE 离线通过全部 21 项依赖；旧清单仍被拒绝。候选原生分支重放、Frida 私有指令夹具、服务端资格/完成/领奖/共享检查复用同 SHA 结果；均不冒充自然游戏验收。

初始化完成阶段的退出/返回选角及广场确认阶段退出，复用既有关闭/选角处理和应用层清理。空请求、game 角色、其他阶段限制保持，V227 已交付行为保留。父版三项失败复现，候选正反向检查通过。

原生故障栈读取按页保留同一 2048 字节上限内的已读前缀；不增加挂点、原生调用、内存写入或修改异常处理结果。自动报告仅增加部分读取标识和读错误摘要，原始栈仍只留本地 trace。此项修复采集缺陷，不证明原五组游戏故障的根因已解决。

用户已授权本批周任务的既有本机自有客户端验证，安装完成后单独移交测试位并记录实际操作边界。发布本身不启动游戏，不恢复玩家数据，不绕过 Git 精确 head 合并审批。按用户新要求，正式停服前通过既有全服公告入口提前 5 分钟通知、1 分钟提醒，并核发送历史。


V229 integrates seven independently reviewed server files over actual V227. V228 was staged but never installed or stopped. Existing exact-input checks cover potion SQL/wire equality and rollback, FF26 actor/mailbox fallback, region admission, pickup stack/new UID/equipment/replay/rollback, and pet entitlement snapshots. Fixture timings are not production speed guarantees. No original EXE/KOM, database restore, reward probabilities, or damage formula changes. Natural party damage and lag remain pending player evidence.
