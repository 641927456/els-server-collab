# V38 完整启动器源码归档

保留 V37 的界面与模式流程，增加随 EXE 固定的 local_updater.py：Git 拉取后自动检查、双 SQLite API 备份、三方合并、原子安装、120秒观察及代码优先恢复；保留账号、存档和较新的本地独立修复。

本目录完整保存已发布 V38 的全部 13 个 C# 单元、app.manifest 和公开签名运行成员清单。V38 另含 LocalInstall.cs 和原样内嵌的 Python 安装器。所有原始输入逐字节绑定原冻结 SHA，见 source-lock.json；历史 EXE、资格/预检/公网发布回执摘要见 release.json。已有验证按相同源码与资源复用，本次没有重跑安装或游戏测试。

运行载荷继续沿 V36，不复制 Python、客户端、载荷 ZIP 或静态二进制资产。原图和图标使用已有私有版本资源包，其 SHA 和两个成员见 build-assets.lock.json。下载及可选构建：

```powershell
gh release download launcher-v29 --repo 641927456/els-server-collab --pattern ELS-V29-Build-Assets.zip --dir .asset-cache
python launchers/friends-v38/build.py --check-only
python launchers/friends-v38/build.py --assets .asset-cache/ELS-V29-Build-Assets.zip --output <新文件.exe>
```

构建器保留原 .NET Framework x64 编译引用、manifest、图标和资源名称，自动核对全部输入摘要，拒绝覆盖输出。它不生成运行载荷、不签署发布元数据、不部署或修改正式指针；签名私钥仍由原维护端保管。PE 时间戳和编译环境可不同，不声称重建文件与历史 EXE 逐字节相同。本次只执行输入核验，未重建启动器。

本地和线上共用原生程序与共同启动入口，保留 DPAPI 密码保护、签名更新和原客户端资源摘要。V38 使用独立干净仓库的合格本地更新通道 `updates/local-v38`；协作 main 不等于当前单机运行版。原实际一键更新已在真实本地完成双库备份、安装及120秒观察，并保留较新业务；已有业务文件无需替换，不能宣称这次增加了游戏业务。其他 Git 分支缺基线、冲突、脏目录、分叉或他人锁时保持现有运行版。V37 仍是历史源码拉取语义，不倒填 V38 的自动安装能力。

账号、玩家库、凭据、邀请、私钥及原始运行日志均未入库。源码同步不触发线上/本地服务部署，也不替换桌面 EXE。自然玩家登录、战斗和多人效果不据此新增验收结论。
