# 早期地域BOSS宝箱（10 箱）

补齐 130159/130160/130161/130162/130645/131262/133471/160662/160774/162020 十只地域BOSS宝箱的原始奖励表。此前这十箱在 0x559 预览阶段一律返回零条目，客户端按 2271D30 的既有行为显示「该角色无法使用该道具」，表现为双击无反应。

## 证据链

奖励内容取自官方概率公示 `elsword.nexon.com/News/Probability/View?n4ArticleSN=225`，该页逐一列出 13 个地域BOSS箱的道具与百分比（罗本→艾丽西昂 10 箱，外加已实现的艾丽阿诺德/帕尼米尔/尼格摩尔）。韩文道具名与客户端模板号按**位次**绑定：

- `RandomItem.lua` 中十箱的 `m_iItemGroupID` 依次为 60343..60352，与公示表的区域顺序严格同序，且每箱另有一条 +10 的平行组（60353..60362）；
- 客户端目录 30xxx 段的「(旧)」副本 30001..30078 与公示表前 33 项**逐条同序同名**；
- 正式段 30163..30196、30247..30274、30329..30365、30426..30576 与本表逐项对应。

生成器在落盘前强制校验：各区域条目数、模板号递增、区域块递增、组号间隔恒为 10、权重合计 10000、各区域首项锚点中文名。任一不符即拒绝生成。

## 变更

- 新增 `els_server/data/regional_boss_cubes_legacy.json`（10 定义 / 86 产物），SHA 锁定；源件 225 公示与 RandomItem.lua 各自 SHA 锁定。
- 新增 `els_server/domain/regional_boss_cubes_legacy.py`：冷读校验 + `catalog()`。
- `domain/cubes.py`：并入上述 10 条，重复模板即报错。
- `domain/acquisition_policy.py`：`can_acquire`/`require_acquirable` 增加 `regional_cube_source`，**仅授权该箱 entries 内的模板**；箱外模板仍拒绝。既有 2295 件 `compatibility_only` 饰品此前无任何已注册来源，本箱即为该来源。
- `storage/inventory_state.py`：`validate_plan`/`grant_items` 透传来源，并与既有 cartridge/fish 来源互斥。
- `storage/fixed_cubes.py`：`grant_items` 传入来源；开箱 `option` 由 `!=0` 放宽为 `{0,1}`——会话 20261025-140312 显示 313105/313107 以 0 确认、成长装备箱（uid 1001089）与复活石箱以 1 确认，奖励与 option 无关。
- `storage/known_resurrection.py`：同一放宽（该箱回执是计数而非道具列表，客户端空对话框确认时送 `option=1`）；`>1`、任何选项向量、非法 flag 仍拒。
- `tests/test_regional_boss_cubes_legacy.py`：新增。逐条开完 10 箱的全部 86 个产物（权重边界、重试不重掷、失败与外来 owner 回滚、0x559/0x196 走原生会话）。
- `tests/test_advancement_cube_coverage.py`：新增。把 9 只转职晋级宝箱钉为「未知即拒且不消耗」。
- `domain/story_controller_retirements.py` + `tests/test_lithia_memory3_retirements.py`：MEMORY5 场景退役规则与断言（`discover -p "test_lithia*.py"` 38/38）。
- `els_server/transport.py`：只为 `0x559` 预览与 `0x196` 开箱追加**已解析字段**的诊断记录（template/keys/flag、uid/choices/option，解析失败记 `parse_error` 与长度），不落原始字节。该文件按 `AGENTS.md` 属维护者协调核收范围，本处的改动是为定位本轮开箱取证，可在不影响功能的前提下单独回退；如维护者不接收，只需还原这 20 行。

## 可携带检查

```powershell
python -B -X utf8 -m unittest tests.test_acquisition_policy tests.test_fixed_cubes tests.test_regional_boss_cubes tests.test_known_resurrection_current -v
```

本机必须用仓库自带的 `els-server-collab\python\python.exe`（3.13.16，含 pycryptodome）；系统 `python` 是 WindowsApps 占位、`.workbuddy` 那份缺 `Crypto`，都会在 `protocol_codec` 的 DES 导入处报 `ModuleNotFoundError: No module named 'Crypto'`。

