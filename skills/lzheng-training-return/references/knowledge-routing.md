# Lzheng 训练中断恢复知识路由

## 固定读取

每次生成接回方案前读取：

1. `references/return-workflow.md`；
2. `references/return-card-spec.md`；
3. `references/evidence-base.md`；
4. 用户本次确认的中断事实、最近状态快照、原计划和最后一次训练。

找不到原计划时标记 `unknown`，使用保守重新评估周，不得推测停训前重量。

## 按问题扩展

- 训练压力回退：读取 `return-workflow.md` 的中断长度与负荷回退规则。
- 动作、器械或能力明显改变：路由 `lzheng-fitness-plan` 重新分层。
- 用户明确要求单项 8—12 周周期：路由 `lzheng-strength-cycle-planner`。
- 中断伴随健康、安全或特殊人群问题：读取 `evidence-base.md`，并联网核验当前官方或原始来源。

## 来源优先级

```text
当前安全与官方标准
→ 用户本次明确确认
→ 已授权且可核验的当前训练记录
→ 最近状态快照与原计划
→ Skill 内置接回规则
```

## 来源记录

每个关键判断记录 `source_type`、`source_title`、`local_path_or_url`、`chapter_or_section`、`rule_used`、`accessed_at` 和 `evidence_role`。用户事实写 `user_current_confirmation`；外部记录使用脱敏标识。未知信息不得伪造来源。
