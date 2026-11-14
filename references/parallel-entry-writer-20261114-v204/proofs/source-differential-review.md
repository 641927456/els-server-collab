# V203 到 V204 候选整合差异复核

本记录为本会话自审；审查的是候选源码，不代表安装、容量通过或 Git 合并。精确六文件输入见 integration-review-source-bindings.json，线上组合输入见发布目录 online-composition.json。当前结论：已检查的六文件差异未发现新增的权限、重复发奖或事务原子性问题；实际安装后的持续容量验证仍待发布负责人完成。

## 父版与历史

实际线上父版为 account-gateway-power-scope-20261114-v203，清单 SHA256 为 9de43617627efec22d89c3add8efbb4f1a6b09f9ba6a3738bfe1503ceda89452，源码提交为 764a15cd15ba3e7ae08a91d62d7473939aacb4fa。共同服务端树与实际线上树分开比较。V203 publication/delivery-frozen.json 明确列出八项 online_only_overlay；不能用共同树替代实际线上树判断回退。

已在 collaboration/els-server-collab 只读检查历史。该提交根路径没有 dungeon_workers.py，根路径 gm_runtime.py 也不是当前部署源码；发布源码按 references/<release>/source 和 online-source 留档。本次不把旧根路径 blame 当成部署证据，使用固定父版文件、清单及发布留档比对，不切换或修改共享 checkout。

## 已解决的整合关注项

共同树没有线上 GM 批量发放与正式掉率管理增量。若直接覆盖线上，将丢失既有功能及在线批量发放的 actor 写入锁。该差异来自既有覆盖层，未发现已部署回退。发布负责人已完成线上三方合成：线上 gm_runtime.py SHA256 d28ffd7c52a8247d8c13ddd8d16749f6b0ab2e8bd1f10da80c5c9cb3538f1813，仅 players 方法 AST 变化；dungeon_workers.py SHA256 bb4480e0d3ee2813f07c8da5f30536309eadd69c57bed0cd5d3b3a6bd8e45059，原 gm_actor_access 批量写锁谓词 AST 不变。其他线上覆盖叶保留。

线上合成版 status-online-candidate/result.json 通过实际 TLS 验证，status 全字段和值一致，包含 formal_drops 与 batch_give_available；give 与在线 batch-give/preview 保留批量锁。忙碌的自有第二角色被人为持锁时，第一角色请求仍在 0.678ms 窗口内完成，父版需等到持锁结束，约 356.6ms。该数字为隔离因果验证，不是公网容量延迟。

## 风险路径与相关验证

1. companion_state.snapshot 与 pet_expedition.initialize 接入既有 write_transaction。前者 ensure_inventory 即使无显式更新仍会 INSERT OR IGNORE，父版因此绕过统一写入 FIFO。后者原有 BEGIN IMMEDIATE 同样绕过。只改变两处事务入口，不变更资格、第二次 guard、概率、编码或 SQL 语义；foreign_keys 设置仍在 BEGIN 前。12组父版/候选输出及完整 SQL 状态一致，五种异常事务全部回滚，后续独立线程仍能取得写入权。未知概率和玩家数据库均未改。

2. GM 只读旁路必须避免被伪装成发奖入口。dungeon_workers.py:265 的 gm_player_read 只接受准确 Runtime 类型、同一 Application、准确绑定方法，以及无参数 players 或单个准确 dict 的 status。Application 中四个引用分别负责分发、worker 调用、跳过无关 publish 与 scope；Runtime.players 有一个直接生产调用入口 Runtime.execute(status)。普通写管理方法不能经此旁路。测试覆盖子类、同名对象、其他 Application 拒绝，已释放角色排除与真实 GM give 成功。players 每行仍取得该 actor scope 并复核 playing 身份；它是逐角色快照，不再承诺全体同一时点。未移除管理 API 原有认证。

3. 共享目录可能造成跨账号污染。ChainGrowthBinding 有一个生产工厂调用；五份输入必须为准确 bytes，缓存键包含全部输入，公开加载器仍返回独立副本。唯一生产消费者 selected_2026_growth_runtime.py:156 将目录传给既有只读投影，未见目录写入。原角色 original、任务、时钟、活动资格对象保持独立。100次构造目录摘要相同，bundle 数量由100变1，改变任一原始输入仍拒绝。测试中的 Windows private bytes 含分配器波动，不把负增量解释为精确节省数值。

## 验证与边界

本会话两文件候选的三对交替实 TLS 测量中，18次首次初始化最大953.3ms降为484.4ms，重复初始化535.3ms降为244.3ms；2人与4人同副本用例通过，480条中继均收到。完整多人集成中的首次初始化仍出现508.0ms，不能声称全部请求低于500ms。

发布负责人对六文件新组合补充了实际 TLS 业务、线上合成 GM、2/4人队伍与签名组件相关验证，证据绑定见 source-acceptance.json。客户端字节未变的完整新进游戏结果按项目规则复用。V203 的20账号基线约29分钟连接超时，客户端最大请求超过3秒；保留该失败及早期监控缺口。它不算30分钟通过，也不能用局部日志尾部推断全程无慢请求。安装后的新版本20账号持续验证、当前运行文件哈希、双端交付及公网进度回读另行核收。

未改动原 EXE/KOM、玩家资料、概率、经济值或签名信任逻辑。本审查没有覆盖全仓库全部玩法，也没有完成20个原生 GUI 客户端或公网真实玩家战斗验收。
