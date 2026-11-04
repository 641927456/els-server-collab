# 首笔拾取预加载修复审查

结论：可发布。仅修改 Application.start，在现有静态目录初始化中增加一次 el_search_effects.catalog()，共三行；经济数据读取、资格校验、比例计算和SQL入账路径未修改。

源父版：native-dungeon-business-isolation-20261104-v2。源码和SHA见candidate-manifest.json；运行快照不是Git工作树，使用固定SHA差异审查。这是当前聊天的自审，不是GitHub批准。

预加载位于prepare_character_catalogs之后、LocalAccount创建之前；因此SHA校验、大JSON解析及70,522条选项验证不会占用首次玩家奖励写事务。仅缓存原有不可变定义，不缓存玩家资格、加成、余额或回执。

成功验证：实际候选Application.start完成后、任何角色准入前，目录缓存已经就绪，首笔真实宠物金币拾取23.405ms，后两笔12.921/12.979ms；正常34710准入、真实NPC掉落、D0/D1/D2、冷余额一致。两个进程对照见此前profile-cold.json和profile-prewarm.json，不将本机时延冒称生产结果。

失败验证：静态目录验证抛出错误时，LocalAccount未被构造、玩家/账号库未创建，错误正常抛出；执行器和自有临时目录清理完成。初次失败测试工具遗漏TLS参数，已纠正，不是业务失败。

影响范围：Application.start这一现有公共启动入口；原有集成DX11模式执行一次，其他profile不新增依赖。外部资料、客户端、数据库结构、存档格式和玩家经济数值均无改动。无待处理阻断发现。

发布继续使用已验证的现有控制器、300秒启动就绪时限、双库备份、正常排空、至少120秒运行观察、首笔公网实际拾取与精确QA清理。自然GUI/实战和生产满负载仍未验。
