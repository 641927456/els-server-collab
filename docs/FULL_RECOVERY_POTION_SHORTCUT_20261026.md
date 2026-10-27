# 快捷栏1「完全恢复药水」不可用与1秒冷却

快捷栏第1格（绑定组412）的完全恢复药水点了没有反应，服务端在0x113之后回0x114且结果为-1。原因是该绑定组同时满足两个独立拒绝，任一都足以让点击无效。

## 两个拒绝点

1. 组412内现在同时拥有两个模板：130165（279个，背包格7）和710000（99个，背包格12）。二者`item_binding`都是412，而`storage/consumables.py`的默认分支要求"同组只有一个模板"，否则抛`Ambiguous consumable template`。这条守卫原本是为了不猜未知药族，但412是同一族的完全恢复药水，结果把一直可用的710000也一起挡死了。
2. 即使只留一个模板，130165也不在`domain/consumables.py:ordinary()`的准入表里，直接抛`Consumable effect not implemented`。它的记录与已准入的710000除模板id外逐字节相同：冷却组15、30秒、A8为空、最低等级0、AC两条依次(13,100)/(19,100)。

旁证：`state/development.sqlite3`的`consumable_cooldowns`里该角色有组2/5/10/12/14的近期使用行（对应快捷栏2/3/4/5的79063、79064、79065、130467），完全没有组15——这一格从没成功用出去过。

## 改动

- `domain/consumables.py`：准入`expected[130165]=(0,15,30,((13,100),(19,100)))`，并用`LOCAL_COOLDOWN_SECONDS={130165:1}`把这格的**服务端计时**改为1秒；`acknowledged_cooldown()`只对这条记录把0x114尾部的冷却浮点从-1改成1.0，其余药水仍是-1（即沿用它原来的原生值）。
- `storage/consumables.py`：选定候选的分支从`(399,775)`扩到`(399,412,775)`，沿用同一确定性顺序（有期限优先、到期早优先、再按背包格与UID）。本角色因此固定消耗130165（格7），不会误吃710000。
- 目录与清单未动：`els_server/data/client/consumables.json`保持记录字节原样（`0xD6`仍30），`consumables.manifest.json`与`tools/check_EP_owned_goods_source_boundary.py`的哈希不变。客户端的物品记录由模板id在客户端本地资源里重建，服务端这份是镜像，不参与下发。

## 边界

710000本身仍按原生30秒并回报-1；它与130165共享组15，所以**先喝710000会让这格等30秒**，这是共享冷却组的既有语义，不是新缺陷。宠物自动使用、Buff、面向目标或活动类药品继续拒绝；`enabled_templates`清单未改。

## 测试

`tests/test_full_recovery_shortcut.py`4项：目录记录仍是30而服务端计时是1、0x114尾部浮点为1.0（710000为-1.0）、组412两模板时按背包格取130165且1秒后可再用（0.99秒时仍报冷却且事务不变）、只剩710000时维持30秒、真实0x113派发拿到0x114(result=0)+0x115。相关回归`test_additional_potions`、`test_consumables`、`test_consumable_current_owner`、`test_manual_magic_potion_current`、`test_potion_bag_migration`全绿；`test_consumable_actor_lifecycle_current`的`private encoder failure`、`test_potion_moves`的3项在本次改动前即失败（与本组无关，涉及分解/固件/冰装与快捷栏移动）。

## 未验

真实客户端界面那圈冷却是否画成1秒：客户端本地记录仍是30秒，若它只认本地数据，服务端1秒生效但界面可能仍扫30秒。到时下一最小动作是把`acknowledged_cooldown`的值一并用于界面（已经发出1.0），或按需在客户端资源侧调整；本说明不下这个结论。自然副本实战、多人同步未在新验范围内。
