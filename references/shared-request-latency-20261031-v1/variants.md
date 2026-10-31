# 公共重工作顺序的同根因变体

2026-10-31，Issue #647。种子问题：已经判定不需要业务处理的7D0，仍经过外层活动持久化/通知。违反的约束是“无业务或不属于当前消费者的输入，应在完整状态投影之前退出”。本轮不推断历史6秒尖峰的具体主因。

## 搜索与范围

搜索先覆盖仓库的完整源码/引用目录，再按已核双端清单区分实际输入与不可改写的历史副本。实际语法扫描覆盖所选engine的整个els_server，而非只搜storage。14个候选全部沿调用者核对；两端消费者源码一致，Application保留模式差异。

| 搜索 | 结果 | 处理 |
| --- | --- | --- |
| 精确匹配 `observed=isinstance(session,LocalSession)` | 所选双端各1个公共worker；引用目录另有历史副本 | 已知阳性；历史副本按来源排除，保持不改 |
| 扩展到 `periodic_notifications` 的 `next_periodic` 门槛 | 1个共用周期入口 | 确认外层未使用已有一秒门槛 |
| 仅搜 `load_items(db` | 138个文件，正常读取占多数 | 过宽，停止在此层继续扩展 |
| AST：完整状态读取位于 `return None` 之前 | 14个函数 | 11个真实变体，3个已有调用端类别预检 |

## 确认并修复

以下严重度均为P2（公共延迟/无关状态读取），置信度高；由隔离回归复现，未声称已在生产逐项观测。

| 位置 | 原问题与修复 |
| --- | --- |
| `Application` → `FriendsSession.periodic_notifications` | 内部活动门槛尚未到期，外层仍执行两次计时和通知。空闲轮询现在只跳过这部分；原房间tick、鉴权和待发消息保留，有消息时仍通知 |
| `storage/boosting_2026_nested_capacity.use_ticket` | 先完整读背包再识别扩展券；改为归属UID模板预检，旧effect回执仍进入原流程 |
| `storage/resonance_state.use_book` | 无关物品也完整读背包；旧回执分支保持在模板预检之前 |
| `storage/character_custom.use_book` | 无关书先完整读背包；类别或旧回执命中才加载，正式资格回调仍在原位置 |
| `storage/boosting_2026_force_inventory.use_book` | 无关道具先完整读背包；保留账号/角色和旧回执检查，识别后完整校验 |
| `storage/artifact_progression.action` | 无关219先读完整角色和背包；神物类别或精确回执命中后才读取 |
| `storage/titles.use_item` | 无关道具先完整读背包；称号类别命中后才读取，已消耗来源的回执重放不依赖现存道具 |
| `storage/expansion_items.use_expansion_item` | 普通扩展券类别过滤晚于完整背包；先模板判定，原回执/扣券/扩展同事务保持 |
| `storage/skill_unlocks.use_skill_book` | 解封书类别过滤晚于完整背包；先模板判定，原解锁/回滚/通知保持 |
| `storage/boosting_2026_limited_pet.activate` | 其他宠物来源也完整读背包；保留已有领取回执，限时来源命中后才读 |
| `domain/pet_support_flow.handle` | 每个219先读完整背包并进入宠物writer；改为最小归属模板/回执预检，永久和限时回执均保留 |
| `storage/town_dialogue.interact` | 没有适用任务仍先构造完整角色；适用任务检查后才构造 |

共享 `inventory_state.owned_template` 只查询同一连接内的 `owner + uid`。不缓存状态，不替代命中后的完整校验，不改变类别池、来源、角色资格、原子扣发或幂等规则。

## 排除项

| 候选 | 严重度/结论 | 依据 |
| --- | --- | --- |
| `storage/fishing_vip.use` | 信息项，误报 | domain已按UID模板及回执预检 |
| `storage/housing_access.use` | 信息项，误报 | domain已有当前归属模板/回执预检 |
| `storage/resonance_page_expansion.perform` | 信息项，误报 | domain先识别指定模板或历史回执 |
| 活跃副本的38E状态 | 信息项，不按无业务包优化 | Lu/Ciel原生状态会持久化选择和同步，不可仅因没有普通ACK就跳过 |

## 回归与剩余边界

101次周期poll的房间tick仍执行101次，活动前后计时/通知从每poll一次改为只在两个到期点执行；中间待发消息和外部撤权测试保持。8类消费者分别验证无关/其他角色物品不读完整状态且无存档增量，匹配道具仍进入原校验。另验称号、扩展券、技能书、宠物的正常业务和回滚/重放/冷读。

CI回归入口是 `tools/verify_shared_request_latency.py --with-runtime`，不将纯语法模式当作业务证明。当前仍保留原SQLite事务和写锁；来源真实输入相同的旧成功结果复用。候选未选择、未发布，生产6秒尖峰是否消失仍需安装后按四段计时核收。
