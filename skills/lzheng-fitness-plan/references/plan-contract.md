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
| `movement_coverage` | array | 供 AI 审计的动作模式覆盖，不直接展示在计划页 |
| `progression_rules` | array | 条件式渐进规则 |
| `minimum_versions` | array | 全局 30/20/10 分钟原则 |
| `short_interruption_rules` | object | 漏练 1—2 次和转恢复 Skill 阈值 |
| `cycle_links` | array | 经用户明确确认的单项周期引用 |
| `review_checkpoints` | array | 复盘时间、数据和决策 |
| `tracking_targets` | array | 目标专属的长期追踪指标；无基线时明确标记待记录 |
| `knowledge_sources` | array | 实际读取和使用的来源 |
| `assumptions` | array | 估算、未知和待确认项 |

`plan_meta.frequency` 固定写作 `每周 N 练`（N 为 1—7），并必须等于 `weekly_schedule` 中非空 `day_id` 的数量。`weekly_schedule.day_index` 必须是 1—7 内不重复的整数；每个 `training_days.id` 至少被排入一周一次。同一训练日可以在不同 `day_index` 重复，覆盖量会按真实出现次数累计。

## 动作处方

每个 `training_days[].exercises[]` 至少包含：

```json
{
  "id": "day-a-leg-press",
  "name": "腿举",
  "pattern": "膝主导",
  "pattern_group": "蹲",
  "modality": "固定器械",
  "equipment": "腿举机",
  "prescription": {
    "sets": "3",
    "set_count": 3,
    "reps": "8—12",
    "intensity": "首组 RPE 6→末组 RPE 7",
    "rest": "90—120 秒"
  },
  "muscle_contributions": [
    {"muscle_group": "股四头肌", "coefficient": 1.0},
    {"muscle_group": "臀部", "coefficient": 0.5}
  ],
  "purpose": "建立股四头肌基础训练量",
  "priority": "main",
  "selection_reason": "P0 阶段优先使用稳定、容易调节负荷的膝主导动作",
  "alternatives": ["哈克深蹲", "箱式杯式深蹲"],
  "technique_checks": ["全脚掌稳定", "膝盖跟随脚尖", "不锁死膝盖"]
}
```

`prescription.sets` 固定为正整数字符串，`prescription.set_count` 是同一数字的整数形式，用于机器计算周组数；两者不一致会被拒绝。

`priority` 使用 `main`、`key` 或 `optional`。P0 计划若安排地面传统/杠铃硬拉，必须额外写 `admission_confirmed: true` 和非空 `admission_evidence`，并在 `movement_profile` 中保存同一动作或髋铰链的 `admission_confirmed: true` 记录与明确证据。

## 动作模式与肌群贡献

每个动作必须写入一个固定 `pattern_group`：`蹲`、`髋铰链`、`推`、`拉`、`单腿` 或 `核心`。页面按 `set_count × 该训练日每周出现次数` 自动计算模式周组数。底层仍以固定枚举完成校验和汇总，页面只显示周组数大于 0 的实际覆盖模式。

每个动作必须写非空 `muscle_contributions`，至少包含一项 `1.0` 直接贡献；只允许 `1.0` 和 `0.5` 两种系数。健美肌群名称固定为：`胸肌`、`背阔肌`、`上背/中背`、`下背/竖脊肌`、`肩前束`、`肩中束`、`肩后束`、`肱二头肌`、`肱三头肌`、`股四头肌`、`腘绳肌`、`臀部`、`小腿`、`核心`。

页面汇总公式固定为：直接组 `set_count × 周频次 × 1.0`，间接折算 `set_count × 周频次 × 0.5`，合计为两者之和，并逐项列出动作来源。固定 14 类肌群继续作为底层校验和计算全集，页面只显示合计大于 0 的实际覆盖肌群。`0.5` 是统一的计划估算口径，不表示对每个人的精确生理刺激；计划量也不表示实际完成量。未知动作没有可靠映射时不得猜测，应先补充动作映射或更换为已定义动作。

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

## 目标追踪

`plan_meta.goal_mode` 必须是 `strength`、`hypertrophy`、`fat_loss` 或 `general_fitness`。只要计划声明了目标类型，`tracking_targets` 就是必填项：力量至少包含 `training_completion`、`key_lift_performance`、`cycle_decision`；增肌至少包含 `training_completion`、`planned_sets`、`progression_log`；减脂至少包含 `training_completion`、`bodyweight_trend`、`daily_steps`、`cardio_minutes`；综合健身至少包含 `training_completion`。旧计划缺少目标类型时仅按兼容模式展示，不能作为新计划模板。

`tracking_targets` 只保存用户已经确认、可被记录的目标数据；没有基线或目标值时不编造数字，应写入 `status: "needs_baseline"` 和下一步收集动作。每一项至少包含：

```json
{
  "id": "daily_steps",
  "label": "日均步数",
  "kind": "daily_steps",
  "source": "notion.activity.steps",
  "status": "needs_baseline",
  "next_action": "先记录 7 天步数，再由 AI 确认下一阶段目标。"
}
```

- 增肌：至少追踪训练完成、重点肌群计划组数、每个重点动作的重量／次数／余力；工作台把计划组数标成“计划量”，只有复盘结果才是完成量。
- 减脂：至少追踪力量训练完成、体重趋势、日均步数和有氧时长。步数、有氧与体重目标必须来自用户记录或本次确认，不能默认填一个漂亮数字。
- 力量：追踪训练完成、关键动作实际表现与周期判定；有专项周期时继续使用对应曲线。

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

## 复盘节点

`review_checkpoints[]` 按时间先后排列。到达每个节点时，AI 必须先向用户确认该节点要求收集的实际训练反馈，再执行 `decision`；不得让用户仅凭静态表格自行判断。最后一个节点视为本计划的周期末复盘，AI 在确认实际完成、余力、动作稳定性与恢复后，生成下一阶段计划。周期未结束或反馈不足时，不提前编造下一阶段精确处方。

## 文件命名

- JSON：与 HTML 同名，仅扩展名为 `.json`；
- 新计划：`YYYY年MM月DD日-训练结构-阶段目标训练计划.html`；
- 客户模式：加入客户代号，不加入真实姓名；
- 修订：保留首次制定日期并追加 `-v02`，禁止覆盖或使用“最终版”。
