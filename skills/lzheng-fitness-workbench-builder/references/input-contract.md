# 输入契约

## 必要事实

正式工作台至少需要以下事实：

1. 使用者称呼与品牌短名；
2. 一个文件名以 `-vNN.json` 结尾的当前计划；
3. 与该版本一致的执行基准 Markdown；
4. 复盘 `INDEX.md` 与索引实际指向的 Markdown 文件；
5. 可选的 Notion 导出 JSON。

初始化脚本可以生成结构完整的示例计划、初始化复盘和执行基准，用于验证页面是否能工作。示例重量不是训练建议，正式使用前必须替换。

## 计划 JSON

根节点包含：

- `plan`：`title`、`weeks`、`athlete`、`goal`、`frequency`、`constraints`、`baseline`；
- `phases`：阶段名及起止周；
- `schedule`：实际日期、训练日职责、动作；
- `cycles`：四个主项的周计划与图表；
- `rules`：页面规则卡片。

每个训练动作至少包含 `name`、`sets`、`target`。四个主项使用统一名称：`负重引体`、`杠铃卧推`、`杠铃深蹲`、`硬拉`。主项必须有可执行重量、组次和 RPE/RIR；未知时先补事实，不得臆测。

当前 `schedule` 是今日处方的唯一排程主源，必须满足：

- 有日期的事件覆盖今天所在的当前七日范围；
- 每个训练日都写真实日期与同一个 `Wn` 标签；
- 训练日数量与 `plan.frequency` 一致，日期和训练日标识不得重复；
- 休息/恢复日也保留日期，使时间线可逐日复现当前排程；
- `sets` 明确写“自重”时，输出必须保留“自重”，不得用历史负重补写。

周复盘进入下一周时，先更新这里，再刷新工作台；旧周 `schedule` 不得继续充当新周训练卡。

参考完整结构：`../assets/examples/plan-template-v01.json`。

## 执行基准

执行基准至少包含：

```yaml
---
status: 执行中
period: 2026-01-05 至 2026-03-01
source_plan: [[训练与周期/当前周期/个人训练计划-v01|个人训练计划 v01]]
---
```

`source_plan` 的版本必须与当前计划文件名一致。

## 复盘索引

索引使用六列表格：

```markdown
| 日期 | 周次 | 训练日 | 主判断 | 状态 | 文件 |
| --- | --- | --- | --- | --- | --- |
| 2026-01-05 | W1 | 系统初始化 | 等待首练 | 待补充 | [[2026-01-05-W1-工作台初始化记录]] |
```

文件列必须指向真实 Markdown。复盘 frontmatter 可提供工作台摘要：

```yaml
workbench_title: W1 上肢A复盘
workbench_lead: 主项完成，动作稳定
workbench_points:
  - 顶组重量与 RPE
  - 技术表现
  - 恢复信号
workbench_decision: 下次保持或调整的明确决定
```

## Notion JSON

Notion 不是构建依赖。提供时使用：

```json
{
  "last_sync": "2026-01-05T22:30:00+08:00",
  "bodyweight": [{"date": "2026-01-05", "kg": 70.0, "note": "最近实测"}],
  "baseline_kg": 70.0,
  "baseline_note": "周期基线",
  "sessions": [{"date": "01-05", "day": "上肢A"}],
  "latest_by_exercise": {},
  "main_lifts": [{"name": "卧推", "week": 1, "value": 50, "detail": "50kg 4×5 @7", "date": "01-05"}],
  "activity": [{"date": "2026-01-05", "steps": 8000, "cardio_minutes": 25}],
  "note": "数据来源说明"
}
```

`activity` 是可选字段，仅在减脂或用户主动追踪活动量时使用；每条记录可含 `date`、`steps`、`cardio_minutes`，缺失即显示待记录。缺失、过期或解析失败时，页面必须显示待同步状态，不得把旧记录冒充当前事实。
