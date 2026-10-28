# V42 统一启动器首次本地初始化

Issue #622。沿实际 V41 启动器继续，保留同一个本地/线上原生窗口、共同客户端启动入口、凭据隔离和签名自更新。

Git 根目录的 `启动统一启动器.cmd` 使用系统 Windows PowerShell 核签并下载 V42+，传入仓库路径。首次切换本地时，统一启动器校验独立的签名 LOCAL 包和 Git 已验收来源，在仓库 `.runtime-cache/unified-local` 原子建立本地安装。配置由受信安装器生成，存档由既有服务端首次运行时创建，不分发作者库或测试种子。已有安装和旧工作目录继续保留。

LOCAL 包源绑定现行 1325 业务叶的完整集合及每个 Git blob/锁定资源；仅共享启动脚本、兼容依赖清单和新存档标记校验支持文件有精确增量。原 V41 friends 1764 文件签名清单逐字节保持，LOCAL 独立清单为 1779 文件。二者的 archive SHA 分别绑定，原客户端 EXE/KOM 无改动，无新增游戏 Hook。

源码和资源签名清单已保存；Python、静态数据与图片不进入 Git。`source-lock.json` 固定编译输入，原图片仍使用 `build-assets.lock.json` 中的既有版本附件。重建不需要签名私钥，也不会生成新的发布签名或替换现有文件：

```powershell
python launchers/friends-v42/build.py --check-only
gh release download launcher-v29 --repo 641927456/els-server-collab --pattern ELS-V29-Build-Assets.zip --dir .asset-cache
python launchers/friends-v42/build.py --assets .asset-cache/ELS-V29-Build-Assets.zip --output <新文件.exe>
```

初始化、并发、中断恢复、篡改和存档保持用 `python -B -m unittest tests.test_launcher_first_local` 验证；完整运行包、新库冷进程、签名公网更新与自然游戏界面分开记录。新初始化工作区不接受未核定开发根目录覆盖；源前进超出签名 LOCAL 包时保留当前安装并提示更新启动器。玩家使用说明见 [首次本地初始化](../../docs/FIRST_LOCAL_SETUP_20261029.md)。
