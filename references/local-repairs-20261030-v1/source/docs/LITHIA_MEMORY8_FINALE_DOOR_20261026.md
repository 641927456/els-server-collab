# MEMORY8 终点房：不清场不结算，清完近侧就把「下一个区域」交给客户端

> 只改终点房的三段：Boss 未离场前不结算；近侧清完时由服务端选出下一块资源 part，
> 让客户端自己搬人。不新增 actor、不改血量、不伪造死亡、不动客户端。

## 现象（会话 20261026-191129，代码已含上一版守卫）

- 进 35322，15 条 0xad 全部被接收（`184` 字节，全是普通死亡），**没有一条 `160` 字节的原生 255**；
- 服务端 `0xba / 0xbb / 0xbc / 0xc1` **各 0 次**；
- 截图里客户端已自己打出「右边的大门打开了。可以通过大门移动到下一个区域。」，Boss 条 `x18`，
  角色停在阵上，服务端没有任何往返。

结论：客户端不看服务端脸色就把门打开，然后**等**服务端选下一块区域；它自己不发 0xB8、也不发 0xBB。

## 死结

这条段在图里的唯一条件是 `kind 3, required=[9452]`，唯一出口是 `kind 4`（结束副本），
而 9452（`LITHIA_MEMORY8_STORY_DUMMY_3`）按源码注释是「门后那场战斗打完才退役」。
玩家在门前 → 9452 不退 → 条件不成立 → 不发 0xba → 客户端继续等。环路闭合。

## 变更

`els_server/domain/dungeon_flow.py`

- `FINALE_ROOMS` / `FINALE_BOSS`（9431）/ `finale_boss_pending()`：Boss 未离场时房间不结算，
  0xbb 只回 0xbc；
- 新增 `FINALE_AREA_ENABLED` / `FINALE_AREA_PART=1` / `finale_area_cleared()`；
- `periodic()`：近侧（除 9431 外的全部 active 且 team≠0 的 actor）清完后，**一次性**下发
  `initial_part(1)`（0xb7，选资源 part）＋`begin_substage(1, npc_entries=当前全员)`（0xbd），
  把下一块区域交给客户端；actor 名单原样透传，不新造。

`FINALE_AREA_PART` 是唯一的实验参数；不成立时把它改回 0 或关掉 `FINALE_AREA_ENABLED` 即回到
「不结算、也不搬人」的旧状态，不涉及数据改动。

## 边界

- 只管 35320 stage3 / 35321 stage2 / 35322 stage0；其它房间、副本、难度一律不动。
- 不产生 9452 的死亡、任务证明、掉落或经验；房间真正的结束仍然只由客户端上报的 9452 退役驱动。
- 客户端是否会因为资源里没有 part 1 而拒绝、忽略或黑屏，只有实机能验；服务端这一侧不做补救。

## 验证

```powershell
$env:PYTHONPATH='vendor'; python -B -X utf8 -m unittest discover -s tests -t tests -p "test_lithia_memory8*.py"
```

24 项全绿。新增 `test_lithia_memory8_finale_door` 四项：近侧清完只发一次 `0xb7+0xbd` 且名单透传、
近侧未清完什么都不发、非终点房不受影响、Boss 未离场时 0xbb 不结算。
`test_lithia*.py` 52 项、15 项既存报错（chip reset / first-entry handoff），与本次改动无关，数量未变。

## 实机复验要点

1. 重启服务端（不要点「更新单机版」）载入新代码；
2. 进「学会研究设施」终点房，把近侧清完；
3. 预期：场景过一下（part 切换），人被搬到「终阶」那一侧，Boss 可以直接打；
4. 若没有任何反应：把 `FINALE_AREA_PART` 改成 0 复测一次——仍无反应则说明这图只有一块资源 part，
   「下一个区域」不是 part 切换，只能改图数据（补出 Boss 区）。
