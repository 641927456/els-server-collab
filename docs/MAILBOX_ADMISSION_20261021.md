# 跨会话通知队列容量保护

候选状态：已完成隔离源码与私有验证，正式线上和本地安装状态等待维护者验收回执。关联 Issue #47；Git 提交不自动部署。

一个慢消费者触发 256 条或 256KiB 限制后，旧 `Mailbox.append` 已改变队列，`FriendsWorld.send` 还继续向它追加通知，可能持续突破原上限。本修复先计算容量，移动同 UID 替换只计旧、新 payload 差值，不增加条数；拒绝时保留原 deque/moves/bytes 与移动对象。已标记 `social_overflow` 后停止排队，仍由原 SessionOrderError→业务释放→连接关闭路径终止会话，不清标记或静默丢包后继续会话。健康 peer、成功报文、正常 drain/FIFO 保持。

只有 `els_server/domain/friends_world.py` 的两个函数变化；无 schema、数据库迁移、奖励/经济/概率、协议或客户端行为变化。运行源码与冻结候选精确 SHA 相同，不为 Git 行尾格式再次部署。

可移植纯源码测试：`python -B tests/test_mailbox_admission.py`。使用合成 payload 和内存队列，不需要账号、玩家库、运行资源、服务端端口或游戏。此前私有真实 loopback/native 帧已验证现有拒绝、租约释放与 socket 关闭链；不重复旧 40 次重连检查，不将这些验证记作多人材料自然拾取/世界/UDP/玩家 GUI 完成。六文件多人材料候选保持隔离。
