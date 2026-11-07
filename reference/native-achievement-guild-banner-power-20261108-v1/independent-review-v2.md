# 战力业绩依赖指纹独立补审

审查者仍为 `/root/native_cp_independent_review`，沿用同一个人类授权的独立审查子代理。只审查 `review-scope-v2.json` 唯一新增的 `tools/client_compatibility_profiles.json`；没有扩展业务范围、改源码、执行游戏、重跑ABI／业务测试、发布或提交Git。

**补审通过，未发现修正后的单指纹变更存在可操作问题。** V1三文件代码结论按原SHA继续适用；新增注册表刷新属于必要交付依赖。V1没有识别出配套注册表仍固定旧JS这一遗漏，N5实际预检已阻断并保留失败；本增补核对该遗漏的修正，不把N5改记通过。

## 唯一变更及绑定

逐SHA核对source-v2全部四文件，前三文件与V1固定候选完全一致：

| 文件 | 候选SHA256 |
| --- | --- |
| `els_server/domain/achievement_flow.py` | `a2b243fabd5734fcd046e4cc9be11a9c67a5e6f65cee28b52ad5936154cb3ee7` |
| `els_server/storage/achievement_profiles.py` | `dfdcf20eb6b9cc32694958caed211d01039bf4ab3dbc09ae993bd7719a952ab7` |
| `tools/raid_native_power.js` | `2fb90926b79bdc7720b3333524c49995279d1a6f2a0331b48b6e26298f911caf` |
| `tools/client_compatibility_profiles.json` | `af27d3c775bd8201f7f06529f2976d55aba3bafbc8ea2b50cb9a501a375efacd` |

新增文件的正式父版是 `native-santilus-adrian-retirement-20261108-v1`，父文件SHA `859b3ee28d97281185cee714cbc12374af7e8a68e54c7fb8ee3d27a70b3d3f36`。候选第62行 `profiles[0].artifacts['tools/raid_native_power.js']` 由旧JS指纹 `28879678bbe97ecaf84ad9041c43161289311be4eb769f9b6d1c2cc24cd2fd94` 替换为上表已审查JS的完整指纹。

独立验证不只比较JSON语义：旧文件中旧指纹仅出现一次，**原始字节做这一处64字符替换后与候选原始字节完全相同**。因此profile数量、schema、EXE身份、原生映像及合同、目录种子、原始资源指纹、required artifacts及其余所有字段均未变化，没有删依赖、扩大允许范围或关闭预检。

## 现有加载器核对

正式父版 `tools/client_compatibility.py` SHA `d1f2d91d0094708c47e4d8fc17744b012dfb26ab6bc882bc411efdf92c7e241a`，与V104读取器相同。

- `load_registry`（160–193行）继续验证schema、种子、artifact路径和64位小写SHA格式、关键资源要求。
- `select`（202–218行）继续要求精确EXE映射、已实现合同和包括该JS／生成器在内的required artifacts，保持原映像／目录合同的一致性。
- `select`（220–222行）对每个artifact读取真实文件计算SHA并与expected严格相等，否则抛出 `Client compatibility dependency changed`。本次expected恰为已审JS的真实SHA；加载器代码未改，校验未跳过或放宽。

只读核对N5隔离回执：没有client_pid、自有Job关闭前为空、EXE未变；失败确为 `Client compatibility dependency changed: tools/raid_native_power.js`，发生在客户端启动前。没有将服务端启动或源码签名当成Game加载成功。

## 适用结论

V1报告SHA `22d69d39f27e30a075dbd82bee7b84076d6a78eecf4654504771ac4311168cfc` 的三文件代码结论和未变相关测试可复用。该注册表单指纹修复保留原身份／资源校验，与加载器一致，没有引入新的行为分支或挂点。本增补是独立代码／依赖绑定审查，不是新签名构建、选中组件、Game实际加载或双端安装回执；root仍须按新冻结构建并核实际选中的四份文件。它不代替GitHub真实审批或精确head绕过许可。
