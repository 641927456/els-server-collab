# 副本内定制（Custom）不生效 —— 2026-11-08 收敛记录

客户端 SHA `6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709`，
保留运行期映像 `analysis/client-6c6b5180/x2-runtime.bin`（SHA256 `c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229`）。

## 1. 结论表

| # | 现象 | 判定 | 证据 |
|---|---|---|---|
| 1 | 副本内点「定制适用」没反应 | **已修**（副本内准入已放开，落库成功） | `state/custom.log` 11:18:39 `apply ok (dungeon) slot=1 custom=11008 replayed=False`；11:18:44 同形 |
| 2 | 副本内保存被重置、退出重进回默认 | **证伪，不存在** | 14:35:36 进副本时服务端仍读到 21 格：`dungeon dto custom=21 ... ids=[8011, 11008, 11012, 11026]`；库里现为 19 条按槽 + 主选择 11008 + 脸部 12106，一条没丢 |
| 3 | 定制面板行显示职业默认 | **确认存在，且城镇也有（本条已更正，见 §3.5）** | 11:19 城镇截图四行都写「不朽之王晋级技能切入」，但槽 3/4/5/6 在库里是**四个不同道具**：13011=ELS制服技能切入、13021=自然白泳装技能切入、13024=[科宝]4月的管家与女仆技能切入、13051=EL★STAR2技能切入（Ver.Special）。四个不同名字不可能同名 → 每一行都回落到职业基础定制 |
| 4 | 副本内角色本体不体现定制 | **未解决** | 见 §2，六条通道全部实测无效 |
| 5 | 窗口行是在 `0x635` 创建窗口时一次性构建的 | **新假设，已按此改序** | 4CD 原来排在 635 之后；改成之前之后四件定制测试全过，待 GUI 复核 |
| 6 | 面板只有「边框」能识别 | **已修（根因=4CD 行类型字节）** | 客户端 `CUSTOMIZING_TYPE` 的值等于槽号，我们发的是折叠后的家族；边框是单槽 16 所以唯一对得上，见 §3.7 |

**一句话**：服务端能说的已经全说了，客户端副本角色就是不采纳。

## 2. 已实测证伪的通道（不要再花时间）

`analysis/client-6c6b5180/20261108-143330/server-logs/server.jsonl`
（UTC，本地 +8）14:35:36 进副本那一帧的**完整出站序列**：

```
0x383(80)              准入
0x4CD × 21 (168 each)  定制登记
0x4CC(2112)            全表回执
0x18E(2208)            演员通知（在 dungeon_start 之前）
0x14A(8240)            dungeon_start
0x18E(88)              ← 空表
0x18E(2208)            ← 全表（empty→full 复投）
```

紧接着 `14:35:38.840 0x18E(2208)` 又一次。**角色依旧默认。**

| 假设 | 做法 | 结果 |
|---|---|---|
| 时序：18E 到得太早，actor 还没建 | 建前发（上面 14:35:36）、建后发（11:18:39 副本内 Apply 回 `0x4CC(176)+0x18E(2208)`） | 都无效 |
| 客户端对「与缓存相同」的 map 早退 | 空表→全表 复投（`local_session.py:3048`，trace `dungeon reannounce empty->full slots=21`） | 无效 |
| DTO 变长槽 0x657 没填 | 21 个 custom_id 已填（`dungeon_messages.py:83`） | 无效 |
| 填 0x657 导致后续字段错位、整条 member 被丢弃 | 副本能正常进、子场景 0x96/0xb2 正常、能打怪 | 证伪 |
| 写库失败 | `character_custom_permanent_selection_slots` 等四张表读数一致 | 证伪 |
| 18E 到得太早，场景还没就绪 | 15:01:29 客户端发 `0xb3`（场景就绪）后，15:01:32 开面板补发、15:01:38 Apply 再补发各一次 `0x18E(2141)` | 无效 |
| 18E 中间那个 u32 是演员选择子，副本要非 0 | 15:01:26 第三帧 `selector=1`（`payload=2141 uid=1001 selector=1 title=12620 slots=21`） | 无效，**该帧已删除** |
| 面板是全表，副本只是看不到差别 | 待机动作页四行同名，但其中一行的值 11012 对应道具 470251「模特动作：艾索德」，见 §3.5 | 证伪（面板确实没吃到登记） |

**这一节的意义**：副本侧六条通道（时序/复投/DTO/选择子/场景就绪/落库）全部关闭。再看
§3.5，问题更可能不在「发给副本的哪一帧」，而在「窗口根本没吃到 4CD」。

## 3. 本轮新增的原生侧证据（P0 部分结果）

保留映像按 RVA 扁平布局（`ImageBase 0x140000000`，文件偏移 == RVA，`.themida` 段 rawsize=0），
已用离线 x64 反汇编（`D:\tmp\x2dis.py`，Frida `Instruction.parse` 作 Capstone 后端）与
成员访问交叉引用扫描（`D:\tmp\x2scan.py`）核对。

| 成员 | 全映像访问点 | 其中落在 `0x87CAF0`（UserInfo 恢复） |
|---|---|---|
| `+0x3EF`（称号，wire i32） | 15 | **有**（`0x87D970` read、`0x87D9E0` read） |
| `+0x657`（wire `set<int>`） | 13（全为 `lea`，集中在 `0x7661A0 / 0x7E0700 / 0x7E2200 / 0x7E2780 / 0x7E3A00 / 0x9603F0 / 0x9747A0 / 0xD9C8B0 / 0xD9D2F0 / 0xDF1410`） | **零** |

`+0x3EF` 与 `+0x657` 同属 member DTO，但恢复路径只搬 `+0x3EF`。这条**削弱**了
「0x657 是副本角色定制载体」的判断，但**不足以定论**——`+0x657` 可能由网络读取器
自己写入另一个持有者结构，再被拷贝。**P0 未完成**：还缺「副本 actor 初始化读哪个字段」的正向答案。

另：文档 `custom-menu-native-performer-20261031.md` 里 `30D5C50 → 214E6C0` 那条注释
**不是 0x18E 的读取器**。`0x30D5C50` 的实际结构是「`need(0x1C)` → 读 1 个 qword →
`need(0x13)` → `0xDD46E0` 读 0x408 字节记录的 vector → 再读两段」，
与 18E 的 `uid(Q)+u32+i32 title+map<byte,vector<Info>>` 不符。

`+0x657` 的内存语义已定：`0xDF1FE6`/`0xDF1FF0` 把 `[rsi+0x657]` 与 `[rsi+0x65F]` 两个
指针换出再换入（`std::set` 的 `_Myhead`/`_Mysize`），紧接着 `0xDF2019` 处理下一个
`+0x667`。也就是 `+0x657..+0x666` 正好是一个 `set<int>` 成员，和 wire 上那一格对得上。
但 `0xDF1410` 是**搬移/交换**函数，不是从包体填值的函数，所以「谁从 18E/14A 写这个 set」
仍未定位。

### 3.5 面板行名的更正（本轮真正的收获）

上一版本把「面板行显示默认」判成证伪，理由是「四行同名 = 槽 3/4/5/6 的四个值」。
这条推理是错的：那四行如果各显示各的，就应该是四个**不同**的名字。逐格查客户端道具表：

```
13011 -> 470096  'ELS制服技能切入：艾索德'
13021 -> 470341  '自然白泳装技能切入：艾索德'
13024 -> 294062  '[科宝]4月的管家与女仆技能切入（A）：艾索德'
13051 -> 390030  'EL★STAR2技能切入（Ver.Special）：艾索德'
```

四格四个不同道具（11:05:35 起陆续 Apply，见 `state/custom.log`），截图却四行都写
「不朽之王晋级技能切入」——那是**职业基础定制**的名字，即一行拿不到「授予它的道具」时
的回落值。副本那张「待机动作」截图同理：槽 11 = 11012 的道具是 470251
`模特动作：艾索德`，面板写的是「不朽之王待机动作」。其余三格是 11008（免费动作，
`template_of` 返回 0），回落成本来就该是基础动作，看不出差别。

