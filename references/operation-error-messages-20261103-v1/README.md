# 装备、制作与交易行失败提示

强化ED不足返回373，镶嵌ED不足返回1355，制作ED/材料/容量不足返回302/303/304，复原缺少卷轴返回380。已知业务原因使用ValueError子类向原入口传递；其他原-1回复改用有文案的1。交易行错误出口移除与业务无关的1168，使用通用失败1。原子扣发、回执、权限、成功与强化结果、原生ERP256静默约定保持。

6文件增量针对source-contract.json绑定的完整线上父包。根源码、当前引擎与资源仍沿仓库既有冻结方式保存；此目录不自动部署。已通过9个实际隔离Application/TLS拒绝场景、2个当前镶嵌成功场景、7个既有经济成功/回滚/幂等回归、ED类型边界及原生文本核验。两项旧测试在父版同样失败（已变化的高等级强化规格、缺少会话标识的旧镶嵌API）；新镶嵌TLS流程单独通过。自然GUI未验。

提供匹配的完整私有父运行资源后，可运行：

```powershell
$env:ELS_OPERATION_TEST_PARENT='G:/els/releases/online/native-dungeon-fatigue-errors-20261103-v1'
python -X utf8 references/operation-error-messages-20261103-v1/verification/reproduce.py
python -X utf8 references/operation-error-messages-20261103-v1/verification/verify_success.py
```

不含账号凭据、玩家库、原始日志或抓包。Git上传、主干合并、线上安装分别登记；本目录初始提交为待安装候选。
