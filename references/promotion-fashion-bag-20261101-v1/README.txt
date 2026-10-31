职业时装箱奖励误入冰装背包的修复源码归档。

三个箱子读表错误把原生普通时装group7改成冰装group27。现在共同沿用原生flags8的0x100区分，恢复普通时装入group7，并保留真正冰装。旧错放实例在角色初始化的同一事务中只改背包和槽位；保留UID、实例子表、已穿戴物品与历史回执，容量不足完整回滚。

delta保存线上7个精确业务源码，local-delta保存保留LOCAL差异的inventory_items.py；其余6个文件两端一致。source.patch用于在实际父版选择性整合。主干缺少当前职业箱和初始化优化前置，因此本PR只按现有references方式归档，不整树替换根目录实现；相关职业箱归档见PR691。

5项定向隔离Application/事务测试已通过，包含5种箱子开箱、入包、穿脱、冷读、重试、旧物品迁移和失败回滚。test_fashion_bag.py依赖维护者保存的完整匹配runtime，不把仓库source-check冒称这些业务测试。原始游戏资源、运行库、玩家库及原始流量均不随包。

安装状态及实际公网范围以installation-summary.json与public-acceptance.json为准；缺失表示尚未双端核收。自然GUI和玩家实战未验。原EXE/KOM与客户端支持文件未修改，Git提交不自动合并主干。
