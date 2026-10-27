# 开发文档 · 2026-10-27 本轮修复

**基线**：`b2b83e6`（2026-10-26 23:28，"docs: log the 2026-10-26 round of six fixes"）
**范围**：本次会话的三组修复（4 个修复文件 / 4 个新测试文件 / 1 个新配置），另附当日其他工作线专项文档索引
**性质**：只记录本次会话改动；当日其他工作线见第七节索引，不在此重复

## 索引

| # | 主题 | 涉及文件 |
|---|---|---|
| 1 | 30282 纳斯德生产基地击败小 boss 后掉线 | `fishing_bait_loot.py`、`dungeon_equipment_loot_flow.py` |
| 2 | 30282 击败小 boss 后无法进入下一张图 | `local_dungeon_flow.py`（新）、`dungeon_routes.py`、`config/local_dungeon_flow.json` |
| 3 | 骑宠进图后体力被幽灵耗尽 / 召唤被拒 / 0x542 定性 | `mount_state.py`、`mount_flow.py`、`transport.py` |

---

## 一、总览

| # | 现象 | 根因 | 结果 |
|---|---|---|---|
| 1 | 30282 打掉小 boss（模板 193）瞬间掉线，服务端 `worker_error` AttributeError | 无身份的 `LocalSession` 走到 `_facts()` 裸读 `s.identity`，且辅助抽签调用在拒签保护之外 | Boss 死亡结算任何分支都不再中断连接 |
| 2 | 小 boss 死后出口门不开，卡在 stage1/part1 无法进下一图 | 出口条件 `{"kind":1,"required":[1]}` 指向 key_code 1 = 模板 156 `SMALLGATE`，是地图脚本自己销毁的脚本门，服务端永远等不到它的战斗死亡 | 脚本门形态放宽（开关可关），整图模拟通关到 `clear` |
| 3 | 骑宠进副本后再召唤被拒（回城也一样）、坐骑体力异常耗尽 | 客户端换场景自动解骑发 `0x542`，服务端不处理 → `companion_active.mounted` 保持 1 → 体力心跳整个副本期间继续扣减直至疲劳 | 服务端镜像释放（`recall`），拒绝原因落日志 |

---

## 二、30282 小 boss 掉线（鱼饵辅助抽签）

**现象**：单机模式打 30282 stage1/part1 小 boss（模板 193，key 14），死亡结算瞬间断线。
服务端日志 `worker_error` 为 `AttributeError: 'types.SimpleNamespace' object has no attribute 'identity'`
（生产会话中为无身份会话进入 `_facts`）。

**根因**：Boss 掉落 writer 在普通掉落之外追加一个鱼饵辅助抽签（`bait_source`）。
单机本地会话是普通 `LocalSession`，从不设置 `identity`（只有应用会话设置），
而 `_facts()` 快照裸读 `s.identity`；同时 `bait_source(s,npc)` 的调用点位于
`LootActorRejected` 保护之外，抽签内部任何异常都会中断已受理的 Boss 死亡写库。

**改动**：

```python
# domain/fishing_bait_loot.py
repr(getattr(s,'identity',None))   # _facts 对无身份会话保持可读可稳定

def issue(self,...):
    # 镜像 validate()：辅助抽签被拒以 LootActorRejected 上报，调用方可放弃该抽签
    from els_server.storage.dungeon_equipment_loot import LootActorRejected
    try:return self._issue(...)
    except (ValueError,sqlite3.Error,AttributeError,KeyError,TypeError,StopIteration) as e:
        raise LootActorRejected(str(error)) from error
```

```python
# domain/dungeon_equipment_loot_flow.py
def _bait(s,npc):            # 解析可选加抽，永不中断死亡
    try:return bait_source(s,npc)
    except (ValueError,AttributeError,KeyError,TypeError,StopIteration):return None
...
try:
    result=write(bait)
except storage.LootActorRejected:
    if bait is None:return []
    result=write(None)       # 放弃加抽后重试普通死亡写库
```

