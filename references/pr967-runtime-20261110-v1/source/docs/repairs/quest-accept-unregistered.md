# 任务助手「接受」点了没反应：两条原生剧情任务从未登记

任务助手列表里「艾索德故事1 决意1」和「亚当斯欢迎会」点「接受」后没有任何变化。服务端 `0xEE` 每次都回了 `0xEF`，长度固定 4 字节，看不出成败——实际是 `wire.accept_ack(2005)`，即 `QUEST_REWARD_UNAVAILABLE`。`2005` 落在客户端错误文案表 `0..0xC4D` 内，所以不画白框，只表现为「点了没反应」。

## 判定链

`quest_flow.handle` 把 `ValueError` 统一压成 `failure()` → `accept_ack(2005)`，真实原因被吞掉。在存档副本上直接调 `QuestState.action('accept', ...)` 才拿到异常：

```
47000 FAIL ValueError Unsupported quest identity
42650 FAIL ValueError Unsupported quest identity
```

`QuestCatalog.quest()` 只在 `self.quests` 里查，`els_server/data/seal_quests.json` 共 495 条，不含这两条。而客户端原生任务表（`analysis/seal-quests-20261015/FieldQuest.tables.json`，3468 条）里两条都在，条件也都满足：

| 任务 | 类型 | 起始 NPC | 目标 | 奖励 | 角色条件 |
| --- | --- | --- | --- | --- | --- |
| 47000 | 3 | 10017 | 在 34090 击杀 6501 ×5（clearType 2） | 130208 艾尔精髓 ×5 | 等级 99，全职业 |
| 42650 | 10 | 10142 | 通关 5 次副本（clearType 32，含排除表） | 188598 记忆中的灵摆 ×1（7 日） | 等级 1，仅艾索德 |

`require_eligible` 对当前角色（99 级、艾索德、职业 152、stage 3）两条都返回合格；`objective_increment` 对 clearType 2 / 32 都能正常计数；奖励 `130208` 已在 `reward_definitions` 证据表内，`188598` 已在 `VERIFIED_TEMPLATES` 内，领取链不缺东西。

## 登记

`tools/register_story_quests_47000_42650.py`：从客户端 dump 原样拷贝两条 quest 与两条 subquest（47000、41990）写入 `seal_quests.json`，并重算 `seal_quests.manifest.json` 的 `sha256`。

该文件是 **CRLF + 2 空格缩进**，脚本先断言 `json.dumps(indent=2).replace('\n','\r\n')` 能字节还原原文件再动手，避免整文件重排；`subquests` 本来就有 7 处历史追加造成的乱序，所以新键按「插到数值前驱之后」的位置落位，不重排。结果：`quests 495 → 497`、`subquests 136 → 138`，diff 为纯插入 259 行，其余字节未动。回滚备份 `els_server/data/seal_quests.json.bak-20261105-1940`。

## 热加载

`seal_catalog` / `quest_catalog` 带 `lru_cache`，改数据文件不会自动生效。`session_dispatch` 增加 `_QUEST_KINDS=(0xEE,0xFA,0xF4)` 与 `_refresh_quest_data()`：按 `seal_quests.json` 的 `(mtime, size)` 判变化并 `cache_clear()`，不 reload 模块（`storage/seal_quests` 的 `QuestState`/`QuestIncomplete` 被 `quest_flow` 在模块级持有，reload 会破坏 `except` 的身份比较）。

## 验证

- 副本 `D:/tmp/quest3.sqlite3`：两条 `action('accept')` 均返回 `objectives={47000:0}` / `{41990:0}`。
- 线上：`character_quests` 出现 47000（accepted_at 1793879012 = 19:43:32）与 42650（1793879014 = 19:43:34），即修复后玩家自己点成功。
- `tests.test_region_quests`、`test_quest_lock_boundaries` 通过；`test_seal_quests`(3)、`test_region_quest_flow`(2+1)、`test_epic_quest_experience_ceiling`(1)、`test_quest_expiry_regressions`(1) 的失败数与暂存本改动后完全一致，属仓库既有失败。`python -m els_server --check` 退出 0。

## 仍然会对「接受」无反应的任务

19:44 玩家又点了 6980 / 6990 / 35370 / 103030 / 53672，全部在目录内，被合法拒绝：

- `6980`、`6990`：`Quest career requirement`——职业谱系不含 152，是别的职业线的转职任务。
- `35370`：`Quest predecessor requirement`——前置 35364 未完成。
- `103030`、`53672`：`Job requires current immediate parent class`——转职任务要求当前直接母职业。

客户端仍把「接受」按钮画成可点，所以观感还是「点了没反应」。要改善只能把 `failure()` 从裸 `accept_ack(2005)` 改成附一条聊天行说明原因（参考 `docs/repairs/pet-auto-cooldown-chat.md` 的做法），这属于交互改动，未做。

另外整体缺口：客户端 3468 条任务里服务端只登记了 2381 条，其中当前角色可接却未登记的有 376 条（低等级旧任务与各职业支线为主）。上游是一条条补的（#711、#213 等），本次只补了玩家实际卡住的两条。
