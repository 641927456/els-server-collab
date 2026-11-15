# V209 补包后发布前定点核对

2026-11-15。**通过：client 缺少 `els_server/gameplay_diagnostics.py` 的阻断已关闭，可按本次精确产物冻结。** 此结论只核包、依赖和签名一致性；未运行启动器、游戏或服务端。

核对对象：`G:/els/analysis/publisher-followup-repairs-20261115-v209`。

- client 成员 134，server-addon 成员 2014，合并 2120；新模块已在 client 签名定义与实际 ZIP 内，内容和 `runtime/combined` 一致。
- 两个模块所有成员的 ZIP 字节、签名定义 SHA/大小及组合运行文件相同；`preview/build.json` 的 157 个源文件和资源 SHA 一致。
- 直接用启动器 `AutoUpdate.PublicKey` 公钥验证新的 client、server-addon、latest 三个 RSA/SHA-256 信封，通过；server-addon 的 `required_client_identity` 指向新 client identity。新 EXE 内包含新的两个完整签名信封，字节一致。
- 仅允许实际 client 模块成员的导入核验通过：自动报告 `archive_bytes()`→`validate_archive()`→分类，以及诊断模块/观察器源组合不再借用 server-addon。没有额外补入依赖、没有网络和原生进程。
- 先前已核过的 V9 字段修复、相关 59 项及兼容配置保持原结论；此次没有重复跑未变业务测试。

冻结标识：

| 对象 | SHA-256 / identity |
| --- | --- |
| client identity | `c87827bbc070184242c2c8c8d8f8c814eeb4f138cd95c50e7a3accc31a5f4a32` |
| client ZIP | `5496b85cd46cf1747f2bec8f3dea9eb64b4bf71527fef28bcd835d4d10fb6f04` |
| client 签名信封 | `bdb965b0d58eab51e1e560a542520edddd6a7cb0e5314baf1f99b8bd81b5b5a6` |
| server-addon identity | `496ba6efa47a357cda511a3f44477bfc094b4ab8c0c881e0865e9541e2178684` |
| server-addon ZIP | `0fb6d460ec03aaca73e5c2d4ee4a5544a09f43a38efa691c91ac4fd6b4469fc0` |
| 新预览 EXE | `d82cc49d4516a75bd82085136aaf1f128840d5bf91730f530c2adc254b3d3b1d` |

机器证据：`v209-repacked-input-check.json`、`v209-repacked-signature-check.json`、`v209-embedded-envelopes.json`、`v209-client-only-check.json`。实际安装、启动及原有实机边界由发布负责人继续核收。