**结论：定制窗口从来没有反映过存档，城镇和副本都一样。** 这不只是显示问题——它意味着
我们发出去的 `0x4CD`（唯一携带「授予道具」的事件）在窗口看来并不存在。副本侧的六条
通道全都无效，很可能就是因为「窗口本身就没吃到登记」这同一件事。

### 3.6 改动：4CD 挪到 0x635 之前

原实现假定「窗口在 635 之后才存在，行状态排在它后面」，代码注释也是这么写的。但症状
（城镇、副本每行都是基础定制）恰好等于「窗口建立那一刻，登记表里什么都没有」。

于是 `character_custom._window_rows()` 把回放拆成两段并改序：

```python
registrations,notices=_window_rows(s)
events=registrations+opening_info(...)+notices   # 4CD... → 635 → 4CC → 18E
```

副本分支同改。同时删掉已被证伪的第三帧（`selector=1`，15:01:26 实测无效）。

### 3.7 根因：4CD 的行类型字节发错了（用户点出来的）

改序之后用户反馈：**「边框」能识别，别的类别不识别**。这一条把根因指得很准。

客户端自己有权威枚举 `resource-scripts/Enum.tables.json` → `CUSTOMIZING_TYPE`：

```
CT_WAIT_MOTION 1  CT_FACE 2  CT_SKILL_CUTIN 3  CT_SKILL_CUTIN_SECOND 4
CT_SKILL_CUTIN_THIRD 5  CT_SKILL_CUTIN_FOURTH 6  CT_SIT_MOTION1 7  CT_SIT_MOTION2 8
CT_WAIT_MOTION2 10  CT_WAIT_MOTION3 11  CT_WAIT_MOTION4 12  CT_SIT_MOTION3 13
CT_SIT_MOTION4 14  CT_HYPER_EFFECT1 15  CT_SKILL_FRAME 16  CT_PORTRAIT 19
CT_QUICK_VOICE1..4 20..23  CT_EMOTICON1..4 24..27  CT_POINT_MARK 28
```

**CT 的值就等于槽号。** 而我们的 `SLOT_TYPES` 是故意折叠过的
（`10:1, 11:1, 12:1`，`4:3, 5:3, 6:3`，`8:7, 13:7, 14:7`，`21..23:20`，`25..27:24`），
因为「一个待机动作可以放进 1/10/11/12 任意一槽」，选槽时按折叠后的家族校验是对的。

但 `0x4CD` 里那个类型字节是**窗口给这一行分桶用的**，必须用该行自己的 CT 值（= 槽号）。
我们发的是折叠后的家族，于是：

| 面板页 | 槽 | 我们发的字节 | 应该发 | 结果 |
|---|---|---|---|---|
| 边框 | 16 | 16 | 16 | ✅ 唯一对得上 → **用户看到能识别** |
| 待机动作 | 1/10/11/12 | 1,1,1,1 | 1,10,11,12 | 后三行回落基础动作 |
| 技能切入 | 3/4/5/6 | 3,3,3,3 | 3,4,5,6 | 后三行回落基础切入 |
| 动作 | 7/8/13/14 | 7,7,7,7 | 7,8,13,14 | 后三行回落 |
| 快捷语音 | 20/21 | 20,20 | 20,21 | 第二行回落 |
| 表情 | 26/27 | 24,24 | 26,27 | 两行都回落 |

单槽页（脸部 2 / 觉醒 15 / 边框 16 / 头像 19 / 徽记 28）本来就不受影响——**这正好解释
「为什么只有边框认到」**。

改法：`registered(value,item=0,family=None)` 增加 `family`，
调用方在知道槽的地方传 `family=slot`；校验 `SLOT_TYPES[family] == custom_type(custom_id)`，
所以既挡住了乱填，也保证「待机动作放进 11 槽」这类跨槽放置仍然合法。
书本使用路径（`storage.character_custom.use_book`）不知道槽，保留默认=家族类型。

### 3.8 再补一处：Apply 时重发该行的 4CD

`0x4CD` 原来只在开窗时发一次。面板一旦是在修好之前打开的，行里就永远没有那次登记，
之后再怎么切都刷不出来。所以 `storage.character_custom.select()` 的回执改成：

```
0x4CD（该行自己的 CT = 槽） → 0x4CC（只回本格） → 0x18E（整窗）
```

这样**切一次就够**，不依赖开窗顺序。测试同步：`test_character_custom_apply`、
`test_character_custom_dungeon` 的 `result_of` / 事件序列断言从 `[0x4cc,0x18e]`
改成 `[0x4cd,0x4cc,0x18e]`（拒绝路径仍只回单个 `0x4CC`）。

### 3.9 关于「会话被重启」

排查中发现服务端在 **15:18:43** 自己起了一个新会话（`analysis/client-6c6b5180/20261108-151843`），
旧会话 `20261108-145842` 在 15:18 停更。15:22:36 / 15:35:29 的 `forced` 都落在新会话日志里，
说明热重载确实作用在**活着的那个进程**上；但 `els_reload.py --status` 打印的是旧会话路径，
之后看日志要按 pid 的 `--stop-file` 找目录，别按 mtime 猜。

另：`state/custom.log` 在 15:21:45 / 15:22:30 出现过 `owned=2 slots=3`，
但任何库里都找不到「2 条拥有」的 owner（1001 是 2902 条），初判为写事务期间的瞬时读，
**未证实**，先记录不追。

## 4. 当前 21 格在副本内的可观测性（最可能造成「还是没用」的误判）

| 槽 | id | 内容 | 副本内能否目视 |
|---|---|---|---|
| 1 / 10 / 12 | 11008 | 免费基本待机动作（`template_of=0`） | 与默认相同，**看不出变化** |
| 7 / 13 | 11026 | 拍立得照片（坐姿） | 【待实测】副本内没有坐下入口，大概率看不到 |
| 8 | 14107 | 街头合奏表演吉他（坐姿） | 同上 |
| 14 | 14003 | 月亮的美丽翅膀（坐姿） | 同上 |
| **3 / 4 / 5 / 6** | 13011/13021/13024/13051 | **技能切入** | **放技能就能看，最可靠的判据** |
| 15 | 1000073 | 觉醒特效 | 用超技能时可见 |
| 16 | 8011 | 技能边框 | UI 上可见 |
| 19 | 15214 | 立绘/头像 | UI 上可见 |
| 2 | 12106 | 脸部 | 模型上可见但细微 |
| 20 / 21 | 156048 | 快捷语音 | 可听 |
| 26 / 27 | 17033 / 17000 | 免费表情 | 需触发表情 |
| 28 | 19003 | 徽记 | UI 上可见 |

**验证副本定制时请只用第 3/4/5/6 格（技能切入）**：进副本 → 放一个带切入的技能 → 看切入图是不是「不朽之王」。
用「动作」页（7/8/13/14 坐姿）判断副本效果是无效判据。

## 5. 本轮改动（diff 摘要）

- `els_server/domain/local_session.py:1084` 新增 `_custom_book_outside_town()`：0x219 闸门在
  `dungeon_active` 下**只**放行 29 字节且 template 命中 `character_custom.catalog()` 的定制书，
  其它 219 家族（复活、票券等）维持原样。
- `els_server/domain/character_custom.py:142` `admitted()` 的 phase 放宽为
  `('town_ready','dungeon_active')`，与 `panel_admitted()`(:153) 一致——
  它是 `use_book` 的 validate 回调，副本里必然抛，客户端对 -1 不画任何提示。
- `els_server/domain/local_session.py:3048-3063` dungeon_start 之后追加 空表→全表 两次 0x18E
  （保留负结果，用于排除「客户端相同即早退」）。
- `els_server/protocol/protocol_codec.py:119` `_TRACED_OUT_KINDS` 扩到含 `0x18E`，
  出站字节落 `state/wire-out.log`。
- 新增 `tests/test_character_custom_dungeon.py`。

## 6. 我怎么验证的

```bash
# 副本内注册/应用/落库/DTO/回城/重登/幂等
./python/python.exe -B -c "import sys,runpy;sys.path.insert(0,'tests');\
sys.argv=['t'];runpy.run_path('tests/test_character_custom_dungeon.py',run_name='__main__')"
# 既有三件不回归
#   test_character_custom_apply / test_character_custom_opening / test_character_custom_all_books
```

离线原生取证（不启动游戏、只读映像）：

