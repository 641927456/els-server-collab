# 2026-10-30 本地修复候选的完整来源

PR635 的119个原始改动文件以原head f2ef13bd78dfac9b2c36543dcf5410b3cc82caec 的Git blob字节完整保留在source/，source-contract.json逐文件绑定路径、大小及SHA。源码、配表、测试、说明及.gitignore均保留，未删减业务实现。

原PR直接覆盖了历史运行清单仍按字节引用的根文件，源码CI因此拒绝dungeon_equipment_loot.json。归档采用其他修复候选相同的独立来源布局，根目录保留当前main前驱，既有清单和校验要求不变。整个依赖组一并归档，避免只还原几个底层模块却留下不匹配调用者。

此处是待选择性整合的候选，不是安装或完整运行通过记录。后续在届时真实运行父版上按source-contract选择性整合，保留ONLINE/LOCAL差异、较新业务及支持文件；不能把归档、CI或主干合入写成已上线。原测试说明和已知失败见source/docs/DEVELOPMENT_LOG_20261030.md，原CI失败保留。
