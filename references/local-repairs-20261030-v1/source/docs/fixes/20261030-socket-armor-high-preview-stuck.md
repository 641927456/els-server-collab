# 20261030 装备镶嵌 UI 预览 ????? 与卡死单处理

## 现象

用户在镶嵌 UI 给 +20 [阿莉尔]赤血魔影下衣（莉缇娅，template 721938，uid 1001188）镶 2 颗贤者的魔法石（135184），4 个槽全显示 `?????`，「適用」「裝備」按钮灰置。

## 排查结论（服务端链路全部正常）

- `sage_sockets.capacity(721938)`：item_type=2、flags4&0xa0=0、容量 4 ✓
- 0x1c4 请求（uid=1001188, materials={0:1001263, 1:1001263}，66 字节）digest 与 receipt `request_hash` 完全吻合 ✓
- 服务端 roll 出 `[41018, 40930, 0, 0]`（槽 0、1），pending 写入，ED 扣 6720、2 颗 135184 已消耗 ✓
- 0x1c5 回包 result=0，changes 2 条（target record 324B + empty record 324B），options 尾向量 `>IiI(0,0,4)+[41018,40930,0,0]` 编码自洽 ✓（record 头 `>QBh`11B + body 304B + tail 9B = 324B/条，复杂装备 body 330B → 350B/条）
- 41018/40930 在 `catalog()['options']` 白名单和客户端 `OptionItemData.lua.tables.json` 里都存在（desc STR_ID_24880/24877）✓

## 根因：0x1C5 options 向量长度（20261030 复盘修正，原「客户端显示层」结论作废）

receipt 全量对照（`inventory_action_receipts` kind 452/2225）：

| 会话 | target | 投入石头 | 0x1C5 options 长度 | apply |
|---|---|---|---|---|
| e14398bf | 395878 武器 1 槽 | 1 颗 | 1 | 成功 |
| 0d738f0c | 136197 武器 6 槽 | 6 颗 | 6 | 成功 `[46620,40430,46620,46620,40840,40340]` |
| 59c44aa8 | 721938 防具 4 槽 | 4 颗普通石 | 4 | 成功 `[40813,40004,40705,40912]` |
| 1f8ed20c | 721937 防具 4 槽 | 4 颗 | 4 | 成功 `[41015,40110,40710,40324]`（即 2225 seq 3325，先前误记为「发放自带」） |
| db574e20 | 721938 防具 4 槽 | **2 颗** | **4（尾部补 0）** | 无 → 4 槽全 `?????`、按钮灰置 |

规律：**成功案例的回包结果数都等于本次投入的石头数**；唯一失败案例投 2 颗却回了容量长度 4、尾部补 0。客户端按请求的材料行与返回值逐项对齐，数量不符即整份预览作废（补的 0 也读不成选项），于是所有槽 `?????`、適用/裝備 灰置。扣钱扣石头发生在 0x1c4，所以预览作废时损失已产生。与防具/强化档位/贤者石头无关——721937 的 4/4 全槽预览本来就是通的。

## 修复

- [els_server/storage/sage_sockets.py:15](file:///E:/游戏/艾尔之光/els-server-collab/els_server/storage/sage_sockets.py#L15) 新增 `_results()`：0x1C5 尾向量只回本次请求每行材料的结果（按请求行顺序），不再回容量长度补零数组；重放分支用同一函数，回包逐字节不变。
- 测试 [tests/test_sage_sockets.py:24](file:///E:/游戏/艾尔之光/els-server-collab/tests/test_sage_sockets.py#L24) `test_preview_vector_carries_one_result_per_material_row`：1 颗 → 尾向量长度 1；2 颗 → 长度 2；同一 operation 重放与首发回包完全一致。
- 扣费/扣石头仍在 0x1c4（#440 既定契约，测试 `test_paid_batch_relogin_and_exact_consumption` 覆盖），本次未改时序。

## 历史处理（保留）

对真实 DB 走 `sage_sockets.apply()` 正规路径（session_id 匹配 pending 的 `db574e20-…`，selected={0:41018, 1:40930}，operation `qa-complete-socket-721938:1002:equipment:90001`）：

- `state/development.sqlite3`：721938 的 option_groups['0'] = `[41018, 40930, 0, 0]`，pending 清空，`load_items` 176 件通过
- 执行前备份：`state/launcher/backups/20261030-021500-before-socket-apply.sqlite3`

## 待用户验证

重启服务端后，用 1~2 颗贤者的魔法石镶 +20 防具：槽内应显示选项文本、`適用`/`裝備` 可点；apply 后选项落库（`option_groups['0']`）。若文本仍显示 `?????` 但按钮可用，则只剩客户端字符串表缺 STR_ID（属性仍会生效）。
