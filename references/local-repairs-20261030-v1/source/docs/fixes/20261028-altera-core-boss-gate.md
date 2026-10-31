# 厄泰拉核心(30302) 进不去 BOSS 图

**现象**：打到 stage2 那间只有一个怪的房间后，走到出口换不了图，BOSS 图
（stage3，纳斯德之王动力装置 / 纳斯德之王）永远进不去。

**卡点定位**：

- `dungeon_altera_core_expert.lua`（图谱 `source_sha256=92fb9a60…`）stage2 part0
  只有 1 个 actor：`{"template":343,"source_index":1,"points":[4],"active":true,
  "gage":true,"team":1,"no_drop":false,"key_code":1}`，实例 key=0，脚本血量 9225。
- 该房唯一出口条件 `{"kind":1,"required":[1]}`，即「key_code=1 的对象全部死亡」。
- `dungeon_flow.py` 的 0xb8 校验同样要求当前场景激活敌对目标全部死亡，
  于是服务端回 `b9 result=-1`，`periodic()` 不置 `part_end_notified`，
  客户端的 0xbb 被丢弃。

**为什么等不到死亡上报**：模板 343 在 `npcs.json` 里是 `class_id=103`
（`NUI_PD_MONSTER`，`IS_NPC=true`，`PD_Monster.lua`），属场景对象家族——
利西安记忆2 的花（9323，同样 class103）已经证明这类对象靠原生 `flag=255`
的退场上报离场，而通用战斗路径在 `d['flag'] not in (0,1)` 处直接 `return []`
丢弃，永远进不了 `run.defeated`。全 258 张图谱共 16 处 kind-1/2 key_code 出口
条件，按命中 actor 的 class 普查：class100 门 10 个（已由 `script_gate_relaxation`
处理）、class0 怪物 33 个、class103 **只有 1 个，就是这里的 343**；模板 343 在整个
图谱集里也只出现在这个位置。

2026-10-27 的审计（`docs/DEVELOPMENT_LOG_20261027.md` 第三节）按
`active=true / no_drop=false` 把它归入「真实战斗目标，绝不放宽」，只看了声明
形状、没看原生 class，本次予以纠正。`references/pr597-remaining-20261027-v2/
PR597-remaining-adjudication.json` 对该开关的裁定是
`replace-with-finite-source-gates`（不许用通用形状放行），本修复正是按有限
来源钉死的方式实现，不用通用形状判断。

**改动**：

- `els_server/domain/local_dungeon_flow.py`：新增开关 `scene_object_exit` 与
  `SCENE_OBJECT_SOURCES`（目前仅 1 行），`scene_object_npc()` 逐条核对
  副本/stage/part、整行 source（template、source_index、points、key_code、
  team、no_drop、gage、boss、rate、offset…）、图谱 `source_sha256`、
  `PD_Monster.lua` 在路由清单里的 sha、原生 `class_id=103` 且 `IS_NPC=true`；
  `scene_object_gate()` 额外要求同场景其他激活敌对目标全部已击杀。
- `els_server/domain/dungeon_routes.py`：kind==1 出口在 `key_code_gate` 之后再试
  `scene_object_gate`，其余分支与战斗型 required 原样不变。
- `els_server/domain/dungeon_flow.py`：0xb8 的「激活敌对目标全死」循环对已钉死
  的场景对象不再否决（客户端主动来要出口，就是它自己那侧场景已结束的证明）。
- `config/local_dungeon_flow.json`：新增 `scene_object_exit: true` 与
  `note_scene_object_exit`（取证与放行范围）。设 false 即恢复上游行为。

其余地图、关卡、part、模板一律不放行；BOSS 图 stage3 的 key_code=1 是
class0 的 338（boss，9 血条），仍必须真打死。

**验证**：`tests/test_altera_core_boss_gate.py`（10 项：出口条件形状、343 的
class103/IS_NPC 身份、放行只认那一行 source、整图模拟
`['stage','part','part','stage','stage','clear']`、无 343 死亡上报也能过闸、
0xb8 回 `result=0` 并置 `part_end_notified`、随后 0xbb 直接下发 0xbc+0xb2
把 stage3（含 BOSS 338）装载出来、BOSS 房 required 仍严格、房间内有其他活怪
仍不过、开关关掉恢复上游拒绝）。
`tests/test_nasod_factory_exit_gates.py` 里那条「altera core stage2/3 都是
key_code 1 怪物」的旧注释同步更正。

**未验**：客户端在 stage2 那间的原生脚本到底何时移除 343（是否附带
flag=255 上报）没有本机抓包证据——`analysis/client-6c6b5180/` 下没有厄泰拉
核心的完整通关轨迹。本修复不依赖它上报：服务端不再等它，出口由客户端自己的
换图请求驱动。真机自然流程待玩家上号验证。