```bash
python D:/tmp/x2dis.py 0x214e6c0:40        # 反汇编任意 RVA
python D:/tmp/x2scan.py 0x657 0x3ef 0x1eb  # 成员偏移的全映像交叉引用
```

## 7. 热重载（2026-11-08 15:00 打通）

`state/hot-reload.json` 已加入三个定制模块（依赖顺序在后）：

```
els_server.domain.character_custom
els_server.protocol.character_custom_messages
els_server.storage.character_custom
```

并把「进副本的定制爆发」从 `local_session.py` 搬进
`els_server/domain/character_custom.py:dungeon_entry(s, ticket=False)`，
返回 `(values, before_start, after_start, note)`；`local_session.py` 只剩 4 行调用。

为什么要搬：`local_session` 的类被活会话持有，**永远不能热重载**（reload 会换掉类对象，
所有 `isinstance` 判定随即失效）；而 `storage/character_custom.py:296` 是在**函数体内**
`from els_server.domain.character_custom import handle as domain_handle`，所以这个模块
一旦 reload 就立刻生效。搬完之后，调这段爆发只需要：

```bash
python D:/tmp/els_reload.py            # 写 state/hot-reload.request 并等日志确认
python D:/tmp/els_reload.py --status   # 看名单、看每个模块的 mtime
```

实测输出 `2026-11-08T15:00:10 forced ... character_custom, character_custom_messages,
storage.character_custom`，请求文件被消费，会话未断。

**边界**：`state/hot-reload.json` 只在服务端启动时读一次，所以新增名单需要重启一次；
之后修改定制域模块不再需要。

## 8. 还没做 / 下一步

1. **P0 收尾**：定位副本 actor 初始化读 custom 的字段偏移与消费函数。已备好反汇编与 xref 工具，
   但缺一条从「渲染函数」倒推的入口。最快的补法是从 `Application` 的 actor 构造点往下找。
2. **P2**：自定义可能只跟在 actor 属性包（`0xCD`/`0xA160` 一类）里，或需要在 `0x14A` 主体内多带一段。
3. 若 P0/P2 都无解，按 P3 走客户端侧补丁，或明确写进文档「副本内不体现定制」，不做假修复。

## 9. 2026-11-08 16:00 这一轮（扁平 18E 被证伪 + 2A 尾部读取器定位）

### 9.1 扁平 18E 实验：失败，已回滚

把 18E 每槽从 `byte + u32(1) + info` 改成 `byte + info`（与 4CB/4CC 一致），用户实测
**边框和头像一起掉回职业默认**。这条负结果的用处很大：

- 说明客户端**确实在消费 18E**（否则不会跟着变）；
- 说明 `u32(1)` 那个「一元列表」包装是**必需的**，不是冗余。

已回滚，并在 `character_custom_messages.selected_notice` 里写明「不要再简化」。
回滚后从 `state/wire-out.log` 里逐帧解出实时字节，21 槽全部 `rest=0`（精确对齐无残留）：

```
15:47:11 n=21 rest=0 title=12620 slots=[1,2,3,4,5,6,7,8,10,11,12,13,14,15,16,19,20,21,26,27,28]
15:47:15 n=21 rest=0 title=12620 slots=[同上]          ← 面板 open（日志行被截到 2057B，非编码问题）
```

### 9.2 2A 尾部读取器找到了：`0xDA3370`

用 `D:\tmp\x2dis.py` 对保留映像逐函数核对，`0xDA3370` 就是 2A 的 DTO 反序列化器
（`rdi` = 目标结构，`rcx` = 读取游标）。尾部顺序与线缆字段一一对应：

| 结构偏移 | 读取函数 | 线缆形态 | 我们发的 |
|---|---|---|---|
| `+0x698` | `0xDB4110` | `u32 计数` + 每项 `{i32, float}` 写入一个 map | `u32(0)` 空表 |
| `+0x6A8` | `0xDB2880` → `0xDD1EE0` | `u32 计数` + 每族 `{byte 类型, 行数组}` | `owned_map()` ✅ 对得上 |
| `+0x6B8` | `0x3B6D810` | 1 字节 | `b'\x01'` |
| `+0x6B9` | `0xDB6F10` → `0xDD7C30` | `u32 计数` + 每项 `{i32 键, 数组}` | `u32(0)` 空表 |
| `+0x6C9 / +0x6DF / +0x6F5` | `0xDB6FA0` ×3 | 三条记录 | 三条 |

**关键更正**：`0x6A8 - 0x698 = 0x10` 是**内存布局**（一个 `std::map` 占 16 字节），
**不是线缆长度**，不能据此推断「少发了 12 字节」。

`0xDD1EE0` 逐条核实了拥有表编码：先读 `u32 计数`，再每族读 `byte` 键 + 一个行数组
（元素 76 字节），与 `owned_map()` 的 `u32 + {byte + u32 + rows}` 一致。

### 9.3 当前唯一还空着的两格

`+0x698` 与 `+0x6B9` 两个 map 我们一律发空表。`+0x6B9` 的形态是
`map<i32, 数组>`，和 18E 的 `map<槽, 定制列表>` 结构同源、只差键宽（i32 vs byte），
是「已选表」的头号嫌疑。改它需要动 `els_server/protocol/local_messages.py:235`
并**重启**（`local_session.py:3` 在模块顶层绑定了 `player_initialization`，
换不掉旧函数对象，所以这两个模块都不在热重载白名单里）。

### 9.4 这一轮没改动任何线缆

只加了两条 trace（都可热重载）：

- `domain/character_custom._window_rows`：建窗时打印每行真实的行类型字节
  `rows=1:1 2:2 3:3 4:4 ...`，用来把「按代码复算」换成「实测」；
- `storage/character_custom.select`：Apply 时打印 `slot / cid / row / ack 长度 / 通知槽数`。

下一次开面板 / 下一次 Apply 就能在 `state/custom.log` 里直接读到地面真值。


### 9.5 2026-11-08 16:07:43 的实测：三条载波对「技能切入」族全部无效

面板截图（技能切入页）四行仍是同一个名字「不朽之王晋级技能切入」——即职业默认。
与此同时 `state/custom.log` 记录：

```
16:07:43 apply slot=3 cid=11016 row=3 ack=105 notice_slots=21
16:07:43 apply ok (dungeon) slot=3 custom=11016 replayed=False
```

也就是说，**针对 slot 3 的 4CD（行字节=3）+ 4CC + 18E（21 槽全表）都重发过一遍**，
面板该行依然没有变化。推论：

1. 问题不在「4CD 行字节发错」这一层——因为 Apply 当场就重发了 3 条载波；
2. `11016` 本身就是切入（`custom_type=3`，模板 470221「艾索德晋级技能切入-2」），
   不是误选的其它族道具；
3. 剩下的分歧只能出在「客户端是否接受这个 custom_id 落在这一行」。

### 9.6 已排除的形状问题

`0x4CB`（客户端**自己**发的应用包）经 `request_slot` 校验为
`u32(1) + byte 槽 + Info`，而 `0x18E` 用的是同一个声明类型 `map<byte, vector<Info>>`。
所以「按槽、每槽一元」的 18E 形状与客户端自身的序列化一致，**形状不是根因**。
另从 `state/wire-out.log` 解出实时 18E，21 槽 `rest=0`（无残留字节），编码也是精确的。

### 9.7 下一步的判据

要看的下一个事实是：点开该行右侧的 ▼ 下拉，**里面有没有列出已拥有的切入**。

- 列出 → 客户端的登记/拥有数据是通的，问题只在「哪一个是选中态」，继续查选择载体；
- 不列或全灰 → `4CD`/2A 拥有表根本没进窗口，回头查那条路。

为此副本 open 分支也补了 `bytes=` trace（`opener ok phase=dungeon ... bytes=1:1 2:2 ...`），
两条 open 路径现在都会把真实行字节落到 `state/custom.log`。

### 9.8 2026-11-08 16:15 的下拉实测：登记通路是通的，坏的是「选中态」

用户点开第一行右侧 ▼，下拉完整列出了已拥有的切入（艾索德晋级技能切入-3、
无尽之刃晋级技能切入、突进的骑士领主、刻印符文的符文杀手、邦尼兔…，可滚动）。
**这直接把 `4CD` 与 2A 拥有表排除掉**：如果登记/拥有没进窗口，下拉会是空的。

