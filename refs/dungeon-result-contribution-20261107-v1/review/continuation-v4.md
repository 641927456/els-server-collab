# 副本结算与 TAB 统计续审

审查对象为已交付 V90、Git `06cab5a50ab374318b9568f0e0c91b9f1647e1e6`。这是本会话自查，不是独立审核，也不代表 GitHub 审批或主干合并。

## 结论

本轮未发现新的可复现产品缺陷，产品源码改动 0。保留已交付的本服贡献／评级／MVP／一次奖金规则；没有重装服务或发布新启动器。新增针对报文交错、封存和共鸣经验上限的验证全部通过。

| 严重度 | 新确认问题数 |
| --- | ---: |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

审查范围内剩余风险低；建议保留 V90。结论限于下述代码、协议和原生读取范围，不能表述为人工自然实战完全验收。

## 固定输入与变更范围

实际线上快照 `native-dungeon-contribution-20261107-v1`，本地 `unified-server-8794e4c073f156ac-b5c3439c1674`，启动器 V90；11 份受审源码与已提交副本逐 SHA 一致。差异父版是 `native-writer-checkpoints-20261107-v1`，398 行统一差异已留在本地分析证据。逐文件增删量、调用位置和完整 SHA 见同目录 `review-summary.json` 与上级 `source-bindings.json`。

| 文件（els_server/ 下） | 审查重点 |
| --- | --- |
| data/dungeon_result_rules.json | 明确本服来源、固定权重／阈值／10%上限 |
| domain/dungeon_result_rules.py | 入场属性归属、本人数据、精确份额、MVP、平分、缓存代次 |
| domain/dungeon_result_stats.py | 合法9E、当前代次、CD按recipient归属、C1封存和投影 |
| storage/reward_state.py | 权威clear限定、同事务支付、上限、历史回执、原生预提交编码 |
| domain/dungeon_flow.py | 普通／团本原clear writer及原会话shadow绑定 |
| domain/dungeon_settlement_commands.py | El Tree原clear入口、typed assessment与回执 |
| domain/dungeon_equipment_loot_flow.py | 有限装备地图沿共享奖励writer接入 |
| domain/secret_clear_rewards.py | 秘密副本配额、原事务和个人归属 |
| domain/silver_mirror_flow.py | 镜像完成与奖励事务边界 |
| domain/local_session.py | 普通准入冻结装备基准 |
| domain/event_admission.py | 票券准入的单人名单与装备基准 |

同时追读 parser、请求分派、Application worker、组队准入／BB barrier、普通与团本共享writer、组队挑战结算、首次剧情过渡、ERP与称号效果等直接依赖。没有把未变大文件的所有无关系统算作本轮全量审查。

## 历史与删除分析

- `997f64b3` 引入原生统计链，`08226589` 增补唯一最高值奖项，`4628cdf1` 加入本服评分与奖金，`06cab5a5` 记录 V90 交付。
- `git blame 08226589` 核定被删除的 `known_awards` 原用于原版公式未还原时的显示推断。其旧“必须全员报告、只认唯一最高值”限制被明确授权的本服平分／缺报告语义替代；新奖项进入权威writer并固化至回执，未删除身份、通关或事务校验。
- 部分运行父版来自非 Git 发布快照，只能按冻结 SHA 对比；不虚构这些快照的 Git 历史。

## 关键检查与反证

1. **报文归属**：`dungeon_result_stats.py:19` 拒绝非当前合法加载角色／无有效lease的9E；`pvp_play_messages.py:21` 完整解析有界、排序、有限非负统计。原生多UID映射只取当前本人UID，观察者副本不相加。PVE1按受益者报告归还来源CD，拒绝本人和匿名来源。
2. **报文时序**：`friends_dungeon.py:553` 的 `end_part` 等待全员BB。每个连接的9E／BB按序处理，跨连接报文交错不会让第一人提前结算。真实两人TLS补验采用“甲9E→甲BB→乙9E→乙BB”，三个分段均成功，甲BB后全员尚未clear。
3. **封存**：`dungeon_result_stats.py:40` 在clear后确认交付但不替换已封存报告。补验改为完全不同的巨额伤害报告，统计对象、回执及余额均保持第一次结果。
4. **缓存代次**：`dungeon_result_rules.py:105` 以epoch、名单、stage/part与报告序列缓存，未提交失败后的新有效报告可刷新。普通和团本shadow均携带原会话；组队挑战writer直接使用真实成员，未发现shadow漏绑。
5. **奖励**：`reward_state.py:107` 仅接收匹配角色／run／地图的typed assessment，并要求clear来源。奖金不以报告数值为倍率，最多是这次既定结算的10%，多奖不叠加；没有9E单独授予通关或经济奖励的路径。
6. **事务和回放**：原SQL事务预编码C1后才写余额与回执，整组失败会回滚。grant_json身份未改变，旧回执不补奖，新回执重放不重算；复用已通过的冷读、旧读者与整组回滚证据。
7. **共鸣经验**：新增五种真实存储与原生C1读取场景，普通EXP均保持满级原值，ERP只入账号共鸣余额，重复请求无增量，见下表。
8. **原生显示**：C1标量、MVP／三奖与TAB13值未变，复用同SHA下已通过的原客户端无遮挡C／SS及队友MVP画面，不重跑未变界面。

