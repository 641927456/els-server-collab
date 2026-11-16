# GM共同源码候选与独立复核

2026-11-16。候选8个文件逐字复用V219冻结线上载荷，未改业务语义。候选位于本目录candidate，准确源、父版和新摘要见candidate-manifest.json。三个绑定、导入与调用范围测试通过，结果见verification.json。

## 统一范围

- 替换共同模块els_server/dungeon_workers.py和els_server/gm_runtime.py，补入els_server/gm_item_batch.py。
- els_server/storage/player_mail.py仅CRLF字节差，采用线上相同字节以消除共享叶摘要差异。
- 加入gm_console/__main__.py、accounts.py、service.py、settings.py。四叶是独立GM API/监护程序，Python namespace package可以导入，无新增__init__需求。
- 共增加5个服务端模块成员。现有server-addon若仍2020文件，合并后应为2025；client137不需要新增GM成员，最终union预计2134。由构建器实算成员数。

## 普通业务与GM边界

worker_scope新增范围只接受绑定当前Application的GM Runtime函数、batch-give/batch-give-preview动作且mode=online。其余正常玩家函数路径逐字相同。测试实际执行该context manager，验证在线批量发放进入角色/世界锁，账户/角色邮件模式及无关函数沿既有路径。

gm_runtime新增批量发放、formal-drops配置和状态字段，只通过127.0.0.1的GM token RPC可达。服务器入口仍要求friends配置和外部提供的ELS_GM_RUNTIME_TOKEN。GM网页API仍检查loopback Host、X-GM-Key，写请求额外检查Origin、JSON和大小。上线或本地共用代码不改变实际认证/数据库/证书/私有配置路径。

批量在线授予继续校验当前registry、role/released、session、受众预览摘要、UUID和精确字段。SQL单事务保存receipt，先编码各mailbox再提交和采用；相同请求回放原receipt。邮件模式按当前数据库中enabled账户或未删除角色选定，不从调用参数接受任意收件名单。授权GM能修改玩家库存与掉率，这种管理能力应在两端共同源码中一致，实际状态各自保存。

formal-drops写现有gm_rates配置入口。gm_rates.py、ordinary_misc_loot.py两端完全同字节，普通掉落算法未改。player_mail.py规范化换行后相同。不存在本批普通玩家handler的新分支。

## 配置与界面兼容

settings的可编辑字段不含mode、host、存档/账号/证书路径、token和runtime_port。更新沿ServerConfig验证，要求正常停服且端口排空、比对配置revision、备份完成及写前二次核对。字段表与NAMES一致。

此四叶不含浏览器静态页面，GET根路径返回页面已迁至管理员电脑。统一安装这些叶可恢复服务端GM API和monitor代码，现有管理员电脑页面仍沿其独立交付保留；无依据替换页面或拷贝私有密钥。新增目录默认不会自行启动，监护器只有显式入口与部署参数才运行。

Service按self.root/server-python/python.exe启动游戏，合并到完整server-addon/runtime后复用已有server-python依赖。config使用传入路径，home独立指定。当前统一本地也是friends模式和127.0.0.1，保留此值即可，无新增LOCAL认证分支。

## 发布建议

本候选和冻结线上8叶完全同摘要，若发布负责人重核实际远端仍相同，可只更新共同源码、签名附加组件与本地安装，线上业务无需因这些代码重启。去掉冻结输入中这8项online_only_overlay，确保两端共同成员采用同一摘要；保持各自账号、存档、证书与GM home配置。部署核对新addon实际成员、V221选中组件和本地安装结果，复用当前版本已验证的安装机制。

已有线上授权入口和经济实现均为原代码，本轮没有再次执行GM发放/掉率写入。当前离线测试只证明新增组合的精确来源、依赖闭包、作用域和配置字段；未开启监听、未启动服务或客户端、未读写玩家库。尚无安装V221结果，本报告不登记安装完成。
