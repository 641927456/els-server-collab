# 队友换装与查看属性增量独审

## 结论

V219 父版上的三叶候选通过源码与定点离线回归，未发现阻断缺陷。可以进入后续小版本的整合与已安装客户端核收。当前结果覆盖已有挂点内部的两处逻辑修改，实机多人换装及切换角色后的自然查看入口仍待验。

## 冻结输入

候选为 `G:/els/analysis/peer-wear-inspection-20261116-v1/candidate-v219`，父版为 `G:/els/analysis/publisher-ten-chat-integration-20261116-v219/runtime/combined`。三叶父 SHA 和候选 SHA 均逐项匹配 `candidate-v219.json`。

| 文件 | 父 SHA-256 | 候选 SHA-256 |
| --- | --- | --- |
| `tools/native_support.json` | `1c45b04ff3dd9fc11c4101f72faef205b34c4dfe7196dad46bd6f062349b3d55` | `9efafc7136b310141acc133d8bc231d291ce7b15b84dcb184f3a93a45495e86b` |
| `tools/native_support.py` | `6e3e143b593e21709cfd04ad43047c1e010610c6fb1696bb4f5dd212fe84d05d` | `dfd8a62d300d15b60197fd000e64f7add0e2b144113b894e5ee9ebc3b3ff711a` |
| `tools/client_compatibility_profiles.json` | `69dd5563d5d732b60f827092440de774da0f76e0e10680fd0b5b533b1d12a0f7` | `e6e3470c52c7c9f4dc45ea8a3198a0fa62aa1209c9b334e00f850511edef20aa` |

`native_support.json` 仅 `scripts.native_login_template` 两处 hunk 变化。`native_support.py` 仅更新对应摘要，兼容性配置仅更新这两个 artifact 的摘要。attach、replace、NativeFunction、NativeCallback 的数量与目标保持父版内容。

## 换装拒绝与队列生命周期

精确映像的 `BAAB2C` 调用 Actor 虚表 `+1398`。紧接的 `BAAB32` 检查返回值，零值跳转 `BAAC67`，销毁当前临时物品与容器并终止当前通知。原有 Hook 将这个零值抛入永久 `fail()`，连带清空队列并阻断后续通知。

候选在原位记录 `model_rejected` 后返回。`cache.end()` 和临时物品、vector 的两层 finally 均执行，`cache.peer()`、`remember()`、后续模型 finishing、`applied++` 与成功事件均跳过。原始收包回调中的 return1 维持通知已消费的含义。

缓存结束可能触发 frame，但外层 `flushing` 阻止递归消费。队列仅保存字节和原生 game generation，下一帧重新解析 Actor。独审新增第二槽拒绝测试，确认第一槽已应用后第二槽拒绝时，两个临时物品和 vector 均被释放，当前通知未计成功、未写 peer 统计、未执行 finishing。原生通知也保留拒绝前已经应用的槽变化，候选沿用该顺序。

同一测试确认换图 generation 变化清空未执行通知，随后合法通知能继续执行。真实 inventory 拒绝仍触发原来的 fail 状态，未被此次改动吞掉。

## 属性表 0/2 与 1/3

原生 `23AF3E0` 先生成 form0，只有 family10 追加 form1。精确映像 `23C065B` 的指令回放得到 form0 为 `0,2`，form1 为 `1,3`。原生 `23BF180` 对 panel `+350` 表按键查找并赋值或插入，保留旧表的其他键。

候选继续先调用原生 refresh，再核对选中角色、engine、manager 与 panel 身份。普通角色遇到完整四键表时只序列化当前 `0,2`，family10 继续要求完整四键。缺键、重复键、未知键、刷新失败和失效对象仍返回失败。客户端表本身未被此次筛选改写，原有记录范围和数值检查继续执行。

## 已执行验证

- 作者换装回归通过，覆盖 model 拒绝后下一条称号及换装通知、临时对象清理和真实 inventory 异常。
- 作者属性回归通过，覆盖普通角色、双角色、四键旧表、无效表、对象退休、refresh 失败、encoder 恢复和卸载。
- 兼容性选择及服务端 `inspection_stats.validate` 通过，普通/切换后输出为 `0,2`，双角色输出为 `0,1,2,3`。
- 精确原映像的两处分支 CPU 回放通过，映像 SHA 为 `c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229`。
- 独审扩展回归通过，脚本在 `checks/peer_review_extended.cjs`。
- 经实际 `native_support.script()`、`festival_return_origin.compose()`、`pet_auto_cooldown_wait.compose()` 完整组合后，node 语法检查通过。组合 SHA 为 `875a8bed6793781bbafd681b3b63398ac4b88a4d48ca07eedf5c65538602ceaf`。
- 相同新增换装和属性回归在 V219 父版分别失败，失败点对应永久停用及旧四键表被拒绝。

## 核收边界

以上 Hook 回归使用真实候选函数和显式原生边界替身，原生 CPU 回放覆盖指定指令片段。未附加游戏、未操作玩家或服务、未部署、未占用锁、未修改候选。G:/els 根目录没有 Git 元数据，审查依据为冻结父文件摘要。

后续核收需用已安装客户端和自有角色，验证队友一次模型拒绝后能继续同步换装，以及同一 panel 生命周期内从 family10 切至普通角色后自然查看的结果。旧事件缺少当时对象快照，源码缺陷与修复机制已经验证，历史两次日志的完整因果仍无法恢复。
