# Windows 朋友服：独立账号与远程存档

当前提供各自登录、角色和资产隔离、城镇互相可见、聊天、单人副本及实验性组队副本。组队已按用户要求开放测试；协议通过与两台真实客户端的完整实战验收分别记录。

现有本地启动器与 `config/server.toml` 保留。远程模式使用 `config/friends-server.toml`，与本地正式存档分开。服务端只需要独立的 Python、协议/业务模块、配表和实际运行所需的原生证据文件，不需要安装游戏客户端或显卡。

## 连接

2026-10-15 已在 `134.175.57.52:19400` 部署，并按用户确认同时放行腾讯云与 Windows 的 TCP 19400 公网访问。已通过公网直连验证证书指纹、两个账号各自的角色列表、角色选择与错误令牌拒绝；SSH 仍仅允许 `119.39.53.102/32`。现有反馈网页验证返回 HTTP 200，资源暂够用，未停止或删除 DNF。

服务端使用 TCP 19400 上的 TLS 通道。客户端启动器先核对固定证书 SHA256，再提交各自的随机账号令牌，然后转发原生游戏协议。本机 TCP 19400 和 UDP 19401 仅监听回环地址；原生服务器列表的回环地址指向这层适配，不是把远程服务器地址错误公布为本地。服务器不对公网开放原生 UDP 探测端口。

```powershell
python tools/launch_friends_client.py --config state/friends-owner.json
```

也可以将自己的邀请配置放在 `state/friends-client.json`，双击根目录的 `朋友服启动器.bat`。原 `艾尔之光启动器.exe` 继续使用本地配置。

客户端位置可以通过 `--client` 指定，仍须匹配已验证的 EXE 与两个资源包。该入口沿用本地原生资源检查和兼容层，不写本地游戏存档，也不随客户端退出停止远程服务。朋友使用自己的配置文件；配置中的 token 相当于登录凭证，不要公开，也不要把自己的配置给所有人共用。

服务端的账号管理命令必须在服务器部署目录中执行，不能修改本机最初用于部署的账号库来代替修改服务器上的账号库：

```powershell
python/python.exe -m els_server.manage --config config/friends-server.toml list
python/python.exe -m els_server.manage --config config/friends-server.toml create player01 --host 134.175.57.52 --output state/friends/invites/player01.json
python/python.exe -m els_server.manage --config config/friends-server.toml disable player01
```

新账号角色列表为空，玩家自行选择角色并起名；重名会返回原生提示。角色 ID 和物品 ID 在全服唯一，每个账号最多 16 个角色。禁用账号后，新连接被拒绝，已有连接在下一次请求或定时检查时断开。同账号允许登录页和切换频道的连接交接，但只能有一个进入角色的会话。

## 存档与运行

部署目录固定为 `C:\ElsFriends`，Python 位于其 `python` 子目录，游戏与账号库位于 `state\friends`。任务 `ELS-Friends-Server` 在开机时启动，失败后最多重试三次。日志位于 `logs\friends-server`。这些路径与 DNF、反馈网页的目录和计划任务分开。

本地存档迁移通过 SQLite backup API 创建副本，只在副本上添加账号归属，保留角色、物品、货币、位置和快捷栏。已经存在的目标存档会被拒绝覆盖；已经属于多人账号的源存档也会拒绝重新分配。

每日备份任务 `ELS-Friends-Backup` 在服务器本地时间 04:00 运行，同时备份游戏和账号库。手动执行：

```powershell
python/python.exe tools/backup_friends_server.py --config config/friends-server.toml --destination backups
```

恢复时先正常停服，保留当前库和 WAL 的可恢复备份，再恢复相同批次的两个备份库。备份不包含 TLS 私钥；`state\friends\server-key.pem` 需要另行安全保管。

正常停服可创建 `C:\ElsFriends\run\server.stop`，等待日志出现 `finished` 和数据库检查点完成。再次启动前删除该停止标记。不要用复制正在使用的 SQLite 主文件代替在线备份。

## 验证与限制

`tests/test_friends_server.py` 使用临时数据库和真实 TLS/TCP 连接，检查错误令牌与证书、双账号资产隔离、越权选角、重复登录、掉线释放、重启恢复、各账号角色容量与回执、存档副本迁移和本地 UDP 探测范围。原有角色、协议、服务生命周期测试继续适用。

源代码回归与远程协议测试不代替两台真实客户端的显示、技能和组队验收。战斗仍沿用现有单人实现，完整服务端伤害与 HP/MP 校验尚未完成。不要将第一阶段称为完整多人服。
