# `plan_contract` 数据协议

JSON 是状态、文字计划和 HTML 的唯一数据源。先验证 JSON，再渲染页面；不得分别手写两套处方。

## 顶层字段

| 字段 | 类型 | 作用 |
| --- | --- | --- |
| `plan_meta` | object | 标题、版本、日期、周期、目标和使用者模式 |
| `profile_snapshot` | object | 状态快照引用、准备状态和 P0—L3 分层 |
| `safety_status` | object | `clear/caution/blocked`、限制和停止信号 |
| `goals` | object | 主目标、副目标和成功标准 |
| `equipment` | object | 场地、可用/不可用器械、最小加重 |
| `movement_profile` | array | 单动作阶段、证据和当前角色 |
| `weekly_schedule` | array | 一周日历和训练日引用 |
| `training_days` | array | 动作与标准/短版处方 |
| `movement_coverage` | array | 动作模式或肌群覆盖审计 |
| `progression_rules` | array | 条件式渐进规则 |
| `minimum_versions` | array | 全局 30/20/10 分钟原则 |
| `short_interruption_rules` | object | 漏练 1—2 次和转恢复 Skill 阈值 |
| `cycle_links` | array | 经用户明确确认的单项周期引用 |
| `review_checkpoints` | array | 复盘时间、数据和决策 |
| `knowledge_sources` | array | 实际读取和使用的来源 |
| `assumptions` | array | 估算、未知和待确认项 |

## 动作处方

每个 `training_days[].exercises[]` 至少包含：

```json
{
  "id": "day-a-leg-press",
  "name": "腿举",
  "pattern": "膝主导",
  "modality": "固定器械",
  "equipment": "腿举机",
  "prescription": {
    "sets": "3",
    "reps": "8—12",
    "intensity": "首组 RPE 6→末组 RPE 7",
    "rest": "90—120 秒"
  },
  "purpose": "建立股四头肌基础训练量",
  "priority": "main",
  "selection_reason": "P0 阶段优先使用稳定、容易调节负荷的膝主导动作",
  "alternatives": ["哈克深蹲", "箱式杯式深蹲"],
  "technique_checks": ["全脚掌稳定", "膝盖跟随脚尖", "不锁死膝盖"]
}
```

`priority` 使用 `main`、`key` 或 `optional`。P0 计划若安排地面传统/杠铃硬拉，必须额外写 `admission_confirmed: true` 和非空 `admission_evidence`，并在 `movement_profile` 中保存同一动作或髋铰链的 `admission_confirmed: true` 记录与明确证据。

## 负荷与校准

每个 `training_days[].exercises[]` 必须包含 `load`，不允许把“自行选择重量”留给使用者：

```json
{
  "status": "verified",
  "working_weight": "40",
  "unit": "kg",
  "source": "2026-08-14 卧推 40kg 4×6，末组 RIR 2",
  "next_rule": "四组均完成 6 次且末组保留至少 2 次余力，下次 42.5kg；否则保持。"
}
```

未知重量使用 `calibration_required`，必须给出 `starting_instruction` 和 `decision_rule`。无公斤数的自重、有氧或时间动作使用 `not_weight_based`，必须给出 `progression_metric`。校准结果写回后才可替换为 `verified`；疼痛、异常或动作变形不进入普通加重。

客户模式的 `plan_meta.subject_id` 只允许脱敏代号，不得出现 `real_name`、`full_name`、`phone`、`email`、`contact` 或 `medical_history_raw` 字段。`safety_status.status` 为 `blocked` 时，`weekly_schedule` 和 `training_days` 可以为空，但不得含普通训练处方。

## 训练日短版

每个训练日保存：

```json
"minimum_versions": {
  "minutes_30": {"exercise_ids": ["..."], "note": "..."},
  "minutes_20": {"exercise_ids": ["..."], "note": "..."},
  "minutes_10": {"exercise_ids": ["..."], "note": "..."}
}
```

短版引用原计划动作 ID，不另外创造一套无关动作。

## 来源记录

每个 `knowledge_sources[]` 必须包含：

```json
{
  "source_type": "local_book",
  "source_title": "The Muscle and Strength Training Pyramid v2.0 Training",
  "local_path_or_url": "references/program-design.md",
  "chapter_or_section": "Progressions Based on Training Age",
  "rule_used": "按可靠进步的时间尺度分层，不按训练年限机械分级",
  "accessed_at": "2026-08-03T19:30:00+08:00",
  "evidence_role": "trainee_classification"
}
```

只列本次实际读取的来源。用户陈述和经授权的外部训练记录也作为 `user_fact`、`external_record` 来源保存。

## 周期调用

`cycle_links[]` 状态为 `active` 时必须包含：

- `movement`；
- `skill: lzheng-strength-cycle-planner`；
- `explicit_user_request: true`；
- `source_plan_id` 或生成的周期文件路径；
- 该周期在整周中的训练日和疲劳职责。

没有用户明确要求或确认时保持空数组。

## 文件命名

- JSON：与 HTML 同名，仅扩展名为 `.json`；
- 新计划：`YYYY年MM月DD日-训练结构-阶段目标训练计划.html`；
- 客户模式：加入客户代号，不加入真实姓名；
- 修订：保留首次制定日期并追加 `-v02`，禁止覆盖或使用“最终版”。
