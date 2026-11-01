# 娜薇／诺亚剧情退场卡关修复

角色已能正常进入副本，但原接收器仍要求持有可选史诗任务，导致原生剧情控制器的255退场被拒绝。
本次归档已安装的public_controller_rules.py，增加11条精确来源规则，覆盖7张地图：

| 地图 | 来源（stage/part → template） |
| --- | --- |
| 34240 竹林之路 | 1/0 → 7407 |
| 34250 通往城池之路 | 0/1 → 7428 |
| 34260 领主之城 | 1/3 → 7449 |
| 34300 扭曲的记忆的隙间 | 0/1 → 7500；3/0 → 7502 |
| 34600 Moonlight Hill (Day) (Downhill) | 2/0 → 8025 |
| 34620 House of Rosso’s Laboratory | 0/0 → 8058；1/0 → 8059 |
| 34680 Titania’s Garden | 0/0、0/1、1/0 → 8142 |

单人和组队继续使用story_controller_retirements.rules_for的现有覆盖分派。只对这11个来源设置
quest_independent=True及requires_native_255=True；原135条公开规则逐内容保留。角色类别、
图谱／脚本SHA、源行、当前实例、初始HP、原生255报文、完整参与者、代次、任务writer、
回包预编码、幂等和结算保护保持。客户端仍负责原动画、计数、AI和退场触发。

消亡之海的26650是实际入场前置，未放宽；莉缇娅任务专属流程也保持。未添加计时器、
模拟死亡、自动跳关、奖励数值或客户端Hook。

## 验证

- 22个真实Application/SQLite隔离检查点（11处单人、11处双人）：原规则拒绝、候选接受、
  原关卡条件和推进、重复AE、退场本身无库存／余额／地面掉落增量。检查点为受控夹具，
  没有声称从自然入口打通全部前置房间或执行所有动态召唤波次。
- 原生离线：11个class103工厂前缀、22组完整DTO/readiness-map/255 writer通过。
- 实际公网自有娜薇从第一批怪推进到纳亚房，诺亚从34680首段进入下一段；重复报告只AE。
  独立SQLite冷读确认没有对应可选史诗任务，两个控制器各只有1条已提交事件。
- ONLINE观察124.22秒，LOCAL观察120秒；新LOCAL实际模块2项业务验证、原V59启动器
  ResolveLocal选择新目录和规则SHA已核。自有QA、临时任务和发布锁已清理。
- 自然GUI、动态波次及自然实战未验。原始客户端、运行库、报文、日志、玩家库和凭据
  不在此归档；私有原件由发布维护者核查，qualification.json仅保存脱敏结论。

纯源码／CI检查：

```text
python -B tools/check_controller_quest_gates.py
```

使用现有锁定运行资产重放App/SQLite检查（临时库仅写入指定scratch目录，并自动清理）：

```text
python -B references/controller-quest-gates-20261101-v1/verify_application.py --runtime <qualified-runtime-root> --scratch <owned-scratch-directory>
```

首次组队检查点漏同步静态代次，修正测试夹具后只重跑失败的组队位置。公网Noah读取器
曾误拒绝合法空计时段，修正后只续跑Noah，复用Laby成功结果。升级请求响应超时后只读
复用原已提交回执，没有重发经济请求；这些问题没有引入业务源码变化。

## Git及交付范围

已安装ONLINE `native-controller-quest-gates-20261101-v1`及LOCAL同名版本。本次Git同步
不重复部署，不改current-engine选择，不改旧channel或旧归档的字节与SHA。manifest.json
绑定精确安装增量；维护者应按其中path选择性整合，不能将整棵Git root源码覆盖运行端。

启动器EXE和签名分发载荷未重发；实际本机LOCAL已选择新版，不声称其他电脑旧签名缓存
包含本批增量。没有数据库迁移或玩家/账号库恢复。主干合并仍须精确head审批。

Git回归驱动移植后，两个组队场景曾把Application附带的定时活动列表同步2AF误判为重复死亡回包。
已只允许该明确独立通知，并继续断言退场响应只有AE、没有库存/余额/掉落增量且原死亡事实不变；
仅重跑两个失败场景，其他成功结果复用。生产规则源码未变。
