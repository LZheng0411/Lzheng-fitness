---
name: lzheng-training-system
description: 初始化、升级、诊断、校验和迁移 Lzheng 本地训练系统，并把增肌、减脂、力量与综合健身计划、训练复盘和健身工作台串成单一主源闭环。用于用户刚下载/刚安装、说开始建立健身系统、想增肌/减脂/提升力量、新电脑搭建、系统升级或工作台异常排查；首次使用时由 AI 自然语言接管引导，不要求用户先找 README、命令或 Skill 名称。
---

# Lzheng 本地训练系统

把本 Skill 当作套件总控层：它只做安装、配置、路由、升级保护和验收；训练处方由四个训练处方 Skill 生成，营养系统独立维护 `nutrition_contract`，专家库只作为共享知识层，工作台只负责展示。

## 首次使用者引导

当用户刚完成安装、刚下载本套件，或第一次说“开始”“想增肌/减脂/提升力量”“帮我建立健身系统”时，不要要求用户先阅读 README、输入命令或记住 Skill 名称。直接回复：

> 我来帮你建立个人健身系统。先确定你的主要目标：增肌、减脂、力量，还是综合改善？

随后依次完成：

1. 询问目标、近期训练、时间、器械、恢复、限制和可用记录；
2. 没有可靠动作重量时安排负荷校准，不让用户自行猜重量；
3. 初始化新的空目录、工作台和事实文件；
4. 生成第一版正式计划，将它接入当前周期、执行基准、复盘索引和工作台；
5. 告诉用户以后只需说“今天练了什么”和主观体感，AI 负责下一次明确处方与刷新。

若当前聊天尚未加载新 Skill，提示用户只需新开对话后说“开始建立我的健身系统”；不得让用户阅读 README 寻找下一步。

## 先选动作

| 用户意图 | 动作 |
| --- | --- |
| 新电脑、空文件夹、从零搭建 | `bootstrap` |
| 检查路径、数据主源、Skill、工作台或链接 | `doctor` |
| 日常任务读取当前状态，不加载整份工作台 HTML | `inspect` |
| 升级系统配置并检查界面状态 | `upgrade`（仅配置；需要界面升级时退出码 2） |
| 修复侧栏或升级已有工作台界面，保留事实和壁纸 | `upgrade-workbench-ui` |
| 只装/检查某个专业 Skill | `install-skill` |
| 导入用户自己的知识、书摘或资料包 | `import-private-pack` |
| 刷新正式工作台并生成可审计回执，可选准备本地发布副本 | `refresh-workbench` |
| 消费正式计划、复盘或接回后的交接并刷新工作台 | `process-handoffs` |
| 升级后或发布前做完整回归 | `validate` |
| 日常训练任务 | 按下方路由转交专业 Skill |

运行前读取 [系统契约](references/system-contract.md)。涉及交接时读取 [交接契约](references/handoff-schema.md)。涉及完整计划、力量周期或工作台 HTML 时读取 [单文件 HTML 模板总契约](references/html-template-contract.md)，只允许使用其中登记的三套固定模板。

日常计划修改、训练复盘和状态确认先运行 `inspect`。`--root` 可指向含 `系统/lzheng-system.json` 的完整系统根目录，也可直接指向含 `健身工作台.html` 的训练项目根目录。它只输出紧凑状态和权威主源路径；随后按任务读取对应的一个计划、基准或复盘文件。除非正在开发视觉模板或检查器已经报告模板结构损坏，不得读取整份 `健身工作台.html`、工作台模板、历史计划目录或全部专家模块。

## 日常路由

1. 完整建档、长期训练计划、短版降级：`lzheng-fitness-plan`。
2. 一个动作的 8—12 周力量周期：`lzheng-strength-cycle-planner`；结果必须交回完整计划 Skill 合并后才可成为当前计划。
3. 单练或周训练复盘、下一次处方：`lzheng-strength-training-review`；正式复盘必须更新索引并触发工作台刷新。
4. 停训 7 天、连续漏练 3 次、条件明显变化：`lzheng-training-return`；改变执行状态时先更新执行基准或当前计划，再刷新工作台。
5. 饮食建档、日型目标、餐食确认与两周趋势复盘：`lzheng-nutrition-system`；它不按单次训练消耗补吃，也不自动确认照片估算。
6. 工作台构建、数据刷新、迁移、发布：`lzheng-fitness-workbench-builder`；它只读聚合，不给出处方。