**边界**：不发明掉落、不改变掉落概率；被拒的抽签只是放弃，普通掉落不受影响。

**验证**：`tests/test_bait_source_local_session.py`（5 项：无身份 `_facts` 可读且稳定、
`_bait` 拒绝透传 None）+ `tests/test_bait_30282_midboss_death.py`（6 项：真实 30282 路由
小 boss 0xAD 复现——修复前形状抛 AttributeError、修复后各分支落库、拒绝→放弃加抽重试成功、
`_Source.issue` 包装）。预修复探针精确复现生产 `worker_error`，修复后全绿。

---

## 三、30282 出口门（kind-1 key_code 脚本门放宽）

**现象**：修完掉线后，小 boss 房清空但出口门不开，`poll_ready()` 永假，
客户端 0xBB 切图请求被丢弃（服务端未置 `part_end_notified`）。

**根因**：stage0/part1 与 stage1/part1 的过图条件为 `{"kind":1,"required":[1]}`——
「key_code 1 全部死亡」。key_code 1 = 模板 156 `SMALLGATE_BESMA_AIR_SHIP.lua`：
`active=false, no_drop=true, ally=false, team=1, class_id=100` 的 SMALLGATE 脚本门，
由地图脚本自行销毁，服务端永远收不到它的战斗死亡。这与巨龙巢穴 kind-3 门同一形态，
沿用既有的 `script_gate_relaxation` 开关。

**改动**：

```python
# domain/local_dungeon_flow.py（新）
def script_door(n):return not n['active'] and not n.get('ally') and n.get('no_drop') and n.get('team',1)==1
def _room_clear(npcs,dead):...
def key_code_gate(npcs,dead,required):
    # kind-1 的 required 只命中脚本门、且房间已清空时放宽
```

```python
# domain/dungeon_routes.py condition_ready()
if kind==1:
    from els_server.domain.local_dungeon_flow import key_code_gate
    if key_code_gate(npcs,dead,c['required']):return True
    return bool(keys) and all(k in dead for k in keys)
```

**安全边界**（普查全部图谱）：kind-1/2 key_code 条件共 16 处——8 处命中纯脚本门
（30282 两处、altera_below_tunnel×2、besma/altera_secret_hell×2、sander 桑地勒斯号
stage2/part2），**8 处命中真实战斗目标（altera_core stage2/3、elysion_memory_hard、
sander 桑地勒斯号 stage0/part1），由 `script_door` 形态检查保护，绝不放宽**。
开关仍是 `config/local_dungeon_flow.json` 的 `script_gate_relaxation`，可一键关闭。

**验证**：`tests/test_nasod_factory_exit_gates.py`（6 项：出口条件形状、整图模拟
`['part','stage','part','stage','clear']`、小 boss 房不含门死亡即可过、战斗 key_code
永不放宽、开关门控路径）。

---

## 四、骑宠：0x542 定性、幽灵耗体力与召唤被拒

**现象**：骑宠进副本后按召唤无反应；回城召唤也被拒。坐骑 1001133 体力从 22.9 耗到 0.0，
231058 会话 15:14:50 服务端推送 1072 强制疲劳下骑。

**证据链**（全量 46 个会话日志扫描，`analysis/client-6c6b5180/`）：

1. `0x542`(1346) 出现规律：每次收到 0x430 下骑确认后立即发送；且**骑着坐骑进副本时，
   客户端在进图瞬间自动解骑并发 0x542**（100237：02:06:11 进图 → 02:06:12 发包；
   122256：04:25:43 同秒）。客户端发完不等回复（城镇里 2 秒后即可再召唤成功）。
2. 服务端此前完全没有 0x542 处理 → `companion_active.mounted` 保持 1 →
   `mount_state.tick()` 在整个副本期间继续按 2.4 秒/点扣体力 →「幽灵骑乘」耗尽。
