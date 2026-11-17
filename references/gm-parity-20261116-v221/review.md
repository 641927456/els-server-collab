# V221共同GM源码整合

八个GM叶逐字采用冻结线上源码。客户端137叶与V220同摘要，服务端附加组件2025叶、联合2134叶。逐项独审和三项定向离线验证通过。

启动器LeanRuntime按精确RequiredClientIdentity绑定客户端，保留每个组件的签名、角色和硬编码identity校验；LocalManifest记录服务端组件SourceRelease。实际编译EXE离线反射验证旧客户端与新addon可组合、错误required identity拒绝、篡改签名拒绝，LocalManifest来源为V221。

本次仅准备未发布候选，尚待发布负责人独立核对后上传、核真实附加组件选中与本地安装。线上八叶已存在，运行服务继续V219。已通过V220原客户端启动结果可复用。详细见gm-review.md与module-pair-verification.json。
