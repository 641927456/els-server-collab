# V44 结构优化启动器源码

本目录映射实际签编的 V44 源码，四个现有 C# 文件更新、两个嵌入资源新增。七个原资源和未变 C# 文件通过完整 SHA 引用 V43 归档。原游戏 EXE/KOM、朋友模式组件及支持文件保留。

LOCAL 签名清单为 1786 项，覆盖 1332 项正式源码/资源来源及所需支持；两个精确前驱升级策略和未知来源拒绝保持有效。完整 ZIP、EXE、私钥、账号和运行日志不入 Git。

`python -B launchers/friends-v44/build.py --check-only` 核源映射。需要编译时传 `--assets <锁定素材包> --output <新输出.exe>`；脚本只编译已归档签名资源，不签名或发布。编译器时间字段可能使重编译 PE 的 SHA 不同，不声称逐字节重现签编成品。

本次双端服务及 V44 公网签名更新已核收。资源首次加载与重复复用使用本批精确 structure profile 的自有干净 Git 副本，accepted profile 保持预先绑定的同一原字节。这不代表 main 已切换；跟踪 main 的新克隆在本 PR 合并前仍按 main 的既有 profile 选择渠道。必要脱敏事实及实际私有回执 SHA 见 acceptance.json。自然 GUI 和实战未验。
