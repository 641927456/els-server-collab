# 已交付商城补货 4121 项

本批补齐 3170 个礼包（3106 个时装礼包、64 个 Track2 粉丝礼包）及 951 件饰品，均为 50 ED；其中 ELSTAR2 缺失礼包 288 个。普通时装散件未扩充。79 个内容、角色或非固定发放尚未核定的礼包保留在 `held-packages.json`，没有上架。

Track2 按用户明确决定整包发该组合全部 3～5 件应援横幅、1 件光效和对应角色的 1 个舞蹈动作。礼物关系取自原生 `PACKAGE_ITEM_ID` 链接；84 本新增动作书沿用既有注册、应用和存档流程。293664、293665 两本书的原始职业字节与物品角色／CharCustomData 角色不符，使用既有逐书 `required_class` 归一化入口修正，两项精确绑定见合同。角色资格和普通购买入口沿用原实现。

`source-contract.json` 锁定已安装的九个差异文件、双渠道父版及最终资源 ZIP。唯一 Python 运行文件在 `source/common/els_server/domain/character_custom.py`，只更新准入计数和数据 SHA。完整配表及原生 DTO 证明留在私有离线资源包中；当前协作仓库公开，因此不上传该 ZIP。源码归档保留已交付版本，协作根引擎保持原基线。

`tools/` 保存实际使用的准备、准入、排序、业务与原生解析脚本。复现时将脚本放回 `G:/els/analysis/shop-unlisted-listing-20261104-v1/` 的隔离副本，使用合同指定父版、当时 `update-binding.json`、初始审计 `analysis/shop-unlisted-check-20261104-v1/remaining-online.json` 及私有原始表／离线原生解析器。按已固定的父版 rollup 清单准备独立 candidate，再执行 `build_catalog.py`、`build_order.py`、`verify_new_bodies.py`；`verify_business.py` 的模式为 packages、accessories、books、boundaries、capacity、native。`prepare.py` 是当时读取 current 的原执行记录，不能对今天的 current 直接重跑来复现旧父版。这里记录原执行入口，不授权从当前安装目录重新生成、覆盖或发布。独立业务运行时还需要候选当前运行依赖；单独拉取本归档不能启动服务。

`validation-summary.json` 复用已成功的 3170 包、951 饰品、84 本书和全角色资格／事务／原生解析验证。初次边界脚本在已完成六项检查后，填包夹具超过 36 项发放上限；分批填充夹具后只重跑容量及后续检查。新增原生 DTO 案例 16319 项，最终 60081 项未变证明直接复用。公网三笔实际购买扣 150 ED，注册／应用和重新认证冷读通过，摘要移除了账号与角色身份。

`installation-summary.json` 分开记录线上、本地及启动器验收。线上已安装 `shop-unlisted-4121-20261104-v1`，本地已安装 `local-shop-unlisted-4121-20261104-v1`；现有 V75 启动器真实选版及全部组件 SHA 验证通过。普通玩家下一次正常本地启动会选中新版。线上／本地总目录 19640／19639 的一项差异继承自原渠道。自然 GUI、多人实战尚未验证。

源码／附件完整性核对：`python -B references/shop-unlisted-listing-20261104-v1/verify_archive.py`；拥有私有资源包时追加 `--payload <ZIP>`，将核对其 SHA、大小、全部九个成员及每项内容哈希。此核对不重复业务测试，也不连接玩家库。

本 PR 关联 Issue #834，只做 Git 来源归档；主干是否合并与上述实际安装状态分别记录。需要暂停时只停止本批新购，保留已存自定义 ID 读入与事务回执；不恢复玩家或账号数据库。
