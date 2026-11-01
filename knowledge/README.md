# 训练知识与执行规则

公开知识层包括来源限定的六个专家模块和可追溯的训练决策协议，不包含使用者的训练记录、原书、付费课程或私人知识正文。

| 要解决的问题 | 读取入口 |
| --- | --- |
| 逐组数据、目标、RPE、渐进与失败反馈 | [共同训练判断协议](../skills/lzheng-strength-training-review/references/training-progression-protocol.md) |
| 力量、增肌、减脂保肌的不同推进顺序 | 同上；先识别目标和每组职责，不能把 RPE 直接换算成公斤 |
| 训练结构、周期化、减载、增肌或营养证据 | [六个专家模块](../skills/lzheng-training-expert-library/SKILL.md)及其来源、适用范围和验证状态 |
| 读取当前记录并形成复盘 | [训练复盘 Skill](../skills/lzheng-strength-training-review/SKILL.md) |
| 设计力量周期并交回完整计划 | [周期 Skill](../skills/lzheng-strength-cycle-planner/SKILL.md) |
| 工作台展示自己的学习材料 | [知识库 Skill](../skills/lzheng-knowledge-library/SKILL.md)；默认空白，由使用者选择导入 |

[training-progression.json](training-progression.json) 是协议的生成副本，带版本与 SHA-256，方便工具读取；不要直接编辑。更新协议后运行 `node tools/sync_training_protocol.cjs --write` 与 `--check`。维护者的内置 AI 仍需按其既有同步流程检查同一协议，生成副本一致不等于真实模型行为已经通过验收。

资料接入、内容核验、规则采纳和公开发布是不同状态。未经核验的文章与个人学习草稿不能自动变成默认训练规则；知识或软件升级也不修改使用者已确认的训练计划。外部材料按其来源与许可选择，不能将个人知识库整体复制成公开包。
