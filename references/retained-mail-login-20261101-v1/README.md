# 旧邮件附件导致的登录断线（Issue725）

进入角色后，服务端在原登录请求50的回复后生成1CE未读邮件预览。邮件托管JSON把旧持有道具还原为普通dict，随后专用物品校验拒绝它并抛出`Unchanged owned native consumable reader required`，关闭连接。本次在持久化邮件入口恢复原有读取类型，使原生预览、邮件查看及领取走通。领取变更数量/位置后仍经原读取器校验；通用发放和伪造普通字典继续被拒绝。

精确运行增量只有3叶：mail_attachments.py、item_instances.py、mail_notifications_2026.py。source另归档2份已生效的读取器/定义依赖，注明existing_runtime_dependency；不是新增来源或新的消费能力。本次不改历史root源码、channel/current-engine选择或旧清单，不把旧的协作源码视图整树当正式服覆盖源。集成时以manifest的3叶增量和实际父版三方核对，已有依赖按SHA复用。

2026-11-01已安装线上retained-mail-login-20261101-v1与本地local-retained-mail-login-20261101-v1，分别完成125.05秒/120.00秒运行观察。7项隔离测试覆盖登录进城和重登、预览与邮件查看、领取与冷读、堆叠及余量、重复领取不增发、编码失败回滚、来源/归属拒绝、损坏及过期附件、单件旧物品和普通附件。自建账号39个公网请求通过，真实问题角色的邮件另以只读连接核验。详情见qualification.json；未包含玩家库、账号凭据、原始抓包或日志。

复核源码归档（无需私有运行资源）：

```powershell
python -B tools/verify_retained_mail_login.py
```

在已有已核资源和源码的运行目录上复现7项业务测试：

```powershell
python -B tools/verify_retained_mail_login.py --runtime <已核运行目录> --channel online
```

工具先核精确源码与依赖SHA，再加载本归档源码；测试仅在本仓库忽略的.runtime-cache中生成自己的临时SQLite库，不读运行目录内的存档或凭据。普通CI只做源码/归档核对，不把缺少私有资源时的结果冒称业务测试通过。

无数据库结构或经济规则变化，无客户端/EXE/KOM变更；现有V58启动器已核实际选择本地新版。自然GUI由玩家正常登录确认，未自动控制玩家游戏。此次Git提交归档已经交付的修复，不重复部署，也不表示主干已合并。
