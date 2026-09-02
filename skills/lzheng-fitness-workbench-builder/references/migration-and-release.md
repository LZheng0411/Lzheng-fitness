# 迁移与发布

## 新电脑安装

把整个 `lzheng-fitness-workbench-builder` 目录复制到下列任一位置：

- Codex：`%CODEX_HOME%/skills/`；未设置时使用用户目录下的 `.codex/skills/`；
- 已安装 `my-study-helper` 插件：放入插件的 `skills/` 目录。

必须整目录复制，不能只复制 `SKILL.md`；模板、脚本、动态背景、静态兜底和兼容图片都是运行依赖。

安装后重新启动或刷新 Agent 环境，再说“使用 `$lzheng-fitness-workbench-builder` 从零搭建健身工作台”。

## 迁移个人事实

跨电脑移动时只需要携带：

- 当前计划 `*-vNN.json`；
- 当前执行基准 Markdown；
- 复盘 `INDEX.md` 与其链接的 Markdown 文件；
- 可选的 `notion-data.json`；
- 希望继续使用的自定义背景图片或视频。

不要复制缓存、浏览器 profile、临时截图或旧发布目录。完整计划由工作台按钮直接打开；复盘和状态内容嵌入工作台阅读器。Obsidian 编辑入口只根据当前位置即时生成，目录不是已注册仓库时也不影响主要阅读功能。

已有工作台需要更换壁纸时，不要手工覆盖后直接发布。按照 [壁纸替换](background-replacement.md) 调用脚本；脚本会把当前背景备份到 `历史与治理/背景备份`，并在替换后验证移动和发布所需的相对资源。

## 发布副本

1. 运行数据生成器 `--apply`；
2. 运行检查脚本并确认 PASS；
3. 明确选择发布模式，再使用发布准备脚本生成全新的发布目录；不得直接复制正式工作台，也不得复用旧目录中的文件：

### 私人可迁移副本（默认）

`private-portable` 保留内嵌训练计划、复盘和状态内容，只移除本机路径与 Obsidian 深链。它含个人训练数据，不是匿名版，只能放在已确认有私有鉴权的环境：

```powershell
python "<skill>/scripts/Prepare-FitnessWorkbenchRelease.py" --project "<项目根>" --deploy "<发布目录>"
python "<skill>/scripts/Check-FitnessWorkbench.py" --project "<项目根>" --deploy "<发布目录>" --allow-private-portable --expect-release-mode private-portable
```

### 公开匿名界面副本

`public-anonymized` 只保留可初始化的界面空壳与页面素材，不携带训练日事实、动作处方、体重、训练记录、复盘、完整计划或 Notion 链接：

```powershell
python "<skill>/scripts/Prepare-FitnessWorkbenchRelease.py" --project "<项目根>" --deploy "<发布目录>" --mode public-anonymized
python "<skill>/scripts/Check-FitnessWorkbench.py" --project "<项目根>" --deploy "<发布目录>" --expect-release-mode public-anonymized
```

### CloudBase 默认网址上的完整私人副本

CloudBase 默认静态域名和底层托管文件可公开访问；HTTP 路由鉴权不能证明底层静态域名不存在旁路。因此不得直接上传 `private-portable`。用户明确要求完整私人网页且保持零现金成本时，只允许发布 `private-encrypted`：

1. 本机遮罩窗口初始化强密码，密码由 Windows DPAPI 当前用户保护，不进入项目或聊天；
2. 受管 `private-portable` 的 HTML、背景和完整计划合并为一个 HTML 字节流；
3. 使用 PBKDF2-HMAC-SHA256（至少 600000 次）派生 AES-256-GCM 密钥；
4. 云端目录只包含公开解密壳、`private-payload.json` 密文和非敏感 manifest；
5. 本地必须回读解密成功，线上必须逐字节核对三份文件；用户再用手机输入密码验收。

统一入口：

```powershell
python "<skill>/scripts/Publish-FitnessWorkbenchCloudBasePrivate.py" --project "<项目根>" --notion "<本轮快照>" --notion-mode incremental --private-release-dir "<项目外私人中间目录>" --encrypted-release-dir "<项目外加密发布目录>" --history-dir "<项目外历史目录>" --backup-dir "<项目外备份目录>" --receipt "<项目外回执>" --config "<非敏感CloudBase配置>" [--execute --verify-online --base-url "<默认网址>"]

### 用户明确授权公开完整个人工作台

只有用户明确表示“让别人看也无所谓”并要求取消密码时，才允许把完整个人工作台转换为 `public-personal-authorized`。这不是匿名版，计划、体重、训练记录、复盘和来源都可能被任何获得网址的人查看。统一入口必须显式携带 `--confirm-public-personal-data`：

```powershell
python "<skill>/scripts/Publish-FitnessWorkbenchCloudBasePublicPersonal.py" --project "<项目根>" --notion "<本轮快照>" --notion-mode incremental --private-release-dir "<项目外私人中间目录>" --public-release-dir "<项目外公开个人目录>" --history-dir "<项目外历史目录>" --backup-dir "<项目外备份目录>" --receipt "<项目外回执>" --config "<非敏感CloudBase配置>" --confirm-public-personal-data [--execute --verify-online --base-url "<默认网址>"]
```

公开个人版使用 manifest 管理精确文件集合：首页、长文档、图片和视频可拆分为独立静态资源，所有受管文件都必须列在 manifest 中并带字节数与 SHA-256。部署前只接受空目录、当前精确文件集合，或上一代受管的两文件集合用于一次受控迁移；部署后和线上回读必须再次精确核验当前 manifest 的全部文件。该授权不可复用于其他用户、环境或内容。
```

旧加密版本可重新部署，但必须带与该版本 manifest/payload 哈希匹配的加密回执。换密码会使旧版本无法用新密码打开，不能静默覆盖本机 DPAPI 密钥。

发布准备脚本每次都在同级临时目录中 fresh staging，再整体替换目标目录，所以旧的 `健身工作台.html`、备份和陈旧资源不会残留。它只复制 `index.html` 实际引用的素材；私人模式另复制当前完整计划。根目录的 `release-manifest.json` 记录模式、隐私标记、精确文件允许列表、字节数和 SHA-256。

检查脚本会递归核对整个发布树、manifest 哈希、资源依赖、额外文件和额外目录，并扫描所有文本文件中的 Windows 路径、Obsidian/file URI、本地 Markdown 链接和占位符。只有显示对应模式的 `deploy: PASS` 后才可部署或分享；任何上传工具都只能取这个已验收的发布目录。

发布安全专项回归：

```powershell
python "<skill>/scripts/Test-FitnessWorkbenchReleaseSafety.py"
```

## 更新模板

界面改版完成后，从正式 HTML 重新生成脱敏模板，而不是手工复制个人数据块。刷新后运行 Skill 校验，并在隔离目录重新初始化一次，确认新电脑路径下仍可独立构建。
