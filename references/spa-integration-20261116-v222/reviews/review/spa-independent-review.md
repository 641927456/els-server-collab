# 温泉及红炎科宝候选独立审查

2026-11-16。两包均通过源码审查，六个文件适用于 V221 组合父版。逐一核对了 V219、V221 的原文件 SHA-256、候选冻结 SHA-256 与两份压缩包里的实际字节。两包文件互不重叠，四个 Python 文件可解析。复用作者的定向离线结果，未启动服务或客户端。 [校验清单](<G:/els/analysis/publisher-spa-integration-20261116-v222/review/spa-independent-review.json>)

## 红炎的境界与温泉科宝

- 1009 的原版场景 851、IsWarp 出生点 1601 和坐标 (-2475, 1600, 425) 一致。目的地沿原目录校验 99 级和完成任务 26640，计价沿既有第 20 组。六个有向组合共用原计价和通行证规则。已有相邻地图入口、持有 1009 存档的恢复与庆典返回入口仍各用原资格。 [场景来源](<G:/els/analysis/x2-village-opcode14-20261017-01a14a51/outputs/DLG_Map_Village.tables.json:5944>) · [准入来源](<G:/els/analysis/dungeon-chain-20261015/selection/resources/MapData.tables.json:1196>)
- 58C 层绑定当前账号、角色、活动及保存地点。在同一 SQL 事务中核目的地资格与余额，编码回执，保存扣费、坐标和操作回执。待入图时相同序号与载荷重发同一回执。对 1009 的新增 225 旗标 1 路径须核本会话已提交回执及目标存档，227 仍走现有入图。六路由、三个连续往返、三条未付费、三条缺 26640、十条越界方向及四条既有路线复用已通过结果。 [存储实现](<G:/els/analysis/spa-system-audit-20261111-v1/varnimyr-cobo-20261116-v1/source/els_server/storage/town_travel.py:11>) · [回执核对](<G:/els/analysis/publisher-gm-parity-20261116-v221/runtime/combined/els_server/domain/town_travel_flow.py:305>) · [点验结果](<G:/els/analysis/spa-system-audit-20261111-v1/varnimyr-cobo-20261116-v1/verification.json>)

## 温泉重登

- 28 初次选择的两条 2A 生产路径共用序列化，唯三处温泉转换到 1500→20000、1501→20008、1506→20013。2A 地图字段只编码地图、线路与进度，坐标由客户端入图确认。普通地点的投影按原值编码。225 新分支要求 28、6E9、5BF、32 已完成，尚无本次 227 或活动地图，且旗标为 0、目的地与保存温泉严格配对。冷登沿用角色租约，并核对当前保存行。 [2A 实现](<G:/els/analysis/spa-system-audit-20261111-v1/spa-relogin-20261116-v1/source/els_server/protocol/local_messages.py:240>) · [225 实现](<G:/els/analysis/spa-system-audit-20261111-v1/spa-relogin-20261116-v1/source/els_server/domain/fishing_village1500.py:93>)
- 28 和 225 不写地点。有效 227 检查场景就绪载荷、完整保存行、角色租约与本次过渡，再预编回复并提交新地点。原样重放须验证已提交地点，避免重复修改位置 revision。科宝过渡已存在时交由原 225/227 处理，三处温泉正常进出、原付费到达均沿各自路径。若付费到温泉后断线，已提交的地点仍是温泉，下一次冷登依此规则入配对村庄，费用按原付费提交时间保留。 [227 实现](<G:/els/analysis/spa-system-audit-20261111-v1/spa-relogin-20261116-v1/source/els_server/domain/fishing_village1500.py:110>)
- 复用了三处原选点函数的离线重放及到达测试，含错误村庄、错误旗标、错误身份封装、无效 227、同包重放及复读。普通路线复测覆盖 150 条科宝方向、75 条同会话转乘、三条一般门户和三组经 20010 的转乘。线上原问题记录缺 225 目的地和 226 结果，实际红炎科宝菜单与温泉冷重登仍待安装后核验。 [重登入场证据](<G:/els/analysis/spa-system-audit-20261111-v1/spa-relogin-20261116-v1/修复说明.md>)