3. 副本内召唤失败发生在客户端侧：**所有日志的 `dungeon_active` 期间从未发出过 0x42C**
   （城镇内全部成功，152 字节回复）；副本内独有 kind 仅 778（20 秒心跳）。
   副本成员 DTO（0x14A，`analysis/dungeon-member-fixture.json`）同伴字段全 0，
   客户端场景层不放行召唤。服务端无法在不发明协议的前提下强制客户端发包。
4. 服务端在 `dungeon_active` 阶段本就允许召唤（`mount_flow.admitted` 含该阶段；
   真实 DB + 正确 owner(1004) 状态层召唤成功）。之前探针 result -1 是假象：
   `LocalState` 默认 uid=1001 与真实角色 1004 错位导致 `owned()` 抛「Owned mount required」。

**改动**：

```python
# storage/mount_state.py（新）
def recall(path,owner,*,now=None):
    # 镜像客户端换场释放：结算一次骑乘时钟、清 ridden 与 mounted，永不回复
    ... # 原子事务，无 mounted 状态时为无操作

# domain/mount_flow.py
if event.kind==0x542:return _recall(session,event)   # 消费换场通知
def failure(reason):session._mount_rejection=reason;...
```

```python
# transport.py（对齐 _wear_rejection 既有模式）
if event.event_id==0x202 and event.kind in (0x42c,0x42f,0x542):
    self.log('mount_diagnostic',...,rejection=getattr(business,'_mount_rejection',None))
```

**边界**：不回复 0x542（原服务器从未回复，客户端不等待）；城镇手动下骑后的 0x542
是幂等无操作；`mount_diagnostic` 只记录拒绝原因字符串，不记录原始字节。

**验证**：`tests/test_mount_recall.py`（8 项：骑乘后 recall 结算并释放、无骑乘无操作、
手动下骑后无操作、流程消费 0x542 无回复、非游戏阶段保持状态、城镇 42C→42F→542 循环
不受扰、修复后不再幽灵扣体力）。回归：既有 mount 17 项、本日全部 25 项通过。

---

## 五、技能是否生效的结论

骑宠技能（`RIDING_MOBI_Z/X/C`、`MOTORCYCLE_ATTACK_Z/X_C` 等）定义在**客户端 Lua**
（`RidingPet_*.lua`，服务端 `analysis/mount-combat-20261015/rules.json` 仅存元数据），
服务端既不实现也不拦截；攻击与死亡走普通战斗上报（0xAD 等）。因此「技能生效与否」
完全取决于坐骑能否在目标场景被召唤出来：城镇内可召唤（技能正常）；副本内召唤为
客户端场景门控（见第四节），非服务端开关。

## 六、待办

- **需重启服务端**：本日三组修复全部代码完成并通过测试，运行中的旧进程不含修复。
- 副本血量调整（普通×2 / 小 boss÷5 / boss×2）未实施，等确认后进行
  （切入点 `formal_npc_hp.maximum()` 增加 role 参数 + `role_scales` 配置 + 位置法小 boss 分类；
  注意 `tests/test_retained_native_hp.py` 已有 3 个与 `global_scale 0.1` 相关的历史失败）。
- 副本内召唤的客户端门控：若重启后仍无反应（服务端日志无 0x42C），
  需反编译确认 0x14A 成员 DTO 的同伴字段才能解锁。

## 七、当日其他工作线专项文档索引

以下文档同为 2026-10-27 产出，随本次整合一并入库，细节以各自文档为准：

| 文档 | 主题 |
|---|---|
| `GIT_PENDING_INTEGRATION_20261027.md` | #548 未合并源码整合核收（8+1 PR） |
| `FORMAL_RUNTIME_BASELINE_20261027.md` | 正式运行基线 |
| `CURRENT_RUNTIME_REGRESSIONS_20261027.md` | 当前运行回归 |
| `SERVER_LATENCY_GUARDS_20261027.md` / `SERVER_LATENCY_ACCEPTANCE_20261027.md` | 服务端延迟守卫与验收 |
| `LOCAL_AUXILIARY_ROLES_20261027.md` | 本地辅助角色 |
| `SERVER_ARCHITECTURE_20261027.md` | 服务端架构说明 |
