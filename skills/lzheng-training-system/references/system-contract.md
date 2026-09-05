# 系统契约

## 主源

- 当前训练计划：`个人训练系统/训练与周期/当前周期` 中唯一有效的版本化 JSON。
- 当前执行基准：`个人训练系统/训练复盘与状态/当前执行基准`。
- 训练复盘：复盘文件及其 `INDEX.md`。
- 状态与接回：状态档案与接回卡；若状态过期，工作台不能把旧计划显示为今日处方。
- 动态训练/体重：可选 Notion 导出；缺失、过期或失败时显示状态，不静默沿用旧值。

## 正式产物归属

初始化后的健身系统根目录是正式产物的首选位置。除非用户本次明确指定其他交付目录，否则先读取 `系统/lzheng-system.json` 的 `output_locations`，并按以下固定分区写入：

- 建档快照：`个人训练系统/训练复盘与状态/状态档案`；
- 完整计划 JSON 与 HTML：`个人训练系统/训练与周期/当前周期`；
- 专项力量周期 JSON 与 HTML：`个人训练系统/训练与周期/力量周期`；
- 训练复盘：`个人训练系统/训练复盘与状态/训练复盘`；
- 状态快照与接回卡：`个人训练系统/训练复盘与状态/状态档案`。

临时渲染、测试、缓存和备份不得混入这些正式目录。完整计划 HTML 必须用相对链接从工作台打开，不得依赖固定盘符、Obsidian 仓库名称或生成时的绝对路径。

## 周切换原子同步

周复盘确认下一周处方后，必须按同一次更新完成：复盘与索引 → 当前计划 `schedule` → 交接记录 → 工作台刷新与校验。`schedule` 需覆盖今天，训练日使用唯一 Wn，数量等于 `plan.frequency`；今天为训练日时必须存在今日处方。历史动态记录只能补充计划未指定的重量，不能覆盖明确的“自重”。任一条件失败时拒绝刷新，不生成半新半旧的工作台。

## 保护边界

用户内容包括计划、复盘、状态档案、私人知识包和 Notion 导出。升级不得覆盖它们。系统托管文件的备份写到配置中 `backup_root`，不得在正式根目录创建版本副本。

`upgrade` 仅更新配置并报告界面状态，不代表用户 HTML 已升级。界面更换必须走独立 `upgrade-workbench-ui`，保留原绝对路径和数据块，候选与替换后浏览器验证通过才报告 `ui_upgraded`。未知界面自定义拒绝静默覆盖；HTML 备份不等于浏览器记录备份。详见 [界面升级](../../lzheng-fitness-workbench-builder/references/ui-upgrade.md)。

## 专家知识层

六个来源限定专家模块由 `lzheng-training-expert-library` 统一承载。计划、周期、复盘和接回 Skill 可按变量读取它，但专家库不拥有当前事实、计划版本、执行基准、最终处方或工作台写入权。升级可以更新公开蒸馏模块和登记表，不得把用户私人知识包合并进公开专家库。

## 套件配置

`系统/lzheng-system.json` 使用 schema 1，最少包含 `suite_version`、`project_root`、`skills_root`、`backup_root`、`portable_config_version`、`output_locations`、`managed_files`。默认值分别为相对当前系统根目录的 `个人训练系统`、运行时标记 `@runtime` 和 `系统/backups`。`doctor`、`upgrade`、`validate` 与 `process-handoffs` 必须先迁移旧电脑绝对路径，并在当前系统内留下可恢复的配置备份；旧路径即使仍存在，也不能覆盖当前位置的事实文件。缺失时先运行 `bootstrap` 或 `doctor`，不猜测其他机器的盘符。详细修复与旧路径迁移遵守 `../../lzheng-fitness-workbench-builder/references/path-portability-repair.md`。
