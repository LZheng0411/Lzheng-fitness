---
name: lzheng-fitness-workbench-builder
description: 将训练计划 JSON、执行基准、训练复盘、可选 Notion 导出和内置界面素材组装为可离线打开的个人健身工作台，并完成数据刷新、壁纸替换、内置文档阅读、可选 Obsidian 编辑、响应式页面、发布副本与自动校验。用于用户要求从零构建、迁移、重建、替换背景、打包、同步、修复或发布健身工作台，或希望在新电脑上复刻同款个人训练系统时；不用于制定个性化训练处方、单次训练复盘或医疗建议。
---

# Lzheng 健身工作台构建器

把工作台视为“唯一固定界面模板 + 用户事实文件 + 可重复构建脚本”。唯一视图资产是 `assets/workbench-template.html`；AI 只能刷新 `workbench-data`，不得手写另一套工作台。不把训练重量写死在页面视图，不复制其他人的个人记录。工作台必须适配增肌、减脂、力量和综合健身，四个力量主项只属于力量模式，不能作为其他目标的前提。

读取 `../lzheng-training-system/references/system-contract.md`；如果存在交接记录，读取 `../lzheng-training-system/references/handoff-schema.md`，只消费其中已确认产物。系统根目录优先使用本次用户指定路径，其次使用套件配置；视图代码不得包含固定磁盘路径。

## 低 token 读取边界

日常计划修改、复盘和本地刷新禁止把整份 `健身工作台.html` 或 `assets/workbench-template.html` 读入 Agent 上下文。先运行：

```powershell
python "<skill>/scripts/Inspect-FitnessWorkbench.py" --project "<项目根目录>"
```

该命令只输出模板完整性、当前计划、今日/下次训练、同步状态和本轮应读主源。随后只读取 `authoritative_sources` 中与当前任务有关的 JSON/Markdown；不要扫描历史计划、完整复盘目录、全部专家库或构建器源码。视觉开发、模板修复及检查器报出结构损坏时，才允许定点读取模板命中行；仍不得默认全量读取 100 KB 以上 HTML。

## 先判断任务

- **从零构建 / 新电脑迁移**：读取 [输入契约](references/input-contract.md)，使用初始化脚本创建完整目录和可运行页面。
- **刷新数据**：保留正式 HTML 视图，只运行数据生成器更新唯一 `workbench-data` 数据块；schema 6 必须包含建档、系统、知识包、状态和来源核验信息。
- **接入完整计划**：完整计划使用 `plan_contract` 时，先运行 `Adapt-PlanContract.py` 适配为工作台主源；不得要求用户手工重写第二份计划 JSON。
- **链接打不开 / 跨电脑迁移异常**：完整读取 [路径可迁移修复协议](references/path-portability-repair.md)，先盘点全部入口、配置和发布目标，再修复并执行整体移动回归；不得只修改截图中的单个按钮。
- **替换已有工作台壁纸**：完整读取 [壁纸替换](references/background-replacement.md)，调用替换脚本完成备份、静态/动态模式、取景更新和检查；不得让用户手工改 HTML。
- **修改项目默认界面或默认背景**：读取 [视觉契约](references/visual-contract.md)，修改源模板后用模板刷新脚本生成脱敏模板。
- **制作发布副本**：读取 [迁移与发布](references/migration-and-release.md)，先校验，再复制 HTML 和全部本地素材。
- **制定计划或训练复盘**：转交对应训练 Skill；本 Skill 只消费结果，不凭空生成个人处方。

## 从零构建

1. 确认目标目录、品牌短名、使用者称呼和周期开始日期。
2. 优先使用用户自己的版本化计划 JSON。没有时可以用内置示例启动界面，但必须明确标注“示例数据”，不得把示例重量当成处方。
3. 运行：

```powershell
python "<skill>/scripts/Initialize-FitnessWorkbench.py" --target "<新项目目录>" --brand "TRAIN" --athlete "使用者" --start-date "YYYY-MM-DD" [--plan "<计划-vNN.json>"] [--notion "<notion-data.json>"]
```

4. 初始化脚本必须创建正式 HTML、五个固定目录、背景素材、当前计划、执行基准和复盘索引，并自动运行构建与检查。
5. 把页面中显示的示例计划替换为用户已确认的计划后，再交付为正式系统。

目标目录已有文件时，初始化脚本默认拒绝覆盖。不要用强制参数覆盖用户独有内容；改用新的空目录或先人工审计。

## 刷新已有工作台

日常刷新优先运行单命令闭环。它严格按 builder check → apply →正式 checker 执行；任一步失败都会写失败回执，正式 checker 失败时自动恢复 apply 前 HTML：

```powershell
python "<skill>/scripts/Refresh-FitnessWorkbench.py" --project "<项目根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full] --backup-dir "<项目外临时备份目录>" [--receipt "<项目外回执.json>"]
```

回执中的四个状态不得混用：`formal_refreshed` 只表示正式 HTML 通过 checker；`release_prepared` 只表示本地发布副本通过 deploy checker；本脚本不上传、不访问线上，因此 `deployed` 与 `online_verified` 始终为 `false`。回执同时记录输入快照、正式 HTML、数据块、发布目录及核心脚本的 SHA-256 和版本证据。