同时库里 `slot 3 = 11016`（持久化成功），行仍显示「不朽之王晋级技能切入」＝职业默认。
再叠加一条独立推理：即便当年 4CD 行字节发的是折叠族，slot 3 的族号也等于 3，
本来就该解析成「艾索德晋级技能切入-2」——它也没有。**所以行名不由 4CD 决定**，
4CD 只喂下拉。

### 9.9 改动：18E 提到 635 之前

行显示的是「管理器当前的选中态」，而窗口是在 635 建窗那一刻按该状态**画**出来的。
之前两处 opener 的顺序都是 `4CD* + 635 + [4CC, 18E]`，18E 到的时候行已经画完；
这也解释了为什么「点一次定制适用」永远改不动任何一行——三条载波都发给了一个已建好的窗口。

现在改为 `4CD* + 18E + 635 + 4CC`（新增 `character_custom._split_notices()`，
18E 归 before、4CC 归 after）。城镇与副本两个 opener 同步。

受影响断言已同步：

- `test_character_custom_dungeon` 第 8 段：`[0x4cd]*rows + [0x18e, 0x635, 0x4cc]`；
- `test_character_custom_opening`：`[0x4cd, 0x18e, 0x635, 0x4cc]`；
- `dungeon_entry` 的进本爆发未改，仍是 `[0x4cd]* + [0x4cc, 0x18e]`。

四件定制测试 11 项通过。**生效条件：必须重新登录客户端**——实测本会话里客户端
只在 15:47:15 发过一次 634，之后关窗重开都不再发，窗口列表是那次建起来一直复用的。

### 9.10 根因（本轮最终）：18E 的键是「族」，值是「该族的全部档位」

重新登录后实测 `16:25:05 opener ok phase=dungeon owned=2902 slots=21 rows=21`
并带出真实字节 `bytes=1:1 2:2 3:3 4:4 ... 28:28`——**21 行的 4CD 行字节全部等于槽号，
活进程实测通过**。出站序列也确认变成 `4CD×21 → 18E → 635 → 4CC`。
但面板四行仍是职业默认 → **18E 的时序／4CD 的行字节都不是根因，两者都已排除。**

把族和槽列出来对比，答案就出现了：

| 族 | 槽 | 档位数 |
|---|---|---|
| 1 待机动作 | 1,10,11,12 | 4 |
| 3 技能切入 | 3,4,5,6 | 4 |
| 7 坐姿 | 7,8,13,14 | 4 |
| 20 快捷语音 | 20,21,22,23 | 4 |
| 24 表情 | 24,25,26,27 | 4 |
| **16 技能边框** | **16** | **1** |
| **19 头像** | **19** | **1** |
| 2 脸型 / 15 觉醒 / 28 徽记 | 各 1 个 | 1 |

用户从最早那次反馈起就只说「**就边框和头像生效**」——而 16 和 19 恰好是**唯一两个
「族号 == 槽号 且只有一档」**的类别。我们一直按「每槽一条、向量长度 1」发 18E：

- 单档族：这条的字节与「每族一条、向量长度 = 该族档位数」**完全相同** → 一直正确；
- 多档族：应当是一个键下挂 4 个 Info（档位顺序），我们却拆成了键 3/4/5/6 四条各 1 个 Info
  → 客户端按族取不到完整的档位向量 → 每一档都回落职业默认。

这同时解释了「待机动作页也不生效」：族 1 同样是 4 档。

### 9.11 改动

`protocol/character_custom_messages.py` 新增：

- `empty_info()`：未被选择的档位补一个 custom_id=0 的空元组；
- `family_selection(values)`：按 `selection_type(slot)` 分组，每族一个
  `byte 族号 + u32(该族档位数) + 按槽顺序的 Info`，未选的档位用 `empty_info()`。

`selected_notice()` 改用 `family_selection()` 取代原来的逐槽拼接。

**回归安全性已单独核验**：对 16 / 19 / 2 / 15 / 28 五个单档族，新旧编码逐字节相等
（`old==new : True`），所以目前唯二能用的边框和头像不可能被这次改动弄坏。
整体 18E 由 2128 字节 / 21 条变为 2150 字节 / 10 族。

受影响断言同步：`test_character_custom_dungeon` 第 6 段改为按族数断言，
`test_character_custom_apply` 第 4 段（槽 1/10/11/12 同属族 1）改为断言族数恒为 1。
四件定制测试 11 项通过。

`0x4CC` 仍按槽单发（它与客户端自己发的 `0x4CB` 同形，不能跟着改）。

## 10. 2026-11-08 16:47：根因确证——`0x4CD` 首个 i32 必须为 0（原生反汇编）

Frida 注入被客户端拒绝（`VirtualAllocEx` 返回 0x5），只能离线反汇编。做法：先定位
`Info` 元组的读取签名（`i32, i32, wstring, wstring, i32` 连续五次调用），扫出一个独立
`Info` 读取函数 `0xDA2C40`，再扫全映像的 5 处内联点，其中 **`0xBB7FA8` 起就是 `0x4CD`
的读取器**：

```
0xBB7FB2  read i32   → [rsp+0x50]      首个字段
0xBB7FC5  read byte  → [rsp+0x54]      行类型字节
0xBB7FD6  need(0x1c)
0xBB7FE9  read i32   → custom_id
0xBB7FFC  read i32   → ability
0xBB800F  read wstring → date1
0xBB8022  read wstring → date2
0xBB8034  read i32   → variant
0xBB804E  cmp dword ptr [rsp+0x50], 0
0xBB8053  jne 0xBB8328        ← 非 0 直接跳到收尾，什么都不做
0xBB80EF  call 0x11F2B10(管理器+0xDC8, &Info)   ← 只有 0 才走到这里
0xBB80F4  cmp byte ptr [rsp+0x54], 0x1C
0xBB80F9  jne 0xBB8328        ← 类型字节只和 0x1C(28=CT_POINT_MARK) 比较一次
```

结论：

1. **首个 i32 一直是道具模板 id（非 0），所以每一条 `0x4CD` 都在客户端被判为“跳过”，
   处理器照样返回成功。** 服务端发了几十个注册包，客户端一条都没存。
2. **行类型字节根本不参与选行**，只用于判断是否徽记那一族的额外分支。这解释了为什么
   “把折叠族改成槽号”这个方向实测完全无声——那一层本来就不是根因。
3. 边框页能列出 9 条边框，是因为它来自 2A 拥有表（`family 16 owned = 9`，与界面条目数
   完全吻合），不是来自 `4CD`。

改动：`registered()` 的 `item` 三处调用点一律传 `0`，并在函数内写明上述反汇编依据。
`tests/test_character_custom_opening` 里那条「模板 = 472284」的断言改为断言 0。
四件定制测试 11 项通过，16:47:35 热重载。

**仍然待验证**：`0x4CD` 的语义是“把这条加进已拥有的注册表”。若客户端确定“已选”时要求
该定制必须先在注册表里，那么它同时也能修好选择态；若不能，则剩下 `0x4CC`/`0x18E` 两条。
这一次改动是本轮唯一有原生证据支撑的，其余方向都已被实测排除。

## 11. 2026-11-08 18:40：`0x4CD` 被实测否定，选择态只能在登录 DTO 里

### 11.1 `0x4CD` 首字段改成 0 之后：四行仍是职业默认

`16:47:35` 热重载后重新登录，`18:32:10` 客户端发出唯一一次 `0x634`（72 字节帧），
服务端回执完整（`analysis/client-6c6b5180/20261108-183030/server-logs/server.jsonl`）：

```
18:32:10.637 client_request            0x634 size=72 seq=208
18:32:10.720 local_business_response   0x4CD size=168   x21
18:32:10.723 local_business_response   0x18E size=2232
18:32:10.723 local_business_response   0x635 size=72
18:32:10.724 local_business_response   0x4CC size=2112
```

`state/custom.log` 同时确认 `opener ok phase=dungeon ... rows=21 bytes=1:1 2:2 ... 28:28`
（每行行字节 == 槽号）与 `registered(item=0)`。**面板四行依旧职业默认。**

