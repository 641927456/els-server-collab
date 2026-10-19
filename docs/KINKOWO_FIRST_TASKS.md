# KinkOwO 第一批修复任务与文件边界

登记日期：2026-10-19，Asia/Hong_Kong。任务基线为 `59cd78afe532cec715520bcb0d702be22b321d81`，运行资源为 `collab-runtime-v2`。
这是分配范围，尚未收到KinkOwO本人认领；没有代他开工或向他发送消息。接手时先以最新main核文件SHA和Issue认领。

第一批集中在**邮件未读提示、普通玩家互寄和黑名单交互**。维护方负责共享入口、其他业务、集成和发布；不同时重写下列已分配邮件函数。
当前本地正式快照与协作仓库的11个邮件文件逐SHA一致，未发现需要先搬运的新邮件代码；文件基线见 `kinkowo-file-scope.json`。
当前并行交接重点是主线/转职、活动、称号/经济、露希及材料；不把这些分给KinkOwO。未向其他会话发信，也没有声称已为所有作者取得文件锁。

| 优先级 | 编号 | 任务 | 当前结论 | 开始条件 |
|---|---|---|---|---|
| P0 | KINK-00 | 建立独立副本与问题记录 | 环境准备，非功能修复 | 接受邀请、取得专用配置 |
| P1，首修 | KINK-01 | 角色邮件可见范围与未读计数一致 | 已有独立临时库复现 | 本地CI/资源检查通过；不依赖实机或第二账号 |
| P1 | KINK-02 | 普通玩家互寄/回信的自然闭环 | 已实现，完整玩家互寄仍未验；先复现再修 | KINK-00；远端需第二个独立测试账号 |
| P2 | KINK-03 | 黑名单拒收及邮箱刷新后的原生状态 | 以验收补缺为主，未断言已有新缺陷 | KINK-01合并；KINK-02基本链可用 |

同一时间只做一个写代码的任务、一个PR；第一批先提交KINK-01。后续任务若没有复现到缺陷，就交验收记录，不为凑改动重写已正常代码。

## KINK-00：独立环境与反馈基线

可写：新增 `docs/kinkowo/reports/KINK-00.md`。只读参考 `README.md`、`docs/STAGING.md`、`tools/launch_friends_client.py`、`tools/ci_checks.py`，不修改启动器或服务端入口。

验收标准：

- 用自己的GitHub账号接受邀请；克隆私有仓库，记录提交SHA和运行资源SHA。
- 在自己的副本执行bootstrap和 `python/python.exe -B tools/ci_checks.py --with-runtime`，记录实际结果。
- 个人联调配置只放忽略的state目录，不上传账号令牌、存档、抓包原件或日志全集。
- 自行选择完整客户端，先执行 `launch_friends_client.py --check`；GUI成功或失败分别记实际现象、客户端EXE SHA、时间和必要日志。
- 新建角色和城镇入口只操作自己的新测试账号。若客户端/入口受阻，保留具体错误，由维护方处理；KINK-01临时库修复仍可继续。

交付：一份脱敏环境记录。不要把环境准备或CI通过算成已修复游戏功能。

## KINK-01：同账号跨角色的未读提示计数错误

### 已确认的最小复现

同一合成账号有角色A(1001)、B(1002)，只有一封绑定B的合成角色邮件：

- `game_mail.inbox(..., uid=A)` 返回0封；`mailbox_extras.status(..., uid=A)` 却返回 `(1,1,1)`。
- B的收件箱和status均为1；预期A的status是 `(0,0,0)`。
- 这是数量、未读和最后邮件ID的范围不一致，不是已经证实能读取/领取其他角色附件。
- 复现仅用TemporaryDirectory中新建的合成SQLite，未运行活动producer、未发物品、未访问玩家库或网络。不是实机复现，也不证明活动当前开放。

复现命令：

```powershell
.\python\python.exe -B tools/kinkowo/repro_mail_unread_scope.py
```

