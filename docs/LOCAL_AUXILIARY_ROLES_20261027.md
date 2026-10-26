# LOCAL 已选子角色的辅助快路

Issue #565。补查证实，`Application.account` 是根账号，`for_character` 为非默认角色创建并缓存子 `LocalAccount`。#562 的第一版守卫对对象直接相等的要求过严，合法子角色仍走慢链；没有放宽准入或错误写数据。

仅 LOCAL `performance.local_auxiliary_noop` 接受根账号真实持有的当前子角色：root 同一对象、当前 UID 的缓存对象相同、Characters 同一读者、account_id/store 路径相同、store UID 相同，原活会话/报文形状/阶段/唯一游戏连接约束继续生效。外来根、移除的缓存对象、释放或 UID 不符仍走原校验。

真实 LocalAccount/Characters 工厂的正反测试先在旧候选复现一项错误，再在新候选通过。新配置为 `channels/server-risk-current-local-roles-20261027-v3.json`；online profile 与已冻结七叶包逐字节一致，LOCAL 只替换这一个 helper。旧冻结 LOCAL 候选不覆盖，以独立 addendum 在首次安装前选择新候选；发布事实另看最终回执。
