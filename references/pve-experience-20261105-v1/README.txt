Issue #858 — 逐怪与阶段经验运行候选

这是已验证的运行版九叶差异归档，不替换仓库根目录开发引擎，不改变 channels/current-engine.json，也不代表正式安装。
源父版 native-unified-ip-page2-20261104-v2；提交前已核线上 native-dungeon-workers-prewarm-20261105-v1，九叶父SHA全部一致，可保留其余17叶副本工作线程优化。

159个普通副本配置、245条有据map/template。没有直接来源的值按用户明确授权，采用同区域/同类/副本定位估算，数据内保留provenance。社区表整本总数是击杀基础和，不是额外通关额。
普通额外通关仍采用本服float32的30%；已有共鸣10倍、未99级全局20倍补助和普通Hot Time2倍均由原入口处理。
Rosso/Berthe的15个模式、45阶段按模式无关来源值结算，不把阶段金额再乘旧phase100，也不按每个部位发一次。其他团本、隐藏和专用资格保留原规则。

原始候选验证：普通SQLite11项、团本阶段SQL/上下文9项；实际Application/TLS肖像单人、水龙双人完整通关，含重放与失败回滚。普通入口无额外效果时肖像累计ERP160842500；水龙每人14411480。
团本本批未运行Application/TLS；自然GUI/实战和正式加载未验。测试夹具问题与未归因额外奖励保存在evidence/failure-history.json，未用于拟合表值。

高GM与其他加成可能超过原生AF主经验i32界限；现按原明确错误整笔回滚，不截断到账或假设分包。GM100×肖像首领×共鸣10倍的拒绝/回滚已验证。

来源：https://drive.google.com/file/d/1H7iqN_faRSyEWx5BbKsLz3Ex7qiKKtsB/view （玩家实测表2025-10-31，非官方原始配置）
帖子：https://gall.dcinside.com/mgallery/board/view/?id=els&no=2023980
Source CI：python -B tools/verify_pve_experience_source_20261105.py
业务复现需维护者锁定的运行资源，入口及完整逐图表在 G:/els/analysis/pve-exp-reference-20261105-v1。未附运行库、账号、玩家库、凭据或原始日志。

发布负责人仅选择source-contract.json中的九个path/source及冻结SHA，按实际新父版核定，不用本归档覆盖整树。提交与安装分开记录。
