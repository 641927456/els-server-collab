# 朋友服V29组件更新登录器

此目录是已交付V29的实际C#源码和公开签名运行文件清单。保留V27的已验证密码提交、账号规范化及更新激活保护，以及V26界面、23个按钮动效和200×42注册确认按钮。运行内容沿用已发布V28；本目录不同于仓库原有的本地测试启动器。

## 获取与使用

从私有仓库的 `launcher-v29` Release 下载分享ZIP，解压后运行其中EXE，使用自己的账号和客户端。V29本体为2,780,672字节。已有匹配环境时不下载运行文件；内容变化时只补变化或损坏文件。首次没有可复用环境时下载一次基础包，也可以从哈希核定的旧完整登录器导入。

实际公网迁移测试复用1077个文件，仅下载5个文件、219,792字节；再次检查下载量为零。签名、固定证书TLS、逐文件尺寸及SHA256校验，临时目录、原子提交和失败保留旧环境均已验证。完整游戏内流程和多人验收没有因此重新得到证明。

## 构建

图像和图标属于二进制构建资源，位于同一Release的独立附件，SHA锁定在 `build-assets.lock.json`。先在Windows x64环境准备.NET Framework C#编译器与Python：

```powershell
gh release download launcher-v29 --repo 641927456/els-server-collab --pattern ELS-V29-Build-Assets.zip --dir .asset-cache
python launchers/friends-v29/build.py --assets .asset-cache/ELS-V29-Build-Assets.zip --output .asset-cache/ELS-Friends-built.exe
```

脚本只编译，校验所有构建资源，不读取账号、私钥或存档，不访问服务器。重新构建的PE可能因编译时间和程序集名称而与发布EXE整体SHA不同；正式文件身份以 `release.json` 和Release附件SHA为准。不得复用已发布版本号发布修改版。

`runtime-files.signed.json`已由发布者签名，清单绑定该版 `Program.PayloadHash`。只改界面时保持相同环境清单；运行文件变化时须审核冻结内容，重新生成并签名逐文件清单。只有公钥和公开证书指纹位于代码，发布私钥不在仓库、附件或CI。

## 更新服务与回退

`update_service.py`是已使用的只读组件分发实现；它只读取显式允许的文件，以及发布者登记的ZIP成员。部署者还需在自己的独立目录配置 `allowlist.json`、`components-index.json`、`public/`和私有 `tls/`。本仓库没有提供生产部署凭据，不自动执行该服务或修改现有服务器。

新环境按签名清单校验后在独立目录准备，全部通过才原子切换当前指针；失败不切换，不覆盖旧环境。旧EXE和失败激活保护保留。新版本需要不匹配的运行文件时，不以混合新旧内容强行启动。

源码归档和Release上传不构成部署授权，也不扩大游戏Hook、客户端适配或业务开放范围。