只有人工确认 full 快照确实代表整份权威主项历史时，才可增加 `--replace-main-lift-history --confirm-replace-main-lift-history`；它必须与 `--notion`、`--notion-mode full` 同时出现，并会原样传给 builder check、apply、正式 checker 和 deploy checker。缺少任一显式条件即拒绝执行。

排查单个底层阶段时才分别运行：

```powershell
python "<skill>/scripts/Build-FitnessWorkbenchData.py" --project "<项目根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full] --check-only
python "<skill>/scripts/Build-FitnessWorkbenchData.py" --project "<项目根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full] --apply --backup-dir "<项目外临时备份目录>"
python "<skill>/scripts/Check-FitnessWorkbench.py" --project "<项目根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full]
```

需要本地发布副本时，在同一命令显式增加 `--deploy` 与 `--release-mode public-anonymized|private-portable`。`private-portable` 会保留完整个人训练数据，必须额外传入 `--confirm-private-portable`，且只能交给有身份验证的私有环境。生成本地目录仍不等于部署；远端上传和线上复核必须由具备真实外部证据的后续流程完成。

### CloudBase 零成本静态发布

只有用户明确要求 CloudBase 发布、上线核验、私人加密版或公开个人数据时，才完整读取 [CloudBase 发布协议](references/cloudbase-publishing.md)。普通本地刷新不得读取该协议或 CloudBase 脚本源码。

完整计划自动接入时使用：

```powershell
python "<skill>/scripts/Adapt-PlanContract.py" "<完整计划.json>" "<当前周期/个人训练计划-v01.json>"
```

若一次 schema 或视图升级误将已有 Notion 动态数据降级为空态，可使用已知本地备份执行 `--restore-notion-from-html <backup.html>`；此动作只恢复 `notion` 数据，再由当前计划、执行基准和复盘重新生成 schema 6，不能直接把旧 HTML 整页覆盖回来。

正式计划、训练复盘或接回完成后不手工猜测刷新时机：创建 `LZHENG_HANDOFF` 后运行 `lzheng-training-system/scripts/Process-LzhengHandoffs.py --project "<项目根目录>"`。它只刷新通过契约验证的事实，并且只在刷新回执证明正式 checker 通过后写入 `delivery.status: formal_refreshed`；需要合并的专项周期会保持待合并，不能越权成为当前计划。

### 周切换同步契约（强制）

跨周时必须把“复盘结论、下一周处方、当前计划 `schedule`、工作台数据”作为一次原子更新：先把 `schedule` 改成覆盖今天的真实七日日期，所有训练日使用同一个 Wn，训练日数量与 `plan.frequency` 一致，再创建交接并刷新工作台。不得只改复盘、只改周次或让旧周训练卡继续显示。

构建器必须拒绝：排程不覆盖今天、训练日混合多个 Wn、训练日数量与频率不符、今天是训练日但没有今日处方、以及计划写明“自重”却被历史负重覆盖。每次发布前运行：

```powershell
python "<skill>/scripts/Test-FitnessWorkbenchWeekTransition.py"
```

必须保持：

- 当前周期只保留同一计划的一个有效版本；
- 当前周来自复盘索引或用户确认，不按日历擅自推算；
- 复盘索引有多少条有效记录，`reviews` 就按索引顺序完整生成多少条；不得只保留最近 5 条或设置其他隐式数量上限；
- 今日训练按计划中的真实日期精确匹配；
- 未知重量显示待确认，不沿用旧值冒充事实；
- 完整计划 HTML 使用工作台相对链接直接交给浏览器；不得依赖固定盘符或要求项目必须是 Obsidian 仓库；
- 复盘与状态内容默认可在工作台内阅读；Obsidian 只作为根据当前位置即时生成的可选编辑入口；
- 图表已执行部分为实线，后续计划为虚线，重合时只显示实线。

## 更新界面模板

源工作台视觉稳定后运行：

```powershell
python "<skill>/scripts/Refresh-FitnessWorkbenchTemplate.py" --source "<正式健身工作台.html>" --out "<skill>/assets/workbench-template.html"
python "<skill>/scripts/Validate-FitnessWorkbenchSkill.py" --skill "<skill>"
```

模板刷新脚本会移除个人 `workbench-data`，把品牌改为占位符，并检查模板中没有残留本地绝对路径或 Obsidian 个人深链。背景图放在 `assets/backgrounds/`，不得嵌入个人训练数据。

## 交付闸门

以下全部通过才能声明完成：

