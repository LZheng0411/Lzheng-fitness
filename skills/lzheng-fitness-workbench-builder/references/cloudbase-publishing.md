# CloudBase 发布协议

仅在用户明确要求 CloudBase 发布、上线核验、加密私人发布或公开个人数据时读取本文件。普通计划修改、训练复盘和本地工作台刷新不得读取本文件，也不得加载 CloudBase 脚本源码。

## 发布前提

先由已授权 Agent 实际查询 Notion 并冻结本轮 JSON；没有新快照、快照过期或查询失败时必须停止，不得冒充最新。公开匿名展示调用 `Publish-FitnessWorkbenchCloudBase.py`，它只接受 `public-anonymized`。浏览器的“确定访问”不是身份鉴权，不能用于直接携带个人计划、复盘、体重或 Notion 来源。

首次 `tcb login`、环境创建、私人密码初始化以及手机移动网络验收必须暂停交由用户；配置必须明确 `accepted_free_tier=true`，发现付费或按量资源立即停止。

## 私人加密发布

用户明确要求在默认免费网址查看完整个人工作台时，使用 `Publish-FitnessWorkbenchCloudBasePrivate.py`：先生成受管 `private-portable`，再把页面和全部资源合并为单 HTML，使用本机 Windows DPAPI 保护的强密码执行 PBKDF2-HMAC-SHA256 + AES-256-GCM 加密。云端只上传登录壳、密文和非敏感 manifest。

密码不得通过命令行、聊天、项目、HTML、回执或云端传递；首次初始化必须由用户在本机遮罩窗口输入。错误密码、密文篡改或明文私人路径残留必须拒绝发布。只有密文版本可走 CloudBase 默认静态域名；未经加密的 `private-portable` 即使配置了 HTTP 身份认证路由，也不得上传到可被底层静态域名旁路访问的位置。

## 用户明确授权公开个人数据

只有用户明确表示完整个人数据可以被任何获得网址的人查看，并明确要求取消密码，才使用 `Publish-FitnessWorkbenchCloudBasePublicPersonal.py`。

该流程仍以 `private-portable` 为项目外中间副本，公开版使用受管静态资源与非敏感 manifest：首页、计划页、图片和视频可拆分为独立文件，并由 manifest 记录精确文件集合、字节数和 SHA-256。每次准备和部署都必须显式传入 `--confirm-public-personal-data`；manifest 与 HTML 同时记录 `contains_personal_data=true`、`user_authorized_public=true` 和 `required_access=public`。不得把这种授权推断给其他用户或其他发布任务。

## 发布目录安全

发布目标必须与项目、备份和回执完全分离，不能是磁盘根目录，也不能经过符号链接、Windows junction 或其他 reparse point。

已有目录只有在 `release-manifest.json` 为 schema 2、带固定 kind/producer，且精确允许列表与每个文件哈希全部匹配时才可替换。无清单、旧 schema、被篡改或无关目录一律原样保留并失败，不提供隐式接管参数。

本地生成或上传成功不等于上线完成。只有远端上传后重新读取首页、资源和 manifest，并完成字节数、SHA-256 与精确文件树核验，才能写 `online_verified=true`。