当前基线输出 `ok:false` 并退出1，这是保留的缺陷复现。修复后应输出 `ok:true` 并退出0，不要修改期望值来掩盖差异。

### 文件范围

允许修改：`els_server/storage/mailbox_extras.py` 的 `status()` 查询；新增 `tests/test_kinkowo_mail_status.py`、`docs/kinkowo/reports/KINK-01.md`。

只读调用链：`els_server/storage/player_mail.py::visible_sql(db)`、`els_server/storage/game_mail.py::inbox()`、`els_server/storage/online_title_mail_scope.py::exists()`、`els_server/domain/mailbox_extras.py::periodic()`。
当前status调用 `visible_sql()`，而收件箱调用 `visible_sql(db)`，应先核对这个数据库上下文差异。优先复用已有可见范围函数，不另造活动资格或计数框架。

验收标准：

1. 原复现由失败转为成功，A/B的count、unread、last均只反映各自可见邮件。
2. 新的自包含临时库回归覆盖：角色限定邮件、普通玩家邮件和账号级邮件混合；不同账号不能混查；无scope表的旧库仍可查。
3. 已读、删除、到期邮件仍按现有查询规则计数；不会因修提示改变邮件或附件的所有权、状态、有效期或领取权限。
4. 必要时补一个status到既有1CE通知的受控检查，确认通知用同一可见未读数，不写自定义客户端红点逻辑。
5. 只读查询前后业务行保持，不迁移schema、不启用活动、不改奖励和客户端。新增回归必须失败于原版、成功于修复版。

新回归命令：

```powershell
.\python\python.exe -B -m unittest discover -s tests -p "test_kinkowo_mail_status.py" -v
```

交付：一个小PR，附原失败、修后结果及文件SHA。原生界面尚未验证就如实标注；这项计数修复不必等待整套活动或多人系统完成。

## KINK-02：普通玩家互寄与回信

这项先做真实玩家流程核验，不能把“尚未完整实测”直接写成确定缺陷。已交付的附件首次领取、旧回执刷新和防重复发奖保持，不重做已有修复。

允许修改（仅实际复现所需）：

- `els_server/domain/player_mail_flow.py::handle()`：普通1CF发送/1D0回执。
- `els_server/storage/player_mail.py::send()`：普通发送事务，不改同文件的活动装饰、范围绑定和到期退回规则。
- `els_server/protocol/player_mail_messages.py`：只有当前已证分支的字段/错误回执确有问题时修改。
- 新增 `tests/test_kinkowo_player_mail_send.py`、`docs/kinkowo/reports/KINK-02.md`。

只读：`player_mail_rules.py`费用公式、`mail_attachments.py`准入、`game_mail.py`领取、原生语法数据和SHA约束。更广改动须先在Issue写出具体文件/函数，等维护方调整分工后再动。

验收标准：

1. 用两个独立的新测试账号A/B及各自角色，正常在城镇通过原生邮箱互寄文字信、ED信，再按现有准入验证普通道具信；ED和物品按现有代码分别验证，不擅自开放混合附件。
2. 发件人只扣一次附件和既有邮费；收件人列表、正文、发件人、附件及领取后的状态正确；回信能到原发件角色；冷登后结果保持。
3. 不存在收件人、自己给自己寄、邮费不足、被对方拉黑、非法或未准入附件时拒绝，ED/物品和回执不发生半笔提交，原生发送界面能够结束等待并再次合法操作。
4. 针对实际改动补必要的事务/编码失败回滚和同操作重试检查，不放宽现有身份、阶段、UID、封印或锁定限制。
5. 按发送扣减与接收增量、回执和冷读判定，不看背包总量猜结果；请求可能已提交时先查回执，不直接重复发送写请求。

