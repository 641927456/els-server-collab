# 正式登录启动修复

当前 V77/V78 runtime 的 trace bootstrap 已变为 127.0.0.2，但 native_cache_sync 仍漏登记其精确指纹，导致磁盘预检后完整组合失败。补登记唯一批准 trace，保留旧四个 trace、EXE/内存身份、精确锚点及逆向组合检查。

同时更新既有 client_compatibility_profiles.json 中 native_cache_sync.py 的唯一 SHA token；只替换 Python 时，实际兼容性预检会因旧 pin 拒绝。此候选总共两个必要运行成员，其余 2119 个父包成员保持原样。

原 22 项完整离线组合验证同输入直接复用；新实际 select 入口验证旧 pin 失败、新 pin 通过。源码、归档及签名交付状态分开：本存档未声称发布或实际启动完成。发布负责人还需核旧启动器升级、选中新 SHA、完整自有隔离启动及公网页面状态。

source/ 为选择性覆盖叶，父版与完整 SHA 见 delivery-overlay.json。没有账号、玩家库、凭据或运行日志。未来公会候选的 705c... 组合器已包含同一修复且另有公会 CP wrapper，不在此存档中，不能以这里的独立登录叶覆盖。
