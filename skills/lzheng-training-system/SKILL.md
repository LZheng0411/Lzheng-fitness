---
name: lzheng-training-system
description: 初始化、升级、诊断、校验和迁移 Lzheng 本地训练系统，并把完整计划、专项力量周期、训练复盘、停训接回与健身工作台按统一配置和交接契约串成单一主源闭环。用于新电脑搭建、系统升级、工作台异常排查、导入私人知识包或检查本地训练系统是否可用；不用于直接生成个人训练处方或医疗建议。
---

# Lzheng 本地训练系统

把本 Skill 当作套件总控层：它只做安装、配置、路由、升级保护和验收；训练处方仍分别由五个专业 Skill 生成。

## 先选动作

| 用户意图 | 动作 |
| --- | --- |
| 新电脑、空文件夹、从零搭建 | `bootstrap` |
| 检查路径、数据主源、Skill、工作台或链接 | `doctor` |
| 升级本地系统 | `upgrade` |
| 只装/检查某个专业 Skill | `install-skill` |
| 导入用户自己的知识、书摘或资料包 | `import-private-pack` |
| 消费正式计划、复盘或接回后的交接并刷新工作台 | `process-handoffs` |
| 升级后或发布前做完整回归 | `validate` |
| 日常训练任务 | 按下方路由转交专业 Skill |

运行前读取 [系统契约](references/system-contract.md)。涉及交接时读取 [交接契约](references/handoff-schema.md)。

## 日常路由

1. 完整建档、长期训练计划、短版降级：`lzheng-fitness-plan`。
2. 一个动作的 8—12 周力量周期：`lzheng-strength-cycle-planner`；结果必须交回完整计划 Skill 合并后才可成为当前计划。
3. 单练或周训练复盘、下一次处方：`lzheng-strength-training-review`；正式复盘必须更新索引并触发工作台刷新。
4. 停训 7 天、连续漏练 3 次、条件明显变化：`lzheng-training-return`；改变执行状态时先更新执行基准或当前计划，再刷新工作台。
5. 工作台构建、数据刷新、迁移、发布：`lzheng-fitness-workbench-builder`；它只读聚合，不给出处方。

专业 Skill 执行前按以下优先级解析根目录：本次用户明确路径 → `系统/lzheng-system.json` → 环境变量 `LZHENG_FITNESS_HOME` → 仅用于首次引导的保守默认目录。未解析到系统时停止写入并说明缺失项，不把示例数据当作训练事实。

## 命令

```powershell
python scripts/lzheng_training_system.py bootstrap --target "<空目录>"
python scripts/lzheng_training_system.py doctor --root "<系统根目录>"
python scripts/lzheng_training_system.py upgrade --root "<系统根目录>"
python scripts/lzheng_training_system.py install-skill --root "<系统根目录>" --name lzheng-fitness-plan
python scripts/lzheng_training_system.py import-private-pack --root "<系统根目录>" --source "<用户明确指定的目录>"
python scripts/lzheng_training_system.py process-handoffs --root "<系统根目录>" [--notion "<notion-data.json>"]
python scripts/lzheng_training_system.py validate --root "<系统根目录>"
```

`bootstrap` 仅接受空目录；`upgrade` 只更新托管配置与模板清单，发现用户改过的托管文件时保留原件并报告冲突；私人知识、计划、复盘、状态档案和 Notion 导出永不覆盖。所有命令均使用 UTF-8，兼容中文、空格和非系统盘路径。

## 完成闸门

只有以下全部通过才可说本地系统可用：

- `doctor` 显示配置、五个专业 Skill、主源目录和工作台均可用；
- `validate` 通过每个 Skill 的快速校验、工作台数据/HTML 检查和隐私扫描；
- 在新的隔离空目录 `bootstrap` 成功，并显示“待建档”而不是假重量；
- 每次正式复盘和接回均生成 `LZHENG_HANDOFF`，经 `process-handoffs` 刷新成功或明确报告失败。
