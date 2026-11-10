# 事务内另开背包/观察连接的同根审查

范围为实际V98的els_server，2026-11-07。P1可用性问题：当前线程持有SQLite读/写事务，又等待独立连接；独立写入提交或外部PENDING写入反向等待当前读事务。未观察到玩家数据损坏或授权绕过。

| 搜索 | 命中与判定 |
| --- | --- |
| 精确return ((info.st_dev,info.st_ino),observer.execute('PRAGMA data_version') | 1；物品缓存受控复现确认 |
| 泛化observer.execute('PRAGMA data_version')、再泛化整个服务端data_version | 4个位置，仅同一模块；停止扩展，不泛扫全部SQL |
| 原生get_inventory_snapshot调用，缩为同一With且之前有BEGIN的AST条件 | 2；Duels.invite、Weddings._deadline均需修复 |
| 对上述房间分派追一层实际调用者 | Wedding._join->_slot、417->saved_user_sync另2条真实同根路径 |

P1 confirmed：物品列表缓存观察版本等待环；切磋FullUser读事务包围独立修复提交；婚礼入场/离场的读事务及超时返回的写事务包围同类getter。原版分别有可控写者失败、实际5C6拒绝和88B SQLITE_BUSY证据；修复版本有相同输入正常结果与提交证据。均在共享入口或原生产者边界修复，没有添加重试或假成功。

其他data_version位置：_tracked_snapshot的普通入口位于该读连接BEGIN之前，不能单凭同形判为另一个已证缺陷；其元数据仅供已删除物品缓存使用，因此一并清除。_ReadScope.read前后两个版本查询不自行持有读事务；已追到的事务内FullUser调用者在本批修复，但未把所有潜在间接调用都声称为已证明安全。保留其他角色/整包缓存，没有凭形似整层禁用。该两处按信息项记录，不冒称额外已确认漏洞。

回归入口为test_inventory_reader_contention.py：保持真实原背包和独立读语义，在一个已确认PENDING的提交前读物品；原实现--baseline复现写者SQLITE_BUSY，新实现必须保持完整物品并让写者提交。同时覆盖嵌套独立读连接。该脚本可直接作为CI回归命令；不以只检查函数名消失的静态规则代替行为验证。另test_duel_reader_commit.py及test_wedding_reader_commit.py以真实App/TLS和独立写提交覆盖生产者路径。AST窄化结果在getter-transaction-variants.json，原失败保留。
