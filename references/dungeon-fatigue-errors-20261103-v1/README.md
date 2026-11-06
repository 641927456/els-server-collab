# 副本疲劳不足提示修复

普通疲劳耗尽时，单人预检原先显示通用2224，单人37F/382及组队382还会丢失具体原因。现在沿既有资格读取返回原生77：“疲劳值不足，无法进行副本冒险。”覆盖单人7D4、37F、382与组队7D4、382；资格、扣除、恢复和零消耗副本规则保持。

`source-contract.json`记录四个候选文件的准确SHA、线上父版和验证结果。根源码与当前引擎仍是仓库历史冻结输入，本次沿既有源码归档方式提交独立增量；上传/合并不会自动安装服务器。原候选是修复调查时的快照；Git主干未合并。实际安装状态见PR说明。

已验证11组场景：真实Application/TLS、自有临时库、正常与单人团本预检、预检后耗尽、组队房主/队员耗尽、直接组队入场、其他资格与报文拒绝、零消耗豁免、读库/角色失败、1点疲劳成功创建共享房间。拒绝路径不改疲劳账本或余额。临时库与连接已清理。自然GUI、多人战斗和正式公网安装尚未验收。

提供完整且匹配的私有父运行包后，可执行回归：

```powershell
$env:ELS_ENTRY_TEST_PARENT='G:/els/releases/online/native-attendance-projection-reuse-20261103-v4'
python -X utf8 references/dungeon-fatigue-errors-20261103-v1/verification/verify_entry.py
```

验证会生成自有临时库/证书并清理；可用ELS_ENTRY_TEST_TEMP指定G盘测试位置。不连接生产账号或玩家库。完整运行资源依照仓库锁定附件提供；没有把私有资源、原始日志或凭据复制入Git。

本次单次安装已获得人类明确授权，按最新 `native-activity-armor-reset-scroll-20261103-v1` 父版三方整合。精确四文件在 `rebased/source/`，SHA、父版和11组私有Application/TLS验证见 `rebased/source-contract.json`；保留原赛车/玩法和重置卷轴增量。操作核收结果另记PR说明，不将本源码归档自动作为已安装证明。