这一条把 §10 的假设也否掉了：`0x4CD` 不是选择态，`0x4CC` 也不是，`0x18E` 也不是。
再加 9.8 的下拉实测（下拉列出全部拥有的切入＝来自 2A 拥有表，不是 4CD），
`4CD` 整条通路对面板**完全无关**，可以从“选择态载体”的候选里划掉。

### 11.2 635 只有 8 个字节

`opening_information()` 的 payload 就是 `bytes(8)`（帧 72 = 64 头 + 8），
`#460` 的解析链也确认它是两条空的现金购买向量。**它装不下任何选择态。**
所以窗口建窗时能读到的每角色状态只剩登录 DTO（2A）。

### 11.3 2A 定制块的四格，只有 `+0x6B9` 能装选择态

`0xDA3370` 尾部的定制块（逐条反汇编核对，`0xDA34F0`–`0xDA3600`）：

| 结构偏移 | 读取函数 | 线缆形态 | 存储内容 |
|---|---|---|---|
| `+0x633` | `0xDB6E10` | 100+ 字节记录 | 未知（byte + u64 + 两个 wstring + …） |
| `+0x698` | `0xDB4110` | `u32` + `{i32,float}` | 装不下 id 列表 |
| `+0x6A8` | `0xDB2880`→`0xDD1EE0` | `u32` + 每族 `{byte,u32,Info×n}` | **已拥有**（下拉来源） |
| `+0x6B8` | `0x3B6D810` | 1 字节 | bool |
| `+0x6B9` | `0xDB6F10`→`0xDD7C30`→`0xDB1B00` | `u32 n` + 每项 `{i32 键, u32 m, i32×m}` | **`map<i32, vector<i32>>`** |
| `+0x6C9/-0x6DF/-0x6F5` | `0xDB6FA0` ×3 | `map` + byte + i32 + byte | 未知 |

`+0x6B9` 的结构是硬证据：`0xDB6F10` 先 `need(0x18)`，再把游标交给 `0xDD7C30`；
后者读 `u32` 计数（`0xDD7C60`），循环里读 `i32` 键（`0xDD7CD6`）后调 `0xDB1B00`；
`0xDB1B00` 是 `need(0x16)` + `u32` 计数 + 逐个 `i32`。**整块定制状态里，只有它能表达
“族 → 已选 id 列表”。** 而我们从第一版起就一直发 `u32(0)`（空表）。

### 11.4 改动

- `protocol/character_custom_messages.py`：新增 `selection_ids()`（族 → 该族按槽位的
  已选 id，未选档位补 0 保持位次）与 `dto_tail()`（`owned_map + \x01 + selection_ids`）。
  真实存档（owner 1001，21 槽 10 族）编码后 `rest bytes 0`、共 184 字节：

  ```
  fam 1  (11005,11008,11012,11008)   fam 2  (12106,)      fam 3  (11017,13055,13052,13047)
  fam 7  (11026,14107,11026,14186)   fam 15 (1000073,)    fam 16 (8012,)
  fam 19 (15211,)                    fam 20 (156048,156048,0,0)
  fam 24 (0,0,17033,17000)           fam 28 (19003,)
  ```
- `protocol/local_messages.py:235`：改为 `u32(0)+custom_dto_tail(character)`，并用
  **函数内 import**，这样以后调尾部不必重启。
- `gm_local_patch.py`：新增 `_reload_login_builders()`。`local_session` 在模块顶层绑定
  `player_initialization`，热重载名单永远治不到它；现在由已在名单里的 `gm_local_patch`
  重载 `local_messages` 并把新函数对象回填到 `local_session` 的模块属性上
  （`local_session` 是裸全局调用，所以回填即生效）。`state/gm-patch.log` 会记
  `login builders [...]`。
- 新增 `tests/test_character_custom_dto_tail.py`（7 项）：空选择与旧线缆逐字节相等、
  拥有表未被改动、单档族/多档族位次、同族两槽合成一键、两族两键、`player_initialization`
  末尾确实带上尾部。定制四件回归共 18 项通过。

### 11.5 环境事实（踩坑记录）

- `20261108-183030` 那个进程的**热重载监听线程已经死了**：`touch state/hot-reload.request`
  之后 `hot-reload.log` 不再追加、请求文件也不会被 unlink。判断方法就是看请求文件有没有被删。
  18:46:54 重新拉起整栈（`tools/launch_integrated_local.py --client …x2_dx11.exe`）之后
  `hot-reload.log` 马上出现 `forced …`，新进程的监听是活的。
- 上一栈其实是**用户自己关掉游戏**后才停的（`server.stop` 内容 `owned probe ended`），
  所以这次重启没有打断任何人。

### 11.6 实测结论：`+0x6B9` 也是错的（第 12 个被否掉的方向）

18:48:54 登录帧已经带新尾部（`dto tail owned=2902 slots=21 tail=278831`），
18:49:52 客户端确实开了一次面板：

```
18:49:52 opener ok phase=dungeon owned=2902 slots=21 rows=21 notices=2 bytes=1:1 ... 28:28
18:49:52 4CD×21(168) → 18E(2232) → 635(72) → 4CC(2112)
```

用户在 18:50:15 回复「你是修不好吗」，中间只隔 23 秒 —— 与前面每一次「实测无效」
后的反应一模一样。**据此判定 `+0x6B9` 也不是选择态载体。**

必须记下的弱点（在改之前就已经知道、但没能证伪）：偏移扫描全映像找 `+0x6B9` 的引用
只命中构造函数 `0x13F78B0`、析构函数 `0x1387210`、2A 读取器 `0xDA3370` 三处，
**没有任何消费者**。所以它很可能确实是死字段，这一改从一开始概率就不高。

### 11.7 到此为止，已被实测否定的方向（共 12 条，不要再试）

1. `0x4CD` 行类型字节（折叠族 → 槽号）
2. `0x4CD` 首字段（模板 id → 0）
3. `0x4CD` 的时序（635 前 / 后）
4. `0x18E` 按槽 vs 按族
5. `0x18E` 扁平化（去掉 `u32(1)` 包装）
6. `0x18E` 时序（635 前 / 后）
7. `0x18E` 选择子 selector = 1
8. `0x18E` 空表 → 全表复投
9. `0x4CC` 全表回执
10. 空 `0x4CB` 回显
11. 2A `+0x6A8` 拥有表（本来就是对的，只喂下拉）
12. 2A `+0x6B9` `map<i32,vector<i32>>`

同时已确认的事实：`0x635` payload 只有 8 字节（两条空现金向量），装不下任何选择态；
面板下拉的条目来自 2A 拥有表，与 `0x4CD` 无关；同一客户端进程只在登录后第一次开窗时
发一次 `0x634`。

**剩下的方法只有两条**：给客户端装真反编译器（Ghidra/IDA）读出「建行」函数的数据来源，
或拿一份别的服的登录 2A + 634/635 抓包做对照。继续按「猜一格 → 重登一次」的做法
已经没有胜率可言。

## 12. 2026-11-08 20:30–20:50：装了 Ghidra，把客户端定制系统整个拆开（第 13 轮，全部反编译实证）

工具链见 §13。这一节只记反编译读出来的事实，全部可复核。

### 12.1 客户端的定制类族（MSVC RTTI 解析）

| 类 | TypeDescriptor | 虚表 | 说明 |
|---|---|---|---|
| `CX2CharacterCustomizeSystem` | `0x47C8570` | `0x41C10C0`（80 槽，对象 0x1C0 字节） | 面板系统本体 |
| `CX2CharacterCustomizeItemView` | `0x47C8300` | `0x41C1100` | 面板行视图 |
| `IntCharacterCustom` | `0x47C8608` | `0x41C10E0` | 接口 |
| `CX2STXCharacterCustomizingSystem` | `0x4795FD0` | — | STX 脚本宿主 |

虚表里能对上的：
- `+0x08` = `0x11D9880`：`if (channel==0x202 && [this+0x20] && [this+0x239]==1) 0x11DD190()` —— 系统确实按 **0x202** 收事件。
- `+0x10`/`+0x18` = `0x11F4810` / `0x11F48D0`：Apply 发送端。`0x11F48D0` 按 `param_2`（槽号）`switch`，
  `FUN_143ae3a38(0x68)` 分配 **0x68 字节**的记录，`*(u16*)(p+3)=0x101`，两条长度 `0x13`(=19) 的日期串
  → 即 `Info` 记录是 **104 字节**结构，不是我们发的 16~92 字节裸拼。
