# 20261030 罗索血条格数本地叠层（BOSS「打到一半不死」第三轮）

> 2026-10-30 收尾：本叠层**未随服务端启用**（`config/local_boss_gauge.json` 为
> `enabled:false`）。用户确认「之前修好了」指的是血量上限版，且上限目标
> `1,796,894.375 ÷ 11,900 = 151.0` 本身就是 151 格，所以恢复上限即恢复同步血条；
> 本文件只保留成可开关的实验钩子。详见
> `docs/fixes/20261030-master-road-boss-hp.md` 的「恢复上限」一节。

## 结论

上一轮回退 HP 上限后 BOSS 依旧不死，说明血量量级不是杠杆。本轮改的是**下发给客户端的血条格数**
（resource+0x58 → DTO 0x77）：`Dungeon_Md_*` 导入数据里一律是 1 格，而实机罗索客户端自己画的是
151 格。只把 34390 叠成 151，其余 15 张图不动。

## 证据

客户端 trace（`analysis/client-6c6b5180/<session>/trace.jsonl` 的 `updated_dungeon_frame`，
BOSS 是 key=0 的 NPC）：

- 20261030-013523：6,999,436,800 起，掉到 2,935,927,296（42%）后**冻结 167 秒**，随后一帧
  **直接回满 6,999,436,800**，再掉到 2,922,793,728（41.7%）卡住直到退出。
- 20261030-015556（回退原版 HP 后）：1,866,516,480 起，平滑掉到 14,892,917，最后一帧停在
  1,866,516.5 = 最大值 ÷ 1000（float32）。
- 同一会话的服务端日志只有 `client_request` kind 2000（时间同步，873 次）等杂项，
  **没有 0xa7 死亡、没有伤害上报**，`dungeon_flow` 的死亡分支一次都没进。

也就是说：血量在客户端本地结算，服务端只收死亡报告；客户端把自己的最大值算成另一个数
（某段是 ÷1000 的下限，某段是 42% 回满），所以永远不发 0xa7。
`els_server/domain/dungeon_population.py:41` 记录的 1693620 插值说明了这个字段的用途：
「按 resource44 门控血量插值、把最大血量除以 resource58」。resource58 我们发 1，
客户端自己按 151 格画条 —— 两边长度不一致是本轮唯一的可调项。

## 改动

- `els_server/domain/local_boss_gauge.py`（新增）：与 `local_boss_cap` / `local_hp_curve` 同构的
  本地叠层，校验 `schema_version`/`provenance`/`enabled`/地图号/1..65535 格。
- `config/local_boss_gauge.json`（新增）：`enabled: true`，`maps: {"34390": 151}`。
  删文件或 `enabled:false` 即恢复导入值。
- `els_server/domain/dungeon_routes.py:135`：BOSS 分支改为先过叠层再写 `raw[0x44]=1` +
  `struct.pack_into('<H',raw,0x58,boss_lines)`，并对格数做 1..65535 边界检查。
- `tests/test_master_road_boss_gauge.py`（新增，6 个用例）：配置钉死 34390→151、叠层与直通、
  开关/身份/边界/缺文件、以及运行期两条 —— 34390 的 wire 在 enabled/disabled 之间只差 1 个字节
  （`0x01→0x97`，0x77 字段本身就是裸大端 2 字节），34370/34380/34400/34490 的 wire 完全不变。

## 验证

```
python -m unittest tests.test_master_road_boss_gauge tests.test_master_road_boss_cap tests.test_master_road_resurrection
Ran 17 tests ... OK
```

未实机验证。`tests/test_dungeon_routes.py` 等 3 个模块在导入时缺
`analysis/client-6c6b5180/20261013-160720/death-event-header.json`，是既有失败，与本次改动无关。

## 边界与下一步

- 只登记实机截图观测过的 34390（x151）。其余 15 张 `Dungeon_Md_*` 未观测，保持 1 格。
- 这是开关式实验：若血条还是卡在 42% 或回满，下一个候选值是 `151 → 1000`
  （客户端内部出现过 max/1000 的下限），再不行则回退 `enabled:false`，转去查客户端的分阶段/无敌逻辑。
- 复活石那次的修复（`els_server/data/known_resurrection_maps.json` 补 16 张 Md 图）代码已在，
  但用户重启后一直没有死亡过，仍未实战验证。
