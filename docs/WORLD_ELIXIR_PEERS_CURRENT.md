# 灵药同房间原生同步

仅当前已加载且持有lease的同房间/代际参与者，完整3A3状态复用原member数据；原gate_stage游标。通知失败保留经济ACK并重试通知。

本项为服务端来源合同与既有通用流程的最小增量，不新增客户端行为。来源身份、资格、事务、实例、回执和冷读保留。

依赖：本series前5步；按Essence→manual→growing→world-self→selector→world-peer顺序。

可携带检查（先安装原222项SHA锁定只读资源）：

```powershell
python -B -X utf8 -m unittest tests.test_elixir_peer_world_current -v
```

测试只使用私有临时库或适配器夹具；没有客户端副本、游戏进程或用户输入。原受控SQL/TLS成功证据由维护者归档复用，本Git准备不重跑。当前仅源码CI/ABI检查；上述可携带业务测试在本草稿中未执行。

状态：等待本轮线上与本地验收后，由维护者按Issue/分支/PR流程独立提交。本稿不代表部署或整卡100%。自然界面、正常获取/EP限购及其他未知边界未因此通过。新增JSON是本服务端来源/规则合同，不是客户端完整资源表；原runtime-assets.lock.json不变。