- 析构 `0x11D6640` 释放 `0x3E0` 字节 → 另有一个 0x3E0 的对象（数据侧，非窗口）。

### 12.2 `0x635` 的载荷格式（`0x23AD020` 反编译，确定）

```
need(0x1c) && need(0x13)          // 帧至少 28 字节，否则整段跳过
u32 n1, i32 * n1                  -> 存 obj+0x2C8, 置 obj+0x2C4 = 1
need(0x13)
u32 n2, i32 * n2                  -> 存 obj+0x2E8, 置 obj+0x2E0 = 1
```
我们现在发 `bytes(8)`（`character_custom_messages.py:191`），`need(0x1c)` 直接失败 → 客户端把两个
列表都存成**空**。但注意：面板照样列出 21 行，所以 **这条大概率不是「行名不变」的根因**，不要拿它当第 13 次盲测。

### 12.3 `0x634` 开窗的真实行为（`0x23ACF70` 反编译，确定）

```
send(singleton+0xC0, 0x634)
结构 = new(0x10): { i32 0x635, u32 *(singleton+0x190) }
压进 singleton+0x198 的 vector
```
所以 `0x635` 是**客户端问、服务端答**的一问一答（客户端只带 1 个 u32 出去，服务端的答复是两条 i32 列表），
开窗本身只发一个空的 `0x634`。

### 12.4 `0x4CC` 的处理（`0xBB8370` 反编译，确定）

```
need(0x1c) -> read i32 (结果码) -> need(0x18) -> 读一个 map
-> 守卫 0x74FFA0(kind=0x4CC) -> 0x751120(singleton, 结果码, 1)
```
只处理结果码，**一个字都不写选择态**。与实测（改 4CC 无任何变化）完全一致。

### 12.5 客户端的每族数据表（字符串 + 引用定位，新）

EXE 里有一整组**数据表名**，并且全部由同一个函数注册：

```
0x11E6280  FUN_14125b4e0(loader, 表名, 解析函数)
  CHAR_CUSTOM_SKILL_CUT_DATA     0x41C90D8 -> FUN_14120BF60     (族 3 技能切入)
  CHAR_CUSTOM_HYPER_EFFECT_DATA  0x41C90F8 -> FUN_141203230     (族 15)
  CHAR_CUSTOM_SIT_MOTION_DATA    0x41C90A0 -> FUN_141205860     (族 7 坐姿)
  CUSTOM_ITEM_SOCKET_DATA        0x41C90C0 -> FUN_14120DD30
  CHAR_CUSTOM_SKILL_FRAME_DATA   0x41C9158 -> FUN_14120E8B0     (族 16 边框)
  CHAR_CUSTOM_PORTRAIT_DATA      0x41C9178 -> FUN_1412103C0     (族 19 头像)
  CHAR_CUSTOM_QUICK_VOICE_DATA   0x41C9118 -> FUN_141212280
  CHAR_CUSTOM_EMOTICON_DATA      0x41C9138 -> FUN_141213550
  CHAR_CUSTOM_POINTMARK_DATA     0x41C9028 -> FUN_141214BB0     (族 28)
另有  CUSTOMIZING_TYPE(0x41C98E8) 由 0x1213550 使用；
      STX 脚本函数名 _CustomizeSearch_STX / _SelectCustomizeItem_STX /
      _OnlyAcquiredCustomize_STX(0x42A72F0) / _MouseLBDownCustomizeMeshRenderArea_STX 由 0x242BC90 使用。
```

**含义**：行内容（名字/图标/能否选）来自客户端**自己的每族数据表**，键是 `CUSTOM_ID`；
`_OnlyAcquiredCustomize_STX` 说明「只显示已获得」是脚本层的一个开关。
这解释了为什么改 4CD 的行字节只影响下拉、不影响行名。

### 12.6 下一步（唯一还没定位的环）

> 「每族当前选中值」存在哪里、由谁写入。

拿到它，就能判断 `0x18E` 该写哪个字段；拿不到就不要再发包盲测。
候选入口：`0x11DD190`（0x202 事件处理）、`0x11E6280` 的 per-entry 结构、
以及 `0x11D9880` 里那个 `[this+0x239]` 开关。

## 13. 2026-11-08 21:20–21:40：§12.6 的环补上了（第 14 轮，全部反编译 + 日志/DB 双证）

### 13.1 方案 A（调试器）被证明不可行——不是工具问题，是客户端自保护

实测（同一个 Python 进程，同样调用，explorer.exe / svchost.exe 全部正常作对照）：

| 调用 | `x2_dx11.exe` | 对照 explorer.exe |
|---|---|---|
| `OpenProcess(ALL_ACCESS)` | 成功，句柄有效 | 成功 |
| `NtReadVirtualMemory(0x140000000)` | `0x8000000D` STATIC_PARTIAL_COPY，0 字节 | 正常 |
| `NtReadVirtualMemory(自己的 PEB)` | 失败 | 正常 |
| `VirtualQueryEx(任意地址)` | `n=0 err=5` | `n=48 err=0` |
| `EnumProcessModulesEx` | `err=299` | `n=2264` |
| `DebugActiveProcess` | **`err=5` 拒绝** | — |

启用 `SeDebugPrivilege` 只把 `5` 变成 `299`，拿不到任何数据。原因：

- `data/xigncode/x3_x64.xem` / `xmag_x64.xem` / `xcorona_x64.xem` + `xigncode.log`（21:20 仍在写）
  = **XIGNCODE3（Wellbia）**；内核模块 `xhunter2`（`\??\C://windows//xhunter2.sys`，Manual，Running）。
  这是拦截 `NtReadVirtualMemory` / `NtQueryVirtualMemory` / `DebugActiveProcess` 的东西。
- 客户端本体还是 **Themida 加壳**：节表有 `.themida`（`va=0x4BAD000 vs=0x10FE000 rs=0`）与
  `.boot`（入口 `EntryRVA=0x5CAB058` 落在其中），前 6 个节名被清空，
  `data/secureenginesdk64.dll` 就是 SecureEngine SDK。
  这解释了 `CHAR_CUSTOM_SKILL_CUT_DATA` 在磁盘 exe 里搜不到——它位于节 1 的 BSS 区间
  （`delta=0x3210D8 > SizeOfRawData=0x2CEA00`），**运行时才解密**。
  所以 `x2-runtime.bin` 是已解包的完整映像，其 RVA 全部可信；对它做静态分析永远有效。

**结论：x64dbg / Cheat Engine 一律进不去，方案 A 作废，不要再花时间。**

### 13.2 踩坑：这份转储必须按「文件偏移 == RVA」读

`x2-runtime.bin` 的节表保留了磁盘上的 `PointerToRawData`（`.text` 是 `0x600`），
但转储本体是扁平的。任何按节表换算 `RVA -> 文件偏移` 的脚本都会整体偏移 `0x600`，
解出来的指令看似合法、实则全错（本轮 `sweep.py` 第一版就是这样，导致 59 个候选里
绝大多数是假命中）。**`rva2off()` 必须直接返回 `rva`。**

### 13.3 §12.6 的答案：`+0x270` 是 `CX2CharacterCustomizeSystem` 的「已登记定制项」vector

用「同一偏移组」做交集定位类，而不是单看 `0x270`（它太常见，单看必然假阳性）：

```
sweep.py 对 119524 个 .pdata 函数从函数起点对齐线性扫描
  取「同时引用 0x270 且 0x578 且 0x598」的函数 -> 59 个
  其中落在定制模块（0x11D0000-0x1230000）的只有 3 个
```

