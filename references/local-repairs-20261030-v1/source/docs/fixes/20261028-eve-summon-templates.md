# 女王神侍 / 电击磁场 召不出怪

**现象**：艾丽西亚·女王侍者（`unit_type=5`）两个召唤类技能放下去都没有 actor：

- 女王神侍（超技能，MP 300 / 冷却 180 秒 / 需要 1 个艾尔精髓，「通过次元之门召唤[费尔德南]，召唤时间 60 秒」）
- 电击磁场（特殊活性，MP 100 / 冷却 10 秒，「开启次元之门召唤奥菲莉娅，持续时间 60 秒」）

**结论：两条不同的链路，卡在两个不同的地方。**

## 电击磁场：服务端模板白名单漏了 1622（已修）

取证来源：本机 spawn dump `state/launcher/script-spawn-dump.jsonl`
（`local_session.py` 对每一条 `0x2CE` 都落原始字节）与玩家轨迹
`analysis/client-6c6b5180/20261028-184402/trace.jsonl`。

- 2026-10-28T18:49:29 / 18:49:31 / 18:49:34，副本 33252，客户端**连发三条**
  单记录 `0x2CE`：模板 384（哨兵）、1621（表面切割）、1622（电击磁场），
  owner 全是玩家自己，字节都能在 native 的 20 种字段排列里**唯一**命中 layout 0。
- 轨迹里前两条各在 40 ms 后跟上 `updated_npc_record_decoded` +
  `updated_npc_actor_created`，第三条（1622）**后面什么都没有**。
- 唯一的差别就是 `EVE_SUMMON_TEMPLATES` 只钉到 384 家族和 2026-10-27 补的
  1621，于是 1622 被判 `Unverified summon template`，服务端只回 `result=-1`、
  不发 `0x2D0`，客户端自然不建 actor。

**改动**：`els_server/domain/summons.py` 白名单加入 1622。
`SI_SA_EEP_ELECTRONIC_FIELD`（NPC 1622）在客户端 catalog 里
`CLASS_TYPE 0 / IS_NPC true`，属有限来源点名放行，不是放宽解码形状：
单记录、`-1` 哨兵 key、二十种布局唯一命中、owner 绑定、坐标有限这些守卫一条不少，
测试里把开关切回旧白名单会立刻恢复拒绝。

## 女王神侍：施法链在扣材料那一步之前就断了

超技能（`m_eType 13`）走的是另一条报文：客户端先发
`0x460`（`'>BBii3f'` = 浓缩标志 / 模式 / 额外材料 / 技能号 / xyz）请求扣 1 个艾尔精髓，
服务端回 `0x461`，**只有扣成功**客户端才继续放召唤、才可能发 `0x2CE`。
`els_server/domain/local_session.py` 的 `0x460` 分支里任何 `ValueError` 都会被
吞成 `result=-1`，客户端就此中止。

用 GM 控制台留下的 `state/launcher/backups/*_before-*.sqlite3` 备份**只读副本**
（不碰 live 存档）按 18:55 那次补给后的状态复现，三个守卫现在全部通过：

- 技能确实学得到：女王神侍是 25601、真级 25604，`m_bBornSealed=1`、
  需 65 级、封印组 5（8 本书模板之一）。持有封印组 1–5 后
  `unsealed_skills` 出 25601/25604，登录报文的 id 向量（`ids_wire`）也带上它们。
- 槽位对得上：`slot_accepts(20, 25604)`（`m_eType 13` 只认 20 号槽），
  `skill_expansion.unlocked_indices` 因为有未封印超技能而放开 20 号槽，
  存档预设第 20 槽 = 25604，`validate_slots` 通过。
- 材料够：背包里 1 个艾尔精髓（130208，4 号袋、未封印、未过期、未锁定）即可，
  `boosting_2026_essence.action()` 成功回 `0x461`（一条 334 字节 payload 的
  绝对库存向量 = 扣减后的堆叠），存档里那格数量 -1。
  同批反向验证：只学 25604 时请求 25601 仍然按预期被
  `Owned unsealed hyper skill required` 拒掉。

也就是说 10 月 27 日那次唯一出现的 `0x460`（服务端回了 400 字节的 `0x461`，
即**成功**、不是 -1）是另一位角色的伤害型超技能（35603
`RNSI_HA_LMM_DESTROY_PICKEL`，无召唤），它本来就不该有后续 `0x2CE`；
不能用它推断「超技能不发 0x2CE」。三个已抓到的召唤 actor（384/1621/1622）
恰好都是 `m_eType 14`，走的就是直接 `0x2CE`。

