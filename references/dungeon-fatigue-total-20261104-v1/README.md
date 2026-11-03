# 副本疲劳整图总额修复

原生明确疲劳字段原先在每个关卡/子分段加载时扣整图数值。现在为91个收费入口按整图总量分摊，每个run/owner/stage只扣一次；例如35600三关16+16+16合计1%，子分段及重访不再多扣。

260个CoboDex页面逐项核对，223个收费入口整图总额一致；132个已正确补缺规则、37个现有免扣及19药水保持。两个原始运行叶的精确SHA见source-contract.json，来源及自审见website-audit.json和review.md。仓库继续使用既有运行源码归档模式，根引擎与历史冻结不被整树覆盖；提交不会自动安装。

双端规则/610关卡、真实SQLite回滚/幂等/冷读和实际Application/TLS单人、组队测试均通过。上线使用届时精确父版独立执行；安装结果与Git合入分别登记。未声称自然GUI或战斗通过。

无运行依赖的源码检查：`python tools/verify_dungeon_fatigue_totals_20261104.py`。

持有匹配的完整私有父运行包时，可设置`ELS_FATIGUE_TEST_PARENT`、`ELS_FATIGUE_TEST_TEMP`（ELS作者环境须在G盘），运行本目录verification/verify_rules.py及verification/verify_tls.py。隔离库与连接会自动清理；不使用玩家库或生产凭据。
