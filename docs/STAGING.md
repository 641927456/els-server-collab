# 同机独立联调实例

联调使用现有线上机器上的独立目录 C:/ElsDevTest、独立运行账号、TLS、账号库、存档、日志及计划任务。
实例已启动，远端端口19410；现有服务19400及反馈/进度站保留。原生客户端本地桥接仍按已核回环端口工作。
联调不是直接把本地启动器的所有端口改掉：需要独立的联调连接配置和配套已核朋友服入口。
测试凭据按人分配，生成在联调主机私有状态中，不入仓库或公共资源包。
初期限制少量连接，合作副本维持既有准入门槛；自然/多人实战结果单独记录。
当前主机是4逻辑核/约4GB内存，启动后120秒观察可用内存约1.7GB。先供2至3人低并发测试，8连接上限不等于8名玩家；CI使用GitHub托管环境。

维护者按指定提交和资源锁构建最小运行包，先本地验证再部署。所有写入限定新目录和自有任务。
使用独立部署锁，不抢其他发布锁；更新时仍备份联调自己的双库及代码配置、正常停服、代码优先恢复和观察。
push/PR不触发线上更新，不把生产SSH/管理密钥放GitHub Actions。
实际资源观察、端口可达性和部署版本记录在本机私有操作回执，不以此文件代替上线验收。

## 2026-10-19 初次部署状态

服务端运行源码基线为91fed547c0997bf98b3d7f74bb30b4ccbfad73d1，后续仓库协作文档/CI提交不会自动部署。
受限运行账号ELSDevTest，独立任务ELS-DevTest-Server与ELS-DevTest-Backup；独立双SQLite库使用backup API每日04:30备份。
新服务账号对原服目录明确拒绝访问，已实际验证原服账号库/GM密钥均access_denied。
已通过：本机TLS认证、两个独立新账号空角色列表、错误凭据拒绝、120秒存活与资源观察。自测账号结束后均禁用。
公网19410目前连接重置，尚待云侧入口核查/放行及公网验收，不能声称远端客户端已经可用。
合作副本开关保持关闭；自然玩家与多人实战尚未验收。
原服19400、原配置/任务、玩家库及反馈/进度网页保留。

连接模板见config/staging-client.example.json。维护者生成各自的新联调账号/令牌，通过私下渠道交给本人；账号令牌不能通过Git、Issue、PR或共享附件交付。
把个人配置保存为state/staging-client.json，然后使用自己的匹配客户端：

```powershell
.\python\python.exe -B tools/launch_friends_client.py --config state/staging-client.json --client "自己的路径/data/x2_dx11.exe" --check
.\python\python.exe -B tools/launch_friends_client.py --config state/staging-client.json --client "自己的路径/data/x2_dx11.exe"
```

模板令牌为无效占位符。公网验收通过且获得个人测试配置后才能启动联调；本地独立测试按README中的本地启动器入口进行。
