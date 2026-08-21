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

## 发布副本

1. 运行数据生成器 `--apply`；
2. 运行检查脚本并确认 PASS；
3. 使用发布准备脚本生成脱敏的 `index.html`，安全嵌入允许发布的本地文档，并复制全部页面素材；不得直接复制含本机深链的正式工作台：

```powershell
python "<skill>/scripts/Prepare-FitnessWorkbenchRelease.py" --project "<项目根>" --deploy "<发布目录>"
```

4. 再运行：

```powershell
python "<skill>/scripts/Check-FitnessWorkbench.py" --project "<项目根>" --deploy "<发布目录>" [--notion "<notion-data.json>"]
```

发布准备脚本会移除本机绝对路径和已保存的 Obsidian 深链，并复制当前完整计划 HTML、视频、海报和页面素材。只有 `deploy: PASS` 后才部署或分享。

## 更新模板

界面改版完成后，从正式 HTML 重新生成脱敏模板，而不是手工复制个人数据块。刷新后运行 Skill 校验，并在隔离目录重新初始化一次，确认新电脑路径下仍可独立构建。
