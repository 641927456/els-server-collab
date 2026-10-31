# 来源和行为

2026-10-31 查阅官方 KR 自定义系统说明（2024-03-25），确认拥有道具右键登记后在定制窗口选择、应用。官方 2018-02-22 公告确认魔法卷轴支持对已赋予能力的技能切入和觉醒定制重新赋予；NA 2022-07-06 公告确认不同切入登记后能否立即赋予能力的提示存在差异。链接见 source-contract.json。

能力并非随机：固定 c881 镜像 11D853C 的 type3/15 分支，11F1CB0 读取来源 group；group1 且未赋予时免费，否则要求模板295995。32CEE90 → 2EE5F40 → 2EE70E0 → 22611D0 → C595C0 保留玩家所选 SocketID。219 依次携带卷轴 UID（免费时0）、CustomID、类别、SocketID、空字符串、false。CUSTOM_ITEM_SOCKET_DATA 的 group0/1 均列出9个允许 ID；没有概率或自动赋值。原生 C595C0 已离线执行核实际请求；BB7F30/11F2B10 已执行核能力更新已有记录，不重复插入。

永久主书来源使用既有合格 ED 交集3087行和原始 item record SHA，不新增产出或价格。25个旧 Lu/Ciel 根编号遵守 AddReplaceCustomID 成对登记；已有一侧保留，只补缺侧，同一事务扣1书。IS_MAJOR 对应原生 Apply variant2/3；非Lu/Ciel保持1。默认及职业免费选项来自已解码的 AddFreeMotion/SkillCutIn/Portrait/QuickVoice/Emoticon，未推断超越/大师专用额外授权。

3件原始unit12/required class201(family11)矛盾书470442、470443、480369无法满足双方限制，219返回285且不扣物。原EXE/KOM不修改，未用服务器成功回包掩盖此源冲突。9个能力ID直接交客户端原生消费者，不另造属性公式；自然界面、多人双人坐姿和完整实战属性未验。