上述 27 项现为 27/27 OK。其中 `tests/test_fixed_cubes.py` 的 `test_large_native_quantity_splits_into_real_stack_limits` 在本项之前就是红的：它按 99 上限断言 300 个火之水晶球要拆成 4 堆、回执 5 个位点，而 2026-10-18 的堆叠策略已把普通可堆叠道具上限统一到 999（`domain/inventory_items.py` 末段），`tools/local_stack_limits.py` 再按同一张表给客户端镜像打补丁；本轮线上取证所用镜像的快照 SHA `3cc9fca4…` 正是该工具的锁定值，所以单堆 300、回执 2 个位点才是原生消费者的实际行为。用例已改名 `test_large_native_quantity_respects_the_pinned_stack_cap`，上限改为从 `TEMPLATE_MAX_STACKS` 现读、堆数与位点数按上限推导，不再写死已经漂过一次的字面量。**这一条是与本项无关的既存测试失配，维护者可单独拆 Issue；同一失配也造成 `tests/test_inventory_rewards.py` 的 `Full bag grant accepted`（该脚本用 `tempfile` 独立库，不触碰玩家存档）。**

基线对照方法：`git archive HEAD` 导出到 `D:\tmp\els_head` 并补上未随 Git 附送的 `analysis/` 取证目录（缺它会在导入期制造与改动无关的 `FileNotFoundError`，第一次对照就被这一点污染过），两侧都用 `discover -s tests -t tests` 同名单跑：

| 分组 | 基线 | 当前 |
|---|---|---|
| `test_*cube*` | 18 项 / 1 失败 | 25 项 / 全绿（+7 为本项新增用例，1 项为上面那条失配被纠正） |
| `test_*retirement*` | 36 项 / 4 失败 | 41 项 / 3 失败（+5 为 MEMORY5 用例；`test_lithia_memory3_retirements.test_relaxation_is_declared_on_35270_only` 由本项 RULES 改动转为通过；其余 3 条逐名相同） |
| `test_inventory*` | 30 项 / 7 错 | 30 项 / 7 错，失败名逐条相同 |
| `test_local_session*` | 1 项 / 1 错 | 1 项 / 1 错，相同 |
| `test_growing_adventure_kit*` / `test_known_resurrection*` | — | 3 绿 / 5 绿 |

结论：本项未新增任何失败。全量 `discover -s tests -t tests` 在本环境不可当门禁——`docs/TESTING.md` 已说明历史脚本用例依赖未附送的抓包与存档；本侧全量为 741 项 / 30 失败 / 139 错误，基线侧因 `state/` 不在导出内不可直接比字，故只作上表同名分组的对照。

`tests/test_lithia_memory5_retirements.py` 与同族用例沿用「兄弟模块裸名导入」写法（`from test_tunnel_native_retirements import …`），只有在 `discover -s tests -t tests` 形式下才可导入；用 `unittest tests.<模块>` 直接点名会报 `ModuleNotFoundError`，那不是缺陷。该形式下 `discover -p "test_lithia*.py"` 为 38 项全绿。

`tools/ci_checks.py` 为 `ok: true`（1663 个受版本控制的文件、973 个源件编译、协议回环、无 owner 数据）。`--with-runtime` 以 `CI must not create a player database` 收尾，因为本机已存在 `state/development.sqlite3`；这是环境前提而非代码失败，未删除也未改写该存档。

## 边界

客户端 `RandomItem.lua` 把分支 15（unit_type 15，莉缇娅）指向平行组（主组 +10）；该池不在公示范围内，本项不臆造，仍下发公示池——产物均为职业无关饰品。自然界面、组队/副本掉落、其余未开箱（109999/300645/135666/190926/313104）未因此通过。新增 JSON 是服务端来源合同，不是客户端完整资源表。

转职晋级宝箱（1/2/3 转、新的力量：原力、[阿莉尔]白境机甲防具、[科宝]1/2/3 转与超越转职纪念，共 9 只）仍保持拒绝：`RandomItem.lua` 只给「箱→组号」，本地没有任何「组号→道具+权重」的表——`els_server/data/client/catalog.sqlite3` 的 `rules` 段共 16773 行，抽取到的只有 `AddRandomItemTemplet`/`…_Templet_Client` 两类调用（各 8378 条），零条组内道具记录；已提取的 `analysis/sol-high-20261015/npc-bank-box/RandomItem.lua.tables.json` 同样是 16756 条纯映射。未知保持未知，开箱继续拒发且不烧实例，由 `tests/test_advancement_cube_coverage.py` 钉住。

成长装备箱（168889）与本次 `option` 放宽的联动已在本地按职业复现：`unit_class` 11（family 1，大剑）与 17（family 4，长剑）各跑 `option=0` 和 `option=1` 四组，均为 0xad8+0x197 回执、箱实例消失、按 `outputs_for` 发出 5 件且强化位为 +7。这是本地存储层取证，不等于线上原生确认；`tools/ci_checks.py` 未覆盖该路径。

状态：本地验收（含上表同名分组对照与 `ci_checks`）已在本轮完成；线上原生开箱/预览确认仍未做，需要维护者或业主在联调频道按 `option=0/1` 两类箱各 witness 一次，再由维护者按 Issue/分支/PR 流程独立提交。服务端与客户端的重启由业主执行，本副本未启动任何进程。