四个训练处方 Skill 与营养 Skill 在需要来源限定判断时内部读取 `lzheng-training-expert-library`。专家库不是独立处方入口，不拥有当前事实、计划版本、营养协议或工作台写入权。

专业 Skill 执行前按以下优先级解析根目录：本次用户明确路径 → `系统/lzheng-system.json` → 环境变量 `LZHENG_FITNESS_HOME` → 仅用于首次引导的保守默认目录。已存在系统配置时，计划、周期、复盘、状态和接回卡必须优先写入 `output_locations` 指定的知识库分区，不得继续散落到当前工作目录。未解析到系统时停止写入并说明缺失项，不把示例数据当作训练事实。

## 命令

```powershell
python scripts/lzheng_training_system.py bootstrap --target "<空目录>"
python scripts/lzheng_training_system.py doctor --root "<系统根目录>"
python scripts/lzheng_training_system.py inspect --root "<系统根目录>"
python scripts/lzheng_training_system.py upgrade --root "<系统根目录>"
python scripts/lzheng_training_system.py upgrade-workbench-ui --root "<系统根目录>" --check-only
python scripts/lzheng_training_system.py upgrade-workbench-ui --root "<系统根目录>" --apply
python scripts/lzheng_training_system.py install-skill --root "<系统根目录>" --name lzheng-fitness-plan
python scripts/lzheng_training_system.py import-private-pack --root "<系统根目录>" --source "<用户明确指定的目录>"
python scripts/lzheng_training_system.py refresh-workbench --root "<系统根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full]
python scripts/lzheng_training_system.py process-handoffs --root "<系统根目录>" [--notion "<notion-data.json>" --notion-mode incremental|full]
python scripts/lzheng_training_system.py validate --root "<系统根目录>"
```

`bootstrap` 仅接受空目录；`upgrade` 只更新托管配置与模板清单，发现用户改过的托管文件时保留原件并报告冲突；私人知识、计划、复盘、状态档案和 Notion 导出永不覆盖。所有命令均使用 UTF-8，兼容中文、空格和非系统盘路径。

`refresh-workbench` 是日常单命令闸门：先预检数据，再 apply，随后用正式 checker 验证；可选增加 `--deploy "<本地发布目录>" --release-mode public-anonymized`。若选择 `private-portable`，必须再传 `--confirm-private-portable`，明确承认副本含完整个人训练数据且只能进入有鉴权的私有环境。命令生成 JSON 回执，分别记录 `formal_refreshed`、`release_prepared`、`deployed`、`online_verified`；它不执行上传或线上访问，所以后两项不能变成 `true`。

整份主项实际历史的权威替换属于高风险例外：只允许在显式提供 `--notion "<完整快照>" --notion-mode full --replace-main-lift-history --confirm-replace-main-lift-history` 时执行；普通同步和 `process-handoffs` 不得携带该替换权限。

`process-handoffs` 复用同一刷新闸门。只有回执中的正式 checker 为 PASS，交接才标记 `formal_refreshed`；旧版 `refreshed` 仍会被识别为已处理并跳过。交接成功不自动制作发布副本，更不代表网站已更新。

## 完成闸门

只有以下全部通过才可说本地系统可用：

- `doctor` 显示配置、四个训练处方 Skill、营养 Skill、专家库、工作台构建器、主源目录和工作台均可用；
- `validate` 通过每个 Skill 的快速校验、工作台数据/HTML 检查和隐私扫描；
- 在新的隔离空目录 `bootstrap` 成功，并显示“待建档”而不是假重量；
- 整套系统移动到不同盘符或改名后，旧绝对路径自动迁移，`doctor` 与 `upgrade` 继续通过；
- 每次正式复盘和接回均生成 `LZHENG_HANDOFF`，经 `process-handoffs` 获得带 checker PASS 和回执哈希的 `formal_refreshed`，或明确报告失败。
