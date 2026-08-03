# Lzheng 健身计划知识路由

## 固定读取

制定完整计划时先读取本 Skill 内的：

1. `references/evidence-base.md`；
2. `references/intake-and-state-snapshot.md`；
3. `references/trainee-classification.md`；
4. `references/exercise-selection.md`；
5. `references/program-design.md`；
6. 用户本次资料、最近状态快照和当前有效计划。

外部训练记录只在用户授权并且当前环境能够访问时使用。无法访问时，不阻断计划生成；把动态事实来源标为 `user_current_confirmation`，并将缺失信息列入假设。

## 问题路由

| 当前问题 | 内置来源 | 需要联网核验 |
| --- | --- | --- |
| 安全筛查、异常症状、特殊状态 | `evidence-base.md`、`intake-and-state-snapshot.md` | 当前 ACSM、WHO 或相关专业机构正式指南 |
| P0—L3 和动作分层 | `trainee-classification.md` | 通常不需要，除非涉及特殊人群 |
| 固定器械与自由重量 | `exercise-selection.md` | 通常不需要 |
| 深蹲、卧推、硬拉、推举、引体 | `exercise-selection.md` | 出现疼痛、术后或康复问题时需要专业来源 |
| 增肌、基础力量和综合计划 | `program-design.md`、`evidence-base.md` | 容易变化的正式立场需核验 |
| 单项力量周期 | 用户确认后路由 `lzheng-strength-cycle-planner` | 按该 Skill 的证据规则 |
| 有氧和健康活动量 | `program-design.md`、`evidence-base.md` | WHO 或 ACSM 当前官方建议 |
| 中断后接回 | 短期用 `program-design.md`；长期路由 `lzheng-training-return` | 中断伴随健康问题时核验 |

## 来源优先级

```text
用户当前事实：本次明确确认 > 已授权且可核验的当前记录 > 时间快照 > 历史记录
训练规则：当前官方安全标准 > 多来源一致证据 > Skill 内置稳定规则 > 单一模板
```

本地旧资料与当前官方指南冲突时采用当前官方标准，并在计划中说明差异。不得把没有实际读取的书、网页或记录列为来源。

## 来源记录

每个实际使用的来源记录：

- `source_type`
- `source_title`
- `local_path_or_url`
- `chapter_or_section`
- `rule_used`
- `accessed_at`
- `evidence_role`

内置资料使用相对路径，例如 `references/program-design.md`。用户事实使用 `user_current_confirmation`。外部记录使用经过脱敏、可追溯的标识，不记录访问令牌或无关隐私。