## 新增验证与复用结果

| ERP距上限剩余 | 本次有效ERP | 获奖奖金实际ERP | 重放 |
| --- | ---: | ---: | --- |
| 不裁剪 | 550 | 50 | 无增量 |
| 510 | 510 | 10 | 无增量 |
| 500 | 500 | 0 | 无增量 |
| 499 | 499 | 0 | 无增量 |
| 0 | 0 | 0 | 无增量 |

上述基数为50、既有共鸣倍率10、一次10%奖金，C1以原DA64C0消费者交叉读取；实际称号／装备效果入口保持启用，测试角色无额外经济效果。所有场景ED均为132，普通经验不变。

新增真实双人TLS用原认证、邀请、共享准入、三个分段和原通关writer，核到C／SS、24.98／75.01贡献、MVP、一次奖金及冷读；没有强改room／run／clear标志。死亡与统计是明确协议夹具，不能冒称自然战斗。五个成功ERP夹具已即时删除，服务和三个自有Job均已结束。

复用上一轮26项原生／数学／事务检查、1170组职业装备基准检查和双端实际运行核收。没有计算或宣称代码行覆盖率。新增测试前两次在正常业务断言之前因夹具未初始化location、inventory表失败；只修夹具初始化，原失败证据保留，未因此修改产品代码。

## 调用影响范围

AST按显式import别名及本模块调用计数，不把文本命中当调用；不含动态反射。

| 函数 | 直接调用点数 | 实际影响 |
| --- | ---: | --- |
| admission_power | 2 | 普通／票券准入，共享准入复用前者 |
| prepare_clear | 5 | 五类权威完整通关writer |
| assess | 1 | 结算计划缓存更新 |
| result_payload | 1 | RewardState预提交响应 |
| report | 1 | 原副本9E分派 |
| current_statistics | 3 | 评分、投影和CD归属 |
| cooldown_payloads | 3 | 报告预检、评分、封存 |
| seal | 2 | 投影与worker完成 |
| project | 1 | 完成消息投影 |
| finalize | 1 | Application共享worker |

## 信任边界、范围限制与建议

威胁模型是已认证普通玩家，可控制自己的合法9E内容和请求顺序。不能由报告选择run UUID、跨角色授奖或绕过原死亡／阶段／writer来制造奖励。客户端统计仍是客户端报告，代码不能证明其伤害真实性；固定10%限制经济放大，但本次不新增服务端战斗模拟或反作弊系统。

首次剧情的 `first_story_entry.py:323` 是原有零ED／EXP教学过渡C1，不是这五个普通有奖通关writer；本轮核对了该分派差异，没有无依据给教学过渡新增经济规则，也未宣称其人工自然GUI重新验收。人工自然GUI和非零CD自然多人实战仍未验；完整原版CP也仍未恢复，本服采用已批准的入场装备属性基准。

没有新增阻塞修复项。建议保持已验证V90；若后续出现实际截图、报文或结算差异，应按对应入口复现后修复，不因本轮“未发现问题”否定新证据。

## 收尾

本轮四个新自有临时目录（两次失败ERP夹具及TLS私有文件／日志）的删除被自动审批以`blocked by policy`拒绝，0删除，未换方式绕过。既往受阻目标未重试。详细范围留本地`cleanup.json`；不将账号库、凭据、原始日志或抓包提交Git。已发布服务、玩家存档和发布锁未改动。