1. `Validate-FitnessWorkbenchSkill.py` 返回 `FITNESS_WORKBENCH_SKILL: PASS`；
2. `Test-FitnessWorkbenchWeekTransition.py` 返回 `FITNESS_WORKBENCH_WEEK_TRANSITION: PASS`；
3. `Test-FitnessWorkbenchPortability.py` 返回 `FITNESS_WORKBENCH_PORTABILITY: PASS`；
4. `Test-FitnessWorkbenchRefresh.py` 返回 `FITNESS_WORKBENCH_REFRESH_TEST: PASS`；
5. `quick_validate.py <skill>` 返回通过；
6. 在一个全新的隔离目录运行初始化脚本成功，页面显示“待建档”且不把匿名示例重量当处方；
7. 新目录的 `Check-FitnessWorkbench.py` 检查为 `FITNESS_WORKBENCH_CHECK: PASS`；
8. 正式页面所引用的每张图片和完整计划 HTML 在项目、移动后目录和发布目录中都存在；
9. Skill 文本和模板不含原作者训练记录、用户名或固定磁盘路径。

## 资源

- `scripts/Initialize-FitnessWorkbench.py`：从模板和输入文件创建新工作台。
- `scripts/Build-FitnessWorkbenchData.py`：从计划、复盘、执行基准和 Notion JSON 生成数据块。
- `scripts/Inspect-FitnessWorkbench.py`：只读输出紧凑状态，供 Agent 日常定位主源且避免加载整份 HTML。
- `scripts/Refresh-FitnessWorkbench.py`：依次完成预检、刷新、正式检查及可选发布副本检查，并生成不可混淆本地与线上状态的 JSON 回执。
- `scripts/Adapt-PlanContract.py`：将完整计划 Skill 的统一 `plan_contract` 适配为工作台主源。
- `scripts/Check-FitnessWorkbench.py`：检查结构、事实一致性、资源和发布副本。
- `scripts/Prepare-FitnessWorkbenchRelease.py`：生成移除本机路径与 Obsidian 深链的分享版并复制素材。
- `scripts/Publish-FitnessWorkbenchCloudBase.py`：统一 CloudBase 发布入口；只允许新鲜 Notion 快照和匿名发布副本，记录四级状态与版本归档。
- `scripts/Deploy-FitnessWorkbenchCloudBase.py`、`Verify-FitnessWorkbenchCloudBase.py`：分别执行显式上传和线上哈希核验/受管回滚；不创建环境或写入密钥。
- `scripts/Prepare-FitnessWorkbenchEncryptedRelease.py`：把受管私人副本单文件化并使用 DPAPI 强密码加密，公开目录不保留个人明文。
- `scripts/Publish-FitnessWorkbenchCloudBasePrivate.py`、`Deploy-FitnessWorkbenchCloudBaseEncrypted.py`、`Verify-FitnessWorkbenchCloudBaseEncrypted.py`：完整私人工作台的统一刷新、加密、上传、线上三文件哈希核验和四级回执；密钥不进入参数或回执。
- `scripts/Publish-FitnessWorkbenchCloudBasePublicPersonal.py`、`Prepare-FitnessWorkbenchPublicPersonalRelease.py`、`Deploy-FitnessWorkbenchCloudBasePublicPersonal.py`、`Verify-FitnessWorkbenchCloudBasePublicPersonal.py`：仅在用户明确接受个人数据公开时使用的免密码统一入口、单文件准备、远端精确文件集与线上哈希核验。
- `scripts/Test-FitnessWorkbenchEncryptedRelease.py`：隔离验证 DPAPI、AES-GCM、错误密码、篡改拒绝、受管覆盖及线上密文字节一致性。
- `scripts/Replace-FitnessWorkbenchBackground.py`：安全替换已生成工作台的图片/MP4 背景，自动备份、检查并在失败时回滚。
- `scripts/Refresh-FitnessWorkbenchTemplate.py`：从正式页面刷新脱敏模板。
- `scripts/Validate-FitnessWorkbenchSkill.py`：检查 Skill 包完整性与可迁移性。
- `scripts/Test-FitnessWorkbenchWeekTransition.py`：回归验证跨周同步、频率、今日处方与自重语义。
- `scripts/Test-FitnessWorkbenchPortability.py`：把完整健身系统移动到新目录，验证计划、内置文档、全部页面资源和无 Obsidian 发布副本仍可用。
- `scripts/Test-FitnessWorkbenchRefresh.py`：隔离验证刷新顺序、失败回滚、隐私确认、发布哈希、四级状态与交接兼容。
- `scripts/Test-FitnessWorkbenchBackgroundReplacement.py`：验证静态、动态、初始化接入、目录移动、发布复制和损坏素材拒绝。
- `scripts/Migrate-FitnessWorkbenchSchema.py`：将保留的 schema 5 数据块安全迁移为 schema 6；正式页面仍应由数据生成器重新构建。
- `references/path-portability-repair.md`：AI 处理链接失效、旧绝对路径、系统迁移和发布假通过时的强制修复协议。
- `references/background-replacement.md`：AI 和用户执行壁纸替换时的命令、备份、取景与验收说明。
- `references/cloudbase-publishing.md`：仅在 CloudBase 发布任务中读取的隐私、鉴权与线上核验规则。
- `assets/workbench-template.html`：不含个人事实的界面模板。
- `assets/backgrounds/`：工作台内置视频、静态兜底和兼容图片。
- `assets/examples/`：匿名计划与 Notion 输入示例。
