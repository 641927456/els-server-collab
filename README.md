# ELS 服务端协作仓库

私有协作源码，基线见 `baseline.json`。本仓库不包含原作者账号、玩家存档、密钥、游戏客户端或完整进程镜像。

## 首次准备（Windows x64）

1. 克隆仓库；安装 Git、GitHub CLI 和 Python 3.11+（推荐3.13）。
2. 在仓库目录运行 `python tools/setup_collaboration.py`，启用本地提交检查。
3. 下载锁定的私有运行资源：

```powershell
gh release download collab-runtime-v2 --repo 641927456/els-server-collab --pattern ELS-Server-With-Local-Launcher-20261019-v2.zip --dir .asset-cache
python tools/bootstrap_runtime.py --archive .asset-cache/ELS-Server-With-Local-Launcher-20261019-v2.zip
.\python\python.exe -B tools/ci_checks.py
```

`bootstrap_runtime.py`只安装锁定运行环境/静态数据/原生指令参考，逐项验证SHA；不覆盖源码、配置、账号或存档。首次解压/导入不生成玩家库。

## 本地测试

资源准备好后，双击“本地测试启动器.exe”，选择自己的 `data/x2_dx11.exe`；先环境检查，再启动游戏。
需要匹配已核客户端及关键资源。已有兼容适配沿用基线，未承诺任意新版本可用。
存档保存在本仓库 `state/development.sqlite3`，首次由服务端生成默认开发角色 LocalElsword，与原作者存档无关。
不同时运行图形启动器与手动服务端。

```powershell
.\python\python.exe -B -m els_server --config config/server.toml --check
.\python\python.exe -B tools/launch_integrated_local.py --client "自己的路径/data/x2_dx11.exe" --check
```

## 协作

先登记问题，再从最新main建立 `fix/<issue>-<topic>` 分支。PR写明来源、事务/存档影响、实际验证层级和未验边界。
main表示审查后的代码，服务器运行版本另有部署回执；提交代码不会自动更新任何服务器。
修改客户端合同内脚本/资源时同步核定依赖SHA，不能删除版本保护来绕过检查。

见 CONTRIBUTING.md、docs/TESTING.md、docs/STAGING.md。历史全量资料在锁定资源包内，按实际提供范围引用，不补造缺失证据。

KinkOwO第一批接手顺序、允许修改的文件/函数、验收标准和避让范围见 [第一批任务单](docs/KINKOWO_FIRST_TASKS.md) 与 [文件范围及基线](docs/kinkowo-file-scope.json)。先修已复现的邮件可见范围/未读计数问题，不并行重写主线、称号或活动。


## 2026-10-19已完成内容与V29

上一批已完成源码见 [同步说明](docs/COMPLETED_SYNC_20261019.md)。当前任务/转职/城镇移动交付见 [独立修复记录](docs/JOURNEY_REVIEWED_SYNC_20261019.md)，主分支保留本地实现，线上正式快照位于 `snapshot/online-journey-reviewed-20261019-v1`；旧快照保留，禁止整树互盖。

[V29组件更新登录器源码及构建方法](launchers/friends-v29/README.md)已纳入仓库；分享包从私有仓库 `launcher-v29` Release 下载。没有可复用环境时首次下载基础包，以后校验复用或只更新变化文件。本次Git/Release同步不部署服务器。

本批任务/转职/城镇移动范围及验收边界见[独立修复记录](docs/JOURNEY_REVIEWED_SYNC_20261019.md)，本地与线上清单分开保留。

当前全角色普通穿脱的服务端修复与未验边界见[穿脱说明](docs/OWNED_WEAR_20261019.md)，线上快照为 `snapshot/online-all-role-owned-wear-20261019-v1`，两端差异继续保留。

第二戒指与神物实例的后续服务端修复见[穿脱说明](docs/SPECIAL_WEAR_RING2_20261019.md)，两端源码快照和未验边界分别保留。

原生套装选用、冷登穿戴实例恢复及验证边界见[后续说明](docs/EQUIPMENT_NATIVE_EFFECTS_20261019.md)。

既有饰品通关收益、完整数值范围及未验边界见[本批说明](docs/EQUIPMENT_CLEAR_ECONOMY_20261020.md)。

全角色公开装备实例、到期同步与完整效果未验边界见[本批说明](docs/EQUIPMENT_PUBLIC_INSTANCE_LIFECYCLE_20261020.md)。
