# 定时备份错误输出审查

当前线上 wrapper 的 SHA 为 f8c2c3145f5effff3e4d439036d50758739883ba18f9f3285d422cc71e193772。它使用 capture_output=True 和 check=True 调用原备份程序；子进程非零退出后，CalledProcessError 的通常 traceback 不包含所捕获的 stderr。计划任务又没有输出重定向，因此真实失败原因未落盘。已发生的两次失败无法靠本次补丁追溯恢复。

候选只让子进程 stderr 直接进入服务器私有 logs/backups 下的独立日志，并在 wrapper 自身失败时写入完整 traceback、刷盘后原样抛出。成功输出目录、后台低优先级、SQLite backup API、空间保护、双库顺序、gzip 校验和原始备份删除条件全部保留。三个压缩相关函数经 AST 比较无变化。

四项针对性检查通过：真实小型子进程的 stderr 和退出码 7 均保留；压缩异常保留；越界返回目录仍拒绝；成功路径仍压缩双库并返回同一目录。测试未运行游戏、真实数据库备份或生产任务。候选 SHA 与结果见 diagnostics-candidate.json、diagnostics-verification.json。

目前尚未安装。正在进行的莉提亚认证清理绑定了现有备份脚本 SHA，不能在它结束前替换脚本，避免破坏已授权清理的校验。待测试和认证清理完成，再按原发布锁安装并核对实际文件；不重新启动失败的大备份。空间不足是否为此前异常原因仍未证实，不能把日志修复记为备份恢复成功。
