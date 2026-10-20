# 固定进度页的当前快照增量入口

历史builder的`--build-only`判断位于历史断言和读数替身之后，不能用于安全增量更新。维护工具在原builder最前加显式入口，匹配参数时提前退出；原历史正文逐字节保持，默认历史路径没有被重写或自动运行。

源码位于`tools/progress/reviewed_card_update.py`和7行`build_dashboard_entry.py.txt`。维护者先核原builder SHA及源码审阅，将helper放到固定builder同目录并将入口加在最前。完整历史builder、私有输入/证据、玩家库和发布凭据不属于本仓库。本工具不属于游戏运行包，也不计为游戏功能完成。

通过固定builder调用`--reviewed-card-update <事实JSON> --facts-sha256 <审阅SHA> --incremental-output <全新自有analysis目录>`；按需要显式指定`--dashboard-source`。缺参数或SHA变化直接失败，不回退执行历史链。默认只生成隔离预览，不写共享文件、联网或发布。

工具核当前JSON与原HTML嵌入及模板一致，固定来源SHA、真实安装完成回执、当前本地指针及manifest；只允许boxes/quests文案和追加证据，以及本地版本、两个本地SHA字段、业务文件数、更新时间。短摘要不超64字且remaining UTF8SHA同步；整卡分数、items、其他卡和线上/启动器状态保持。

本轮隔离输出与独立审查通过：原四项已安装本地并通过122秒观察；77110只完成验证及Git合并，尚未安装。额外score、65字短文和online元数据越界被拒绝。真实发布由维护者另外核来源SHA、备份后应用三份数据文件，再复用既有公开导出和固定网页发布器。

后续同一入口允许boxes、quests、sockets及special-socket的非空子集，仍只更新本轮实际传入卡片的文案/追加证据；其他卡片完整保持。原有两卡事实和五个本地元数据字段兼容，分数/分项保护没有放宽。