| 地址 | 作用 | 证据 |
|---|---|---|
| `0x11E5320` | 构造函数 | `*obj = &0x41C10C0`（正是 §12.1 的 `CX2CharacterCustomizeSystem` 虚表）；把 `+0x270/+0x278/+0x280` 清零；`lea rcx,[rdi+0x578]`、`lea rcx,[rdi+0x598]` 构造两个 map |
| `0x11E5C80` | 析构函数 | 反向销毁 `+0x598`/`+0x578`/`+0x270` |
| `0x11F48D0` | Apply（虚表 `+0x18`） | `mov rbx,[r14+0x270]` / `cmp rbx,[r14+0x278]`（`r14`=this），族 3–6 在此线性查 id；族 15/16/19/20–23 走 `+0x578`/`+0x598` 的 map |

元素布局（`FUN_1411f2b10` 与 `FUN_1411f2c00` 交叉核对，步长 `0x13` 个 int = **76 字节**）：

```
+0x00 i32            custom_id（key，Apply 就是拿 param_3 比这一格）
+0x04 i32            ability
+0x08 std::string    date1      (16 字节内联缓冲 + size@+0x10 + cap@+0x18)
+0x28 std::string    date2
+0x48 i32            variant
```

**与 `character_custom_messages.info()` 发出的顺序逐格相同**（`>ii` + `_text(date1)` + `_text(date2)` + `>i`），
所以 Info 的线缆形态这条是对的，不要再改。

### 13.4 写入者只有一个：`0x4CD`，且首个 i32 必须为 0

`FUN_140bb7f30`（0x4CD 处理器）：

```c
if ( need(0x1c) &&
     read_i32(&flag) && read_byte(&CT) && need(0x1c) &&
     read_i32(&id) && read_i32(&ability) &&
     read_wstring(&date1) && read_wstring(&date2) )
{ read_i32(&variant); }

if (flag == 0) {                                  // ← 没有 else 分支
    ... 组 record ...
    FUN_1411f2b10(singleton + 0xDC8, &record);    // push 进那个 vector
    if (CT == 0x1c) { ... 族 28 点位标记的额外处理 ... }
}
```

函数尾部就是 `if (flag == 0) {...}` 之后直接进清理返回，**`flag != 0` 时整条记录被静默丢弃**，
处理器仍然「成功」。所以 §10 的结论是对的，而且现在有了「为什么」：
`flag` 非 0 不是「换一种语义」，而是**什么都不做**。

`CT` 字节只与 `0x1C`(=28) 比较，从不参与选行——§11.1 里把行字节在「折叠族 / 槽号」之间换来换去
毫无反应，原因就在这里。

### 13.5 重要更正：`0x4CD` 修好之后，**Apply 确实是通的**

§11.1 否掉 `0x4CD` 用的是「面板四行仍显示职业默认」，那是**行标签**观察；
`+0x270` 决定的是**「应用」能不能通过查找**，两个症状不同，不能用同一个观察否定。

`state/custom.log` 里有直接证据（`item=0` 在 16:47 生效之后）：

```
18:48:28 apply slot=3 cid=83022 row=3 ack=105 notice_slots=2
18:48:28 apply ok (dungeon) slot=3 custom=83022 replayed=False
```

`slot=3` 就是技能切入族，客户端**发出了** 0x4CB，服务端接受。这说明 `+0x270` 的成员查找成功了。
`state/development.sqlite3` 的 `character_custom_permanent_selection_slots` 也确认四个切入槽全部落库：

```
slot=3 11017   slot=4 13055   slot=5 13052   slot=6 13047
```

**所以「应用不生效」已经不是当前故障；剩下的是「客户端渲染/显示用的选择态」。**

### 13.6 本轮改的代码（2 处，still-broken 的真实 bug）

用道具书解锁的路径仍在往首字段塞真实模板 id，那两条登记一直被客户端丢弃：

- `storage/character_custom.py:194`（回执重放）：`wire.registered(value, before[0]['template'])` → `wire.registered(value, 0, family=rules[before[0]['template']]['slot'])`
- `storage/character_custom.py:211`（首次解锁）：`wire.registered(value, source['template'])` → `wire.registered(value, 0, family=rule['slot'])`

注意 `family` 必须取 catalog 规则的 `slot`，不能取库存记录的 `slot`（那是背包格号，会触发
`SLOT_TYPES.get(family)!=base` 校验）。

### 13.7 下一个唯一未解的问题

> **客户端「显示/渲染」用的每族已选项，到底从哪条消息来？**

已知它**不是**：`+0x270`（那是可应用集合，已验证能通过 Apply）、`0x4CC` 的结果码、
`0x635`（8 字节，装不下）、`+0x6B9`（§11.6 单改无效）。
`0x18E` 的形态已被试过 5 种（按槽/按族/扁平化/时序/selector），全部无效。

下一步不要再盲测。可做的是给它装**出站包全量落盘**（现在只有 `_trace` 的摘要），
拿「一次干净的开窗 + 一次应用 + 重开」的完整字节流，与官方/别服抓包做逐字节对照。
或者：在 `x2-runtime.bin` 上反编译 `0x18E` 的**消费端**（`0x30C39E0` 分发点之后的处理函数），
看它把每族选择写进哪个成员——这是纯静态、必然有答案的一条。

### 13.8 `0x18E` 的真实字段表（反编译到底，`0xC4E700` → `0xDD46E0` → `0xD9A550`）

§12 记的「0x18E 键是族、每族一个 Info 向量」是**错的**。按 `0x30C39C0` 的分发确认
（`030C3A08 cmp rbx,0x18e` / `030C3A15 je 0x1430C4154`），`0x18E` 走的是：

```
030C4154  lea  rcx,[rsp+0x60]      ; 栈上构造载荷对象
030C4159  call 0xC832F0
030C4167  call 0xC4E700            ; 反序列化
030C417B  call [rax+0xC8]          ; 交给 [rsi+0x648] 的虚函数
```

`0xC4E700` 的读取顺序（偏移是 **packed 结构**，所以出现 `+0x01` 这种奇数偏移）：

| 偏移 | 读取器 | 线缆形态 |
|---|---|---|
| `+0x00` | `0x3B6D1E0` | **u8** |
| `+0x01` | `0x3B6D7A0` | **8 字节裸读**（u64） |
| `+0x09` | `0xDD46E0` | **`vector<0x408>`**：`u32 count` + 每项见下 |
| `+0x21` | `0xDB07E0` | `need(0x1c)` + **7 × u32** |
| `+0x3D` | `0xDB07E0` | `need(0x1c)` + **7 × u32** |
| `+0x59` | `0x3B6D340` | i32 |
| `+0x5D` | `0xDB2880` | 拥有表 map（与 2A `+0x6A8` 同一读取器） |
| `+0x6D` | `0x3B6D810` | u8 |
| `+0x6E` | `0xDD25B0` | 622 字节对象 |
| `+0x86` | `0xDB2910` | `need(0x18)` + 容器 |
| `+0x96` | `0xDB29A0` | `need(0x1c)` + i32,i32,?,? |
| `+0xA7` | `0x3B6D420` | u32 |

`vector<0x408>` 的单个元素（`0xDD46E0`）：

```
+0x000  u64   (8 字节裸读)
+0x008  u8
+0x009  u16
+0x00B  FUN_140D9A550 -> need(0x1c) + 0xD9A550   ; 0x3EC 字节的角色定制块
+0x3FF  u8
+0x400  u64   (8 字节裸读)
```

`0xD9A550`（1138 字节，就是 2A 那套角色 DTO 的同款）尾段有**两组 7 个 i32**：

```
need(0x1c); u8(+0x3b0) u8(+0x3b1) u8(+0x3b2) u8(+0x3b3)
need(0x1c); i32(+0x3b4) i32(+0x3b8) i32(+0x3bc) i32(+0x3c0) i32(+0x3c4) i32(+0x3c8) i32(+0x3cc)
need(0x1c); i32(+0x3d0) i32(+0x3d4) i32(+0x3d8) i32(+0x3dc) i32(+0x3e0) i32(+0x3e4) i32(+0x3e8)
先 u8 检查 0x21，再 u8 检查 3 / 3        ; 长度校验
FUN_140DAEC10(+0x3ec)
```

### 13.9 结论：服务端发的 `0x18E` 从**第 0 个字节**就是错的

服务端现在发：

```python
struct.pack('>QII', uid, kind, title) + family_selection(values)
#                u64   u32   u32           u32 count + {byte family, u32 n, Info×n}
```

