# 双端正式服务端源码基线

Issue #555。来源为已交付 Clock 父版：online `b302076617bf11a8c69cb0162519e673ad0c1bb91d2ec626b639c0123e3e2a72`，LOCAL `bc3fd813957f16aa6d1298f0825e50c05ac2b5cb947f556398d94fcfa1921dc0`。这是当前运行代码的可重建索引，不能用主干根目录直接覆盖正式服。

`channels/formal-clock-20261027-v1.json` 逐文件绑定已有 Git 源，缺失的当前版本保存在内容寻址的 `references/formal-clock-source-20261027-v1`。不改变既有归档，不把 root 新提案混入正式调用链。两个通道分别保留配置模式、联网租约、LOCAL 业务差异及已交付疲劳、随机任务、药水、交易所、角色和原力链。同步主干未来改动必须显式更新索引和验证，不会自动进入此冻结父版。

范围为完整 `els_server`、业务 JSON 规则及所需锁定静态资源；没有宿主配置、证书、任务、Python、账号/玩家库、客户端、运行日志或启动器打包。本地原生 V38 启动器及原 Web 管理页面继续分别按已有交付管理。对部署仍需在真实新父上审查、备份、排空和独立验收。

默认入口现由 `channels/current-engine.json` 选择实际已验收的双端配置；当前是保留票券/角色刷新父的七叶性能修复，LOCAL 包含已选子角色补充。实际正式清单 SHA 随选择文件绑定，宿主配置和玩家数据不包含在内。下列命令验证默认当前选择，不需要生产凭据：

```powershell
python -B tools/materialize_formal_runtime.py --channel online --verify-only
python -B tools/materialize_formal_runtime.py --channel local --verify-only
```

建立新目录中的源视图（不替换当前 checkout）：

```powershell
python -B tools/materialize_formal_runtime.py --channel local --output G:/work/els-local-engine
```

源视图缺少的静态资源在回执中明确标注；准备好已有锁定资源后，可添加 `--assets-root <已验证资源根>` 完整物化。默认复制资源；同卷一次性 QA 可显式使用 `--link-assets`，链接资源不得修改，验后删除该临时视图。工具校验完整输入后才创建输出，拒绝已有输出、路径穿越、大小写重复、Windows 别名、源越界、未知或篡改资源。

历史 Clock 配置仍可显式使用 `--manifest channels/formal-clock-20261027-v1.json`；不修改旧冻结源。后续正式发布必须根据实际新父组合并核全 SHA，再更新当前选择；不能仅更新 Git 后自动假定服务器已采用该修改。

来源清单与完整当前源可重建，解决的是此前“归档合入但无法组合重建”的风险。历史自然界面、战斗伤害和多人延迟的未验边界继续保留；不据索引或 Git CI 外推功能全部验收。
