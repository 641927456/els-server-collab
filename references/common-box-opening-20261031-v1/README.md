# 常用箱子补漏修复（隔离候选，尚未安装）

新增修复76个模板、15组消费者；完整ID和名称见 `audit.json`。继承上一批11箱修复及723618“空精灵石、未扩孔”的人类决定。实际玩家端尚未安装，也没有自然GUI实测。

修复普通背包196请求将单次Count1误当选项拒绝的问题，继续支持历史Count0；负数和Count2以上仍拒绝。未统一改协议解析器，冰机、疲劳药及装备操作保留各自语义。
成长装备、时装、称号、扩包、饰品的现有注册改由 owned_growth_items 独立安装，不创建活动报名、日历或自动发奖。723680补齐本身的物品注册。
启航723612和称号支援723673沿原事务签发已有_RaidSource，只准本箱扣除后的完整既定奖励计划；723618/723610的通用发放仍关闭。共享工厂为获准的保留物品生成合法读取类型，并按已有原生读取上限分堆；连续开启启航得到两件不同UID、count1的神物箱。没有改变奖励、属性、概率、池或活动产出。

| 消费者组 | 数量 | ID |
| --- | ---: | --- |
| boosting_2026_fashion_rewards | 3 | 721780, 723613, 723614 |
| boosting_2026_participation_gear | 1 | 723680 |
| boosting_2026_force_rewards | 3 | 723616, 720746, 723617 |
| boosting_2026_accessories | 3 | 723615, 721785, 721786 |
| boosting_2026_nested_capacity | 1 | 721788 |
| boosting_2026_title_rewards | 1 | 723673 |
| published_2026_bundles | 1 | 723612 |
| wardrobe_ticket_box | 1 | 715036 |
| potion_choice_box | 1 | 303673 |
| teacher_elixir_boxes | 2 | 715920, 718310 |
| white_armor_boxes | 1 | 118655 |
| furniture_boxes | 1 | 136039 |
| cartridge_selection_box | 1 | 119335 |
| raid_reward_actions | 30 | 30615, 30616, 30617, 30874, 30875, 30876, 118182, 118183, 118184, 118256, 118257, 135902, 136051, 136052, 136053, 136054, 136087, 136106, 136107, 136108, 136117, 136118, 136172, 136173, 136175, 136176, 136177, 136178, 136179, 136180 |
| black_market_box_rules | 26 | 62270, 62271, 62272, 62273, 62274, 62275, 62276, 62277, 62278, 62279, 62280, 62281, 62282, 62283, 62284, 62285, 62286, 62287, 119215, 119333, 119334, 119336, 119337, 119338, 119339, 119340 |

验证：
- `python test_common.py`：最终76/76通过。实际Application所属LocalSession、受控城镇/99级职业150、G盘独立SQLite、合成已持有道具。每模板预览、Count1、拒绝负数及批量、回执奖励与实际库存一致、重复无增量、冷读；每组代表另测Count0及事务末端编码故障回滚。
- `python test_boundaries.py`：原始3例中通用发放/错误身份/无扣箱来源与父箱→两件神物箱→十件神物装备及称号材料分堆/冷读两例已通过。剩余容量/锁定/跨角色一例修正测试的周期初始化前提后单独重跑通过，见 boundary-result.json（tests=1）；不把该次单例说成重跑全部3例。
- `python check_startup.py`：真实Application.start、无活动工厂/活动报名表、9个缺失箱子注册齐全；已有活动奖励注册可再次安装而不冲突。
- `python verify_native.py`：15组代表的55A/AD8/197由固定SHA客户端原始代码离线完整读取通过。native-inputs均为自有合成回包，不是玩家抓包。未操作游戏进程。
- 上一批11箱的5项相关业务回归在最终共享工厂上重跑通过，见 inherited-regression.json。其他未变的历史证据沿用。21个修改Python文件语法编译通过。

初次故障保留在任务目录：`tests-first.json`、`tests-second.json`、`tests-third.json`、`tests-before-shared-factory.json`。问题包括故障注入没有替换已绑定的encoder、夹具城镇缓存未同步、独立启动注册/保留物品发放及堆叠缺陷。最终76项测试对应修正后的完整共享代码。startup测试曾未显式close自己的SQLite连接导致临时目录清理失败，已修正；native测试曾被旧工具sys.path抢先导入根代码，已固定先导入候选。失败不作为成功复用。

来源与交付：
- 正式父版 `local-cobo-guidebook-upload-20261031-v1`，manifest SHA256 `b653342071444ffe46837685187e5cc3d3ba8a24229f4360f5fc488641f218a0`。测试使用其1375个业务文件，加上一批候选与本轮精确叶文件。
- `candidate.json` 是相对该正式父版的组合文件清单（包含上一批候选依赖）；`delta.json` 是相对上一批11箱候选的21文件增量。SHA逐项核对后整合，不能整目录覆盖旧Git根代码或较新的运行版本。`qualified-runtime.json` 绑定实际测试的全部业务输入。
- 源码在 `source/<SHA256>/文件名`；parent-relative-code.patch只便于评阅。测试默认运行时是脚本同目录runtime；另设 ELS_COMMON_BOX_RUNTIME 指向重建后的候选。test_common.py复用上一批test_boxes.py，路径可由 ELS_COMMON_BOX_FIXTURE 指定；verify_native.py复用G:/els/tools的原生离线读取器。
- 本轮没有提交PR、合并或发布，没有改玩家/账号库、EXE/KOM、启动器。指定发布负责人按现有流程选择性整合，并核实际运行结果后收口。
- 136186旧有限候选集合仍未批准；不猜补未核实的箱子奖励池。本次结论限定于列明的76模板，不声称全客户端所有历史箱子已实现。

收口时current已前进到 local-public-controller-retirements-20261031-v1。完整manifest核验后，本候选27叶的父SHA仍全部一致；额外两项public/story controller retirement与本轮开箱路径无关，应原样保留，见current-parent-compatibility.json。测试基线仍如上记录，不宣称对新版全目录重跑。
