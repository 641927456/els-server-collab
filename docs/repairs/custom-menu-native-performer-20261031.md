# 定制菜单原生请求修复

角色菜单点击“定制”后，原生客户端发送634并等待635。23ACF70→7E9610→683650构造一个值为0的performer；旧服务端要求空列表，直接丢弃正常请求。旧夹具也使用空列表，未覆盖真实入口。

本次只将634的performer条件改为精确接受`(0,)`，继续复用现有资格、只读存储及635编码。回归测试覆盖真实72字节请求与响应、错误请求拒绝及原有会话准入。

相同业务修改已安装到线上`accessory-identification-groups-20261030-v1`和本地`local-accessory-identification-groups-20261030-v1`；两端文件SHA256均为`f6424155e2e9904d7aaa18b93c87ef205a922e5c264d9969f48ae4a8bcdc4968`。实际运行观察分别125.61秒、120.00秒，公网原生格式634→635核收通过，测试账号已清理。此项没有客户端组件依赖，不涉及Schema或玩家数据修改。

既有隔离Application/GameServer TLS的11项相关验证通过，包含重复/冷读、身份/阶段/代次、编码失败和无SQL写入。原生静态证据基于客户端SHA256 `6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709`及保留映像SHA256 `c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229`。自然GUI显示尚未验收。

私有原始材料及安装回执由维护者在本机`analysis/custom-menu-open-20261030-v1/`和`analysis/deemo1-accessory-identification-20261030-v1/publication/`核原件，未随Git上传。