本地合成夹具可以准备ED/道具，但要标记“预置”，不能当自然获取。联调需要第二账号或测试资源时由维护者另行提供；不共享kinkowo令牌、不调用GM、不修改远端库。
自然互寄与协议/事务结果分别记录。若没有复现到错误，交一份真实互寄验收报告即可；不能以新测试数量提高整卡分数。

## KINK-03：黑名单拒收及原生邮箱刷新

只在KINK-01合并后继续。优先核“拉黑→拒收不扣钱→解除→合法互寄→阅读/删除后未读提示刷新”的原生闭环。

允许修改（仅有复现的函数）：

- `els_server/domain/mailbox_extras.py` 的黑名单请求、refresh和periodic处理。
- `els_server/storage/mailbox_extras.py::change()`及与KINK-01一致的status消费。
- `els_server/protocol/mailbox_extras.py` 已证黑名单/通知回执。
- 新增 `tests/test_kinkowo_mail_blacklist.py`、`docs/kinkowo/reports/KINK-03.md`。

只读参考：`domain/mail_flow.py`、`storage/game_mail.py`的收件箱/阅读/删除。不以此任务重写领取事务、账号级GM邮件或活动邮件。

验收标准：

- 黑名单按角色及当前服务端规则隔离，新增/删除及重登一致；同操作重试不重复写，编码失败回滚。
- 被拉黑的发件请求拒绝且无费用/附件扣减；解除后正常发送。不为了通过用例扩大为账号全局黑名单。
- 阅读、删除或手动刷新后，列表与可见未读提示同步；切换角色不沿用上个角色的计数。
- 非法阶段或数据库暂忙时失败/重试行为不使普通连接断开；只为实际改动增加必要验证。
- 原生GUI证据与临时库/协议证据分开，客户端自行显示，服务端只发已有通知。

## 避免重复修改：双方约定

KinkOwO第一批以本文件和 `kinkowo-file-scope.json` 为边界。维护方暂不同时实现已分配的邮件修复函数；收到PR后做最小核收。未经确认不扩到下列范围：

- `els_server/domain/local_session.py`、`els_server/config.py`、`els_server/storage/local_state.py`、`els_server/domain/inventory_items.py`等共享分发/存档/物品入口。
- `els_server/domain/*quest*`、转职/成长、称号、露希/希尔、材料掉落/多人世界、刻印/重铸、芯片、Cartridge、活动producer及其配表。
- `tools/launch_friends_client.py`、兼容工具、Frida/JS、EXE/KOM、启动器载荷、资源锁、CI/发布脚本、GM、服务器任务/配置/证书。
- `storage/online_title_mail_scope.py`、`storage/online_2026_mail_snapshot.py`等活动共享边界；邮件任务可以复用其只读过滤能力，不能改活动准入或发奖。

若根因落在禁改范围：先提交最小复现、具体函数、建议修改片段和依赖，交维护方接手公共文件，不直接整文件覆盖。依赖未交付不阻塞其他独立任务。

接手/每次提交前：

1. 先在Issue写任务编号、负责人KinkOwO、基线提交、预计改动文件和函数。维护方核范围后开 `fix/kinkowo-KINK-01-mail-unread` 一类分支。
2. 工作区干净时更新main；对比文件SHA。若基线文件变了，先看diff和最新认领，再三方合并，不覆盖新代码。
3. PR标题含任务编号；说明根因、修复前后、实际验证层级、失败轨迹、存档影响和未验项。新增测试文件用 `test_kinkowo_` 前缀。
4. 不直接推main、不强推、不整树覆盖、不改服务器。合并不等于已经部署；部署和进度表由维护方负责。
5. 现有完整业务测试和QA资料并未全部随Git附送，不能把缺失夹具当功能缺陷，不要求无差别全跑历史测试。复用未变成功证据，只补实际改动所需回归。

范围是协作约定，当前套餐没有GitHub强制主分支保护，也没有对其他会话建立技术锁。后续并行作者/需求变化时必须先重核分工；本清单不代表未验功能已修复。
