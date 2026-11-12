# 冰装分解差异审查

本服明确规则：每件合格冰装固定返还45个未鉴定艾尔结晶130047，不生成额外或随机奖励。本次两叶只扩展共享分解规则，仍由既有1C0入口和事务负责归属、场景、扣发、容量、回执及同步。

审查结论：未发现阻断采用的代码缺陷。候选ZIP和两份业务源码、全部交接证据SHA均匹配；当前root整合中原规则叶仍等于绑定的market父，新叶不存在，无合并冲突。保持候选源码原始CRLF/LF字节。未修改主会话候选或正式目录。

## 调用和风险

高风险点是物品换奖励。唯一生产规则直接调用者为storage/decomposition.py；其两个直接生产调用入口是white_chip_decomposition_flow.handle（当前LocalSession优先分派）及其后既有LocalSession后备分派。inventory_items只调用reward_definition构建普通结晶定义；新130047奖励定义仍精确核原生记录SHA及既有group4/999定义。

已核攻击路径：认证玩家提交他人物品UID、重复UID/旧操作重放、锁定/封印/期限/穿戴冰装、伪造普通时装/机器/宝箱、目标栏容量不足及编码失败。共享事务在BEGIN IMMEDIATE后读当前归属和实例，先quote整组，再同事务扣物、发奖、编码及提交；失败不留经济增量。原生客户端读者消费三个成功ACK的完整记录；11537模板现金价格成员查询只证明原生类别资格，不用于推导45奖励。未移除任何安全检查。

原父为无Git元数据的SHA冻结发行树，不能对其运行可信git blame；本审查使用精确父叶、交接patch和逐字节哈希，不将本地共享checkout历史当作发行来源。

## 验证复用和整合

原8场景的6项首次成功和2项夹具修正后的成功均复用，未抹掉首次失败。root共享依赖与原测试父的有效变化已核：decomposition增加公会副职XP转换；equipment_receipt_state仅增加其他kind，原1C0读者不变；inventory_items增加显式guild_bank容器及常量缓存，默认inventory资格不变；LocalSession新增公会/摄影棚生命周期。仅补跑实际抽取→开箱→handle→冷读/回放，以及普通装备/芯片/冰装混选两项，两项成功；实际加载当前依赖与原候选2叶，仍由原生22793A0读者解析成功。纯冰装不生成普通铁匠XP，普通701000分派保留。

没有新表、DDL、第三方依赖或客户端支持改动；无玩家库访问、原EXE/KOM改动或游戏进程操作。安装、自然GUI和多人画面未验，需发布负责人在实际选中组件后核收。此分支仅归档增量，不合main、不代替精确head审批；性能会话后续若改变上述有效依赖，应只补相应受影响检查。

## 重现

原测试脚本和结果在verification/original。verify_integrated.py依赖G:/els工具及根整合的test-full-source完整树，两份source叶必须覆盖到该隔离树，SQLite DLL使用该树固定版；本档案不是完整独立运行包。额外运行仅选test_draw_open_dispatch_and_cold_read与test_mixed_ordinary_chip_and_ice_keep_distinct_rewards，不要求重跑已复用8项。

关键位置：source/els_server/domain/decomposition_rules.py:23 奖励分派、:53 冰装quote接入；source/els_server/domain/ice_decomposition.py:14 类别集合、:20 资格及固定产出、:36 奖励读者。绑定父 storage/decomposition.py:20 权威事务、:34 当前回放、:49 整组quote、:71 扣物发奖、:91 编码和回执；当前white_chip_decomposition_flow.py:16 当前身份与:36共享事务调用。
