# 后台启动与装备原生复验

后台验收曾把图形设备初始化失败显示为“游戏脚本损坏”。修复屏幕外窗口和隔离保护后，真实原生客户端完成四件普通初鉴、影子初鉴、穿上、卸下及新进程重登；未发送键鼠事件，正常游戏启动行为保持。

[源码、适用环境、必要性与恢复说明](../references/background-native-gear-20261026-v1/README.md)、[源码摘要](../references/background-native-gear-20261026-v1/manifest.json)、[脱敏核收](../references/background-native-gear-20261026-v1/qualification.json)。

本次通过的是独立私有账号的受控原生回调和状态核验，不宣称自然点击、像素界面检查或战斗。原始客户端、内存、资源、证书、凭据、数据库和运行日志均未上传。

鉴定与穿脱业务代码已在 PR512/513 合并并安装双端。本次[双端安装复核](../references/background-native-gear-20261026-v1/dual-installation.json)确认较新正式包保留修复及现有其他增量，因此无需重复停服安装。Git归档不自动发布服务或改动玩家存档。