**改动**：白名单加入 1454 `SI_HA_FERDINAND`（费尔德南）。
这是本次唯一一条**没有 `0x2CE` 实抓**、只靠客户端数据钉死的放行，依据链是：

- 技能侧：25601/25604 是 `m_eType 13`、图标 `SI_HA_EEP_LINK_OVERCHARGE_ILLUSION`，
  且 `NUMERICAL_DATA` 里带 `SA_EFFECTIVE_TIME = 60`，与 tooltip 的「召唤时间 60 秒」一致
  ——它确实是召唤型超技能，不是纯伤害超技能。
- actor 侧：客户端 NPC 表里 `Motion_EEP_FERDINAND.x` 只有两个模板用——
  1454 是 `CLASS_TYPE 0 / IS_NPC true`，6384 `EN_TUNNEL_EVENT_FERDINAND` 是
  `CLASS_TYPE 103`（副本里的敌对同模怪），照旧拒绝。所以区分召唤物与怪物的
  是 `CLASS_TYPE`，**不是**模型名。全客户端只有 1454、1604 两个 `SI_HA_*`
  actor，1604 的 motion 是 `Motion_AMM_APOCALYPSE`（别的角色家族）。

若真机放一次女王神侍后 dump 里出现的不是 1454，撤掉这一条即可（`summons.py` 的
白名单是唯一的开关，测试同时钉住了「切回旧白名单立刻恢复拒绝」）。

## 安全边界

- 白名单仍是**逐个模板点名**的枚举，没有按形状/前缀放宽。
- 每条 `0x2CE` 依旧要求：单记录、dto key `-1`、owner == 施法者 uid、
  坐标有限且 ≤100000、二十种 native 布局里**唯一**命中，`0x2D0` 实例号仍在
  `16 <= key < 16384` 且整 run 不复用。
- `0x460` 的守卫一条没松：仍要求已学、`m_eType 13`、20 号槽命中该技能、
  材料是当前且未锁定的普通艾尔精髓，失败一律 `result=-1`。
- 未识别模板照旧继续写 spawn dump，漏放的召唤物看得见、不会被静默吞掉。

## 验证

`tests/test_eve_summon_templates.py`（12 项，本机全 OK）：

- 抓包字节解码身份（key `-1`、模板 1622、owner 一致）；布局命中唯一（`['0']`）。
- `sentry_spawn` 出 144 字节 `0x2D0`、实例号 16、尾部 24 字节 0。
- 白名单切回旧集合（1622 前 / 1454 前两个版本）立刻恢复拒绝。
- 其余守卫对新模板继续生效：owner 不对、两条记录、尾字节、实例号越界全部拒绝。
- 真实 `LocalSession` 施放路径：回 `[0x2CF, 0x2D0]`，`0x2CF` payload 是
  `struct.pack('>i', 0)`，并把请求写进 `run.summon_payloads`（顺带确认电击磁场
  也享受 20261028-sentry-stage-persistence 的换图续命）。
- 有限来源体检：白名单里每个模板在 catalog 都是 `class_id 0 / is_npc true`；
  1622 脚本名 = `SI_SA_EEP_ELECTRONIC_FIELD.lua`；1454 的 motion、25601/25604 的
  `m_eType / m_bBornSealed / SI_HA_EEP_ 图标 / SA_EFFECTIVE_TIME 60` 全部钉住；
  6384 同模但 `CLASS_TYPE 103` 仍被拒；1604/200/519 等未点名模板仍被拒。

同批回归：`test_sentry_stage_persistence`（9）、`test_altera_core_boss_gate`（10）全 OK。

**待玩家上号验证**（需要他自己重启服务端，白名单才生效）：
两个技能各放一次——电击磁场应直接出 actor；女王神侍应先扣 1 个艾尔精髓、
再出费尔德南。如果女王神侍扣了精髓仍不出怪，看 `state/launcher/script-spawn-dump.jsonl`
最后一条 `0x2CE` 的模板号，按同一套体检补进白名单即可。

**另**：本机缺 `analysis/skills-clear-20261015/` 抓包产物，`test_summons` 仍在
import 期 `FileNotFoundError`；与本次无关的既有失败（缺 `cryptography`、
若干 NS 假 fixture 套件）未追查。
