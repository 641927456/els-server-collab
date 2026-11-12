# 「晋级时装（15日）宝箱」打不开：这个道具从来没有消费端

玩家点背包里的箱子没反应，日志里那一次点击是真的落到了服务端：

```
20:58:00 kind=0x196 event=0x202 seq=117 len=19 performers=(0,) uid=0xffffffffffffffff ... payload=00000000000f4635 00 00 00 00000000 00000001
```

`uid=0xf4635=1001013` → `template=980047`、`count=4`、`slot=18`、`bag_group=4`，即「晋级时装（15日）宝箱」×4，`option=1`（数量 UI 的「使用」按钮）。`0x197` 回的是 `code=-1` 的 104 字节静默帧，客户端不画任何提示——所以表现就是「点了没反应」。

## 为什么前面那批箱子合并没救到它

`980047` 在 245 个归档分支、362 个引用里**一次都没出现过**，`els_server/domain/cubes.py::catalog()` 也没有它。合并进来的 `common-box-opening` 覆盖的是 77 个模板和 15 组消费端，其中不含这一个。也就是说这不是「修错了」，是这一类道具本来就没有消费者：`0x196` 被判成 `Unsupported fixed cube use`，然后被 `except ValueError: return cube_result(...,code=-1)` 吞掉。

顺带确认了玩家「道具都使用不了」是**另一个缺口**：他 `bag_group=4` 的 19 个道具里只有 `980047` 是箱子，其余（魔法石、艾尔精髓、艾尔之树种子、贤者的魔法石…）都是消耗品，走的是另一条使用链，与本修复无关。

## 判定依据

`135666 晋级时装（7日）宝箱` 已经在归档里通过审阅、也是同一族 `class_outputs` 箱子，两者只差有效期：

| 字段 | 135666（7 日） | 980047（15 日） |
| --- | --- | --- |
| 客户端 `item_type` / `metadata` | 7 / 2 | 7 / 2 |
| 目录 `selection_count` | 0 | 0 |
| 发放表 | `class_outputs`，194 个职业 | 同左，逐条一致 |
| 每件 `inventory_days` | 7 | 15 |

客户端目录里 `980047` 没有可用的 item-group 表（`rules` 与 `ItemManager.lua` 都只到 `__symbolic_calls__` 就断了），所以「开一次给什么」只能沿用同族已审阅的定义，不自己编。**唯一改动是 `inventory_days: 7 → 15`**，其余逐字节照抄。

各职业发放件数并非统一：`{5:125, 6:56, 10:9, 12:4}`——基础职业 5 件（武器+上衣+下衣+手套+鞋子），后续职业加饰品和第二套。这一点原样继承 7 日箱子，属原生行为。职业 `205` 在 194 条之外，两个箱子都发不了，同样不是本次引入。

## 改动

- `tools/register_promotion_15day_box_980047.py`：受控登记脚本。断言 `DATA_SHA` 命中、`json.dumps(...,ensure_ascii=False,indent=2)+'\n'` 能字节还原原文件、且该模板未登记过才动手。输出 `boxes 6 -> 7`、`classes 194`、`size 875293 -> 1079389`、`record_sha256 07370984…`、`DATA_SHA 3ed67020… -> c1b55066…`。
- `els_server/data/owned_reward_boxes.json`：新增 980047 一行，`source` 注明是 135666 的十五日同族。
- `els_server/domain/owned_reward_boxes.py`：`BOXES` 加 `980047`，`DATA_SHA` 换新。
- `els_server/domain/local_session.py`：`0x196` 的 job-box 分支模板元组加 `980047`（预览分支靠 `row.get('owned_reward_box')` 自动生效，无需改）。

`catalog()` 因此 98 → 99 项，`owned_reward_box=True`、`selection_count=0`、`entries=()`；`0x559` 预览走 `outputs_for` 现算 6/5/10/12 件，`0x196` 走 `plan_for` 发 15 天。

## 验证

`tests/test_owned_promotion_fashion_boxes.py`（5 个新用例 + 继承的售卖夹具）：

- 194 个职业逐个比对两个箱子，模板顺序、数量逐条一致，只有天数 7/15 不同；
- `plan_for` 全部 6 件 `expires_at == epoch + 15*86400`；
- 集成：发 2 个箱子 → 点一次 → `[0xad8, 0x197]`，箱子 2→1，6 件全进 `bag_group=27`，`item_expiration` 与操作时刻相差 15 天（±120 秒）；
- `option=0`（历史双击路径）同样只开 1 个；
- 重放同一 `operation` 不扣第二个箱子。

存档副本上跑的端到端模拟（与玩家实际那一次点击同一 payload）：

```
box count 4 -> 3
granted 42573/42574/42575/42576/42577/42579  slot 10..15  bag_group 27
item_expiration 6 行，全部 expiries = 15.0 天
events [0xad8(2500B), 0x197(2579B)]
```

`python -m unittest tests.test_fixed_cubes tests.test_cube_single_count_current tests.test_acquisition_policy` 全通过；`python -m els_server --check` 通过（items 181836、dungeons 740、npc 7526）。

## 注意

`owned_reward_boxes.catalog()` 有 `lru_cache`，`local_session` 在启动时构造路由元组——**必须重启服务端**才会生效，热加载不清这个缓存。

## 回滚

`git revert` 本提交即可（数据表与模块同属一个提交，`DATA_SHA` 会一起回到 `3ed67020…`）。脚本里 `MODULE.write_text` 在 Windows 上会把 LF 翻成 CRLF，导致整文件 diff，已改成 `write_bytes`。`catalog()` 的 `lru_cache` 也要靠重启清掉。