而客户端第一个动作是 `need(0x1c)` → `read_byte(+0x00)` → 8 字节裸读 `(+0x01)`。
**两边从第 0 字节起就错位**：客户端会把 uid 的高 7 字节当成 `u8`+`u64` 的一部分，
后面的 `vector` 计数、两组 7×u32、map 全部读错，`0xC4E700` 在第一个不满足的
`need/read` 处直接返回，对象保持默认。

这正好解释了 §11.7 里那个诡异现象：**0x18E 试过 5 种形态（按槽 / 按族 / 扁平化 /
时序 / selector）全部毫无反应** —— 因为前缀从来就没对上，后面怎么改都到不了。

### 13.10 下一步（两个可选，都不靠猜）

1. **停发 `0x18E` 做差分**：既然它现在是「一定读失败、然后把默认值套到目标演员身上」，
   它本身可能就是面板被打回职业默认的元凶。把 opener 里的 18E 去掉跑一次，
   面板行为有没有变化就能定性。风险极低、可立即回滚。
2. **按上表实现完整的 `0x18E`**：字段顺序已经全部拿到，缺的只是每个 i32 的语义
   （尤其 `+0x3b4..+0x3e8` 那两组 7 个 i32 —— 目前最像「每族已选 id」的候选）。
   要定语义，需再从 `0xD9A550` 的**消费端**（谁读 `+0x3b4` 等偏移）反推一轮。

---

## 14. 已实施：默认停发 `0x18E`（2026-11-08 21:5x）

按 13.10 的第 1 条执行。理由不是「赌它会好」，而是它**今天不可能成功**：
`0xC4E700` 在我们这种前缀下必然在第一个 `need/read` 处返回，对象保持默认，
紧接着 18E 分支把这个默认对象交给目标演员的 `[vtable+0xC8]`——
每一次通知都在**把外观刷回职业默认**。所以停掉它的结果只可能是「没变化」或
「变好」，不存在变差；而且是一个环境变量就能开回来的开关。

### 14.1 改动

| 文件 | 改动 |
|---|---|
| `els_server/protocol/character_custom_messages.py` | 新增 `_ENABLE_18E_NOTICE = os.environ.get('ELS_ENABLE_18E_NOTICE','0')=='1'`；`selected_notice()` 关闭时 `return None`；文件头注释记录 13.8/13.9 的结论 |
| `els_server/domain/character_custom.py` | 新增 `_live(events)` 过滤 `None`；`_split_notices()` / `_dungeon_custom()` / `restored()` / `_window_rows()` / dungeon opener 分支全部先压实再拼帧 |
| `els_server/storage/character_custom.py` | Apply 事件列表里 18E 改为「可选追加」，`events[0]`(4CD) / `events[1]`(4CC) 的索引保持稳定，追踪日志不会因开关而错位 |

`family_selection()` / `info()` / `selection_map()` **一行没动**：开关只是不发这条帧，
一旦 13.10 的第 2 条做完，改的是 `selected_notice()` 里的拼装顺序，其余全部复用。

### 14.2 一个必须记住的坑：`encode_event(None)`

`_window_rows()` 在返回前会拿 `registrations+notices` 逐个 `encode_event()` 做自检
（防止坏帧把整个 635 回复带走）。第一版改动里 `notices` 里带着 `None`，
自检抛 `TypeError`，被外层 `except Exception` 吞掉，函数返回 `([], [])` ——
**窗口会连 4CD 注册一起丢掉，退回「所有行都是职业默认」的最坏状态**。
所以凡是拼进 `encode_event()` 或 `+` 运算的列表，必须在拼之前就压实
（`notices` 保持 `list`，不要图省事换成 `_live()` 的 tuple，`list+tuple` 同样会炸）。

### 14.3 测试

`tests/test_character_custom_apply.py` / `_dungeon.py` / `_opening.py` 三条用例从
「18E 默认存在」改成「18E 默认不存在」，并各自新增一段 `patch.object(wire,
'_ENABLE_18E_NOTICE', True)` 的用例，把**旧形状逐字节钉住**（uid、selector=0、
按族分组、family 计数在 `payload[16:20]`、首条 Info 的 `custom_id` 在 `payload[25:29]`、
4CD→18E→635→4CC 的顺序）。开关不是「删掉的功能」，是留给抓包对照的工具，
所以它的形状仍然要受回归保护。

结果：`tests.test_character_custom_apply` + `_dto_tail` + `_opening` + `_dungeon`
+ `_all_books` 共 18 项全绿。

### 14.4 待实机确认

服务端需重启（模块级开关在 import 时求值）。观察点，按信息量排序：

1. `state/custom.log` 里 `opener replay ... slots=N` 与 `apply ok ...` 是否照常；
2. 面板四行是否还掉回职业默认 —— 若**不再掉**，说明 13.9 的判断成立，
   18E 的消费端确实在覆盖，届时 13.10 第 2 条才有做的价值；
3. 若毫无变化，说明面板行另有来源（更可能在 2A 的 `+0x6B9` 与 4CD 的组合上），
   18E 就只保留开关、不再投入。

---

## 15. 定稿：当前版本＝已知最好状态（2026-11-08 22:15）

决定停止继续试探，把这一版作为交付版本。判断标准很简单：
**每条改动都有实测或反编译证据支持，没有一条是"猜的"；被证伪的全部清掉。**

### 15.1 现在确实能用的

| 能力 | 证据 |
|---|---|
| 打开定制面板不报错、不卡 | `state/custom.log`：`opener ok rows=21 notices=1` |
| 点「应用」被接受并落库 | `apply ok slot=28 custom=19003` / `slot=1 custom=11033`；DB 里切入四槽 11017/13055/13052/13047 全在 |
| 选择在重启、回城后保持 | 同一批 `character_custom_permanent_selection_slots` 行 |
| 面板下拉能列出已拥有的道具 | 之前截图已确认（`+0x6A8` owned map 解析正确） |
| 每行按自己的槽号登记，不再串到第 1 格 | `rows=1:1 2:2 3:3 4:4 5:5 6:6 … 28:28` |
| 注册帧首字段为 0，客户端不再静默丢弃 | 反编译 `0xBB7F30`：`cmp [rsp+0x50],0 / jne epilogue` |

### 15.2 仍然不行的（如实记录，不再假装修好）

1. **面板里多格族（技能切入 4 格、待机动作 4 格、表情等）行标签仍显示职业默认。**
2. **副本里放技能，选的切入画面不出现。**

两条同源：客户端"显示/使用某一族里第几个"的那份数据，我们没找到正确的载体。
已用实测排除的候选（12 条，见 §11/§13）：4CD 行类型字节、4CD 首字段、4CD 时序、
18E 按槽/按族/扁平化/时序/selector、4CC 全表回执、空 4CB 回显、2A `+0x6A8`、2A `+0x6B9`。

### 15.3 这一版的取舍

- `0x18E` **默认不发**（`ELS_ENABLE_18E_NOTICE=0`）。理由：反编译证明它从第 0 字节就解析失败，
  失败后会把默认对象套到目标演员上——即每条通知都在把外观刷回默认。不发只可能"没变化"或"变好"。
- `family_selection()` / `info()` / `selection_map()` 原样保留：开关打开即可恢复旧行为，
  将来按 §13.8 字段表重写 `selected_notice()` 时，其余全部可复用。
- 想要旧行为对照抓包：`set ELS_ENABLE_18E_NOTICE=1` 后重启服务端。

### 15.4 回滚

三个文件独立可回滚，互不牵连：
`els_server/protocol/character_custom_messages.py`、`els_server/domain/character_custom.py`、
`els_server/storage/character_custom.py`。服务端开着热重载，改完 1 秒生效，不用重启。

### 15.5 如果以后还要继续（给下一位的入口）

不要再从"扫全图找 +0x270 的访问者"开始——已证明那条路会产出 263 个噪声候选。可行入口只有两个：

1. **动态**：需要先解决 XIGNCODE（`.xem` 改名实测进不去游戏，已还原），否则拿不到"建行那一刻读了谁"。
2. **静态**：从 `.rdata` 里找出 kind→handler 的跳转表（客户端不是用 `cmp imm32` 派发的，
   所以按立即数扫描必然 0 命中），再顺着 0x635 的 handler 找窗口对象。
