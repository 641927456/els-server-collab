# 服务端结构优化交付

本批将角色公共字段、读取作用域、构造初始化、会话生命周期、周期调度和结算入口收敛到既有共享机制。双渠道各 27 个累计运行路径，其中 7 个新模块；22 个路径共享内容，5 个保留渠道字节差异。数据库格式、奖励数值及原游戏 EXE/KOM 不变；LOCAL 启动器载荷随本批精确源码更新，既有支持组件保留。

运行源码沿 channels 清单与内容 SHA 物化，不覆盖仓库根目录的历史源码视图。32 个新源码对象及两份必要中间基线均为可审查 Python 文本。历史 profile、资源锁和历史测试保持冻结。

双端各 169 项源码/自有 SQLite 合同回归已通过，包括原生事件编码字节、冷读、资格、回滚、重放、取消与通知顺序。性能仅为受控合成负载；未据此声称公网 RTT、自然 GUI 或实战验收。

已按精确双端清单核收并交付 V44。ONLINE 完成公网原生身份初读/冷读、跨连接条款及自有账号清理；LOCAL 完成独立双 SQLite 备份与120秒隔离实际服务观察。V44 公网资源首次加载与重复复用采用本批精确 structure profile 的自有干净 Git 副本核收，原游戏 EXE/KOM 和既有支持能力保留。跟踪 main 的新克隆仍由 main 当时的 accepted profile 选择渠道；本 PR 合并前不会因此自动选择 structure。脱敏验收见 references/server-structure-20261029-v1/accepted-delivery.json。Git 审批、精确 head、CI 和分支保护要求继续适用。

源码检查：`python -B tools/verify_server_structure_20261029.py`。
双端私有运行测试：`python -B tools/verify_server_structure_20261029.py --with-runtime --assets-root <锁定静态资源根>`。
