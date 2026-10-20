# 朋友服 V31：组件传输和启动诊断

这是已发布并通过公网验收的 V31 实际外壳源码和公开签名运行清单，文件身份与验收范围见 `release.json`。V29、V30 的原签名更新、DPAPI 密码保护及界面保持；Git 提交本身不触发部署。

组件传输显示字节/百分比进度，断流最多尝试三次。错误哈希或超长立即失败；重试耗尽保留旧环境和当前指针。诊断记录绑定本次运行目录，兼容旧 `versions/` 和新 `component-runtimes/`，继续限制根目录、防链接和越界。

打开诊断不再先强制下载环境。有完整签名环境时复用原 Python 诊断；环境不可用时只生成所选启动器记录的有限元数据包，不能替代完整游戏日志。上传仍须用户点击原上传按钮，沿原固定证书 TLS、账号认证和幂等协议，不自动上传。

本版运行包仅改变 `runtime-tools/friends_diagnostics.py` 对应的非游戏工具。其余 1081 个运行文件保持 SHA，包括游戏 EXE/KOM、资源、probe、注入脚本和 Hook；没有新增客户端行为或服务端玩法。

## 构建和验证

复用 V29 已锁定的图标/背景图附件；本目录只保留资源锁，不含二进制、私钥、账号、存档或运行日志。在 Windows x64 准备 Python 与 .NET Framework C# 编译器：

```powershell
gh release download launcher-v29 --repo 641927456/els-server-collab --pattern ELS-V29-Build-Assets.zip --dir .asset-cache
python launchers/friends-v31/build.py --assets .asset-cache/ELS-V29-Build-Assets.zip --output .asset-cache/ELS-Friends-V31-built.exe
python -B -m unittest discover -s tests -p 'test_launcher_v31_*.py' -v
```

构建只读取公开源码、签名清单及核定资源，不使用发布私钥，不连接服务器或启动游戏。PE 编译时间和程序集名称可能使重建 EXE 的整体 SHA 与正式发布文件不同；实际发布身份以 `release.json` 为准。不得沿用 V31 版本号发布修改版。

本地资格验证覆盖断流恢复、三次上限、哈希/超长拒绝、失败保持旧环境、路径准入与链接拒绝、无 Python 元数据包、脱敏与原上传报文、密码/设置和激活回归。该验证不声称自然游戏启动、完整 SDK、GUI 玩法或多人流程通过。

公网实际从 V30 下载并验签 V31，运行环境复用 1081 个文件，仅下载 1 个非游戏工具、22,396 字节；再次检查为零下载，设置保持。离屏外壳启动检查通过，127.475 秒观察更新、游戏和网页监听 PID 保持，正式入口及桌面快捷方式已更新。另以真实 V31 .NET 实现生成并上传 1,807 字节的纯启动器元数据包，固定证书 TLS、持久报告及服务端 `launcher_component_update_failed` / `observed_stage` 重分类已核。该上传使用固定阶段 QA 夹具，仅验证无 Python 的诊断闭环，不推断真实下载故障根因；自有 QA 已禁用。

下载服务继续复用 [V29 只读分发实现](../friends-v29/update_service.py)。本目录不包含生产发布控制、主机凭据或服务端密钥，Git 同步不会自动部署服务器。
