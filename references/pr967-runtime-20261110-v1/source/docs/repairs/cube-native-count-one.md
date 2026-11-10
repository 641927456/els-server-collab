# 箱子点了没反应：原生 Count1 被共享数量闸门挡掉

背包里的箱子（`bag_group=4`）双击后既不开箱也不发奖，有的还弹一个只有「确认」的空白框。原因是**客户端原生「使用」按钮把数量当最后一个 i32 发过来，值是 1**，而 `els_server/storage/fixed_cubes.py` 只认 0：

```python
if request.option!=0 and not(request.option==1 and row['selection_count']==1):
    raise ValueError('Unsupported fixed cube quantity')
```

`selection_count==1` 只对「选择箱」成立。成长冒险家整套箱 `168889` 的 `selection_count=0`，于是 `option=1` 直接落到 `Unsupported fixed cube quantity`，`open_cube` 抛错，上层按 `0x197 code=-1, rewards=0` 回包。

## 证据

`state/wire-debug.log` 里同一晚的两种结果只差最后一个字节：

| 时间 | 0x196 载荷尾部 | 服务端 0x197 | 结果 |
| --- | --- | --- | --- |
| 18:57:15 | `...00000000`（option=0，模板 723168） | 1872 B | 正常发奖 |
| 18:53:05 / 18:56:30 / 18:59:22 / 19:00:05 / 19:00:50 | `...00000001`（option=1，uid 1001075=`168889`） | 104 B | `code=-1`，静默拒绝 |

`use_request` 的布局是 `>QBBBI`（uid、3 字节标记、选择集长度、选择集、i32 option），19 字节且 `n=0` 时 option 就是末尾 4 字节。`1001013`（`980047`，4 个）11:04:11 那次发的是 `option=4`（批量），同样被拒。

## 修法

闸门改为接受原生单箱的两种写法，批量与负数继续拒绝——一次点击绝不能多扣箱子：

```python
if request.option not in (0,1):
    raise ValueError('Unsupported fixed cube quantity')
```

这正是上游 issue **#655「成长冒险家整套箱168889拒绝原生单箱数量Count1」**（已关闭）的结论，本地仓库里 `references/growing-kit-count-one-20261031-v1/portable/` 就放着那份补丁，只是从未装进 `els_server/storage/`。便携补丁基于旧树，会顺手删掉本地新增的 `job_reward_boxes` 分派，因此只取数量语义、保留分派。

`storage/fixed_cubes.py` 不在热加载白名单里。`session_dispatch` 增加 `_CUBE_KINDS=(0x196,0x559)`，在链首用既有的 `_live()` 按 mtime 刷新该模块，修复对下一次点击立即生效，不掉线：19:07:38 装载成功。

## 验证

`D:/tmp/verify-cube.sqlite3`（`state/development.sqlite3` 副本）用线上真实载荷 `00000000000f46730000000000000000000001` 复现：

- 改前：`ValueError: Unsupported fixed cube quantity`
- 改后：`0xad8`(1948 B) + `0x197`(2019 B)，`code=0`，`entries=5`，箱子被消耗，入包 `11030166` 大剑与 `11030162/163/164/165` 上衣·下衣·手套·鞋子（强化 7，职业 152）

`tests.test_cube_single_count_current` / `test_fixed_cubes` / `test_growing_adventure_kit_current` / `test_pet_auto_flow` / `test_hot_reload` 共 23 项通过，`python -m els_server --check` 退出码 0。

`tests/test_regional_boss_cubes_legacy.py` 有两处把 `option=1` 当非法值（并发重放守卫、失败回滚扫描），改用 `option=2` 保持「批量不二次授权」的原意。该文件另有 2 项失败（`answer[-1].kind` 得到 577 而非 0x197；陈旧会话被误判成功）在本次改动前就存在，与箱子无关。

## 仍未修

- `980047 晋级时装（15日）宝箱`（4 个）**没有任何入口**：`cubes.catalog()`、job/promotion/teacher 各箱目录都不含它。客户端 `RandomItem` 模板是 `UC_ONE_CLASS`，按 194 个职业映射到 `m_iItemGroupID` 80017882..80183249，但该组的成员表本地没有——`els_server/data/client/catalog.sqlite3` 只收了 17 个资源、`ice-resources` 只解出 `AddRandomItemTemplet`，缺 `RandomItem` 的组定义。不猜数据就无法实现，需先从 `E:\游戏\艾尔之光\data` 解出组表。
- 同一类隐患：`job_reward_boxes`、`promotion_reward_boxes`、`teacher_elixir_boxes`、`white_armor_boxes`、`furniture_boxes`、`potion_choice_box`、`wardrobe_ticket_box`、`raid_reward_actions`、`boosting_2026_*` 等入口都写死 `request.option != 0`，原生 Count1 会被同样挡掉，且本地没有任何测试覆盖这些模块。当前背包里没有这些箱子，未一并放开。
