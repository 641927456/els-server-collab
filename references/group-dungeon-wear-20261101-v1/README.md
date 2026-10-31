# 组队副本换装与队友原生同步

普通组队副本内穿脱装备现在沿原库存事务提交，并同步队友Actor的装备实例与本人客户端计算的最终属性。服务端校验身份、资格、同房间与加载阶段、支持状态、实例和报告代次；回执重放不重扣、不重复广播。客户端沿已有原生装备消费者、计算与刷新，不修改原EXE/KOM。

`server/online`、`server/local`是相应实际父版上的4个完整增量文件；`support/common`为4个公共支持文件，模式各自profile见`support/profiles`。根目录协作运行树不整树替换。重建须使用安装回执所列精确父版，保留其余文件及LOCAL差异。

`launcher/source`包含V55到V56变化的C#及新增bootstrap资源，既有V55源码、原资源依赖由source-contract完整SHA清单固定；签名组件清单分别保留两模式差异。签名私钥、游戏/账号库、原始抓包、日志和游戏二进制均不随Git提供。

验证：双端Application/TLS事务、阶段拒绝、回滚、重放与冷读；自有基础职业和完整三转Eve164混合队伍各5轮原生验证；永久缓存故障与借用Event恢复8项实际函数体验证；独立审查；实际C# LOCAL升级、重复运行和typed存档保留。自然GUI、多玩家完整实战及未复现的概率性自身tooltip属性消失未因此宣称全部修复。最终guard/停用用例为函数体测试，原生故障注入未到触发点，未冒称通过。

可在仓库内运行 `node references/group-dungeon-wear-20261101-v1/validation/verify_lifecycle.js`。完整原生及隔离App证据由交付负责人保留，未随仓库提供。安装、公网核收、启动器交付与Git提交分别登记；见安装完成后写入的installation.json。
