# 输入契约

## 必要事实

正式工作台至少需要以下事实：

1. 使用者称呼与品牌短名；
2. 一个文件名以 `-vNN.json` 结尾的当前计划；
3. 与该版本一致的执行基准 Markdown；
4. 复盘 `INDEX.md` 与索引实际指向的 Markdown 文件；
5. 可选的 Notion 导出 JSON。

这些正式事实优先放在初始化生成的个人训练系统内：完整计划进入 `训练与周期/当前周期`，专项周期进入 `训练与周期/力量周期`，复盘进入 `训练复盘与状态/训练复盘`，状态与接回卡进入 `训练复盘与状态/状态档案`。临时渲染和备份不得混入正式目录。

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

力量模式如接入 `main_lifts` 实际曲线，计划还必须能确定“主项 → 训练日职责”。显式 `plan.objective_mode=strength` 会启用真实性校验；显式 `hypertrophy`、`fat_loss` 或 `general_fitness` 会关闭该力量专用约束，即使输入保留了旧主项历史。旧计划未写目标模式时，仅在明确声明 `main_lift_tracking/main_lift_day_map`，或“力量”标题/目标同时存在主项周期表时兼容启用。构建器会优先读取 `plan.main_lift_day_map`，否则只从当前 `schedule` 的职责文字、主项动作和周期表强度日表头中推导；无法得到唯一映射时拒绝主项实际记录，不使用全局固定四分化猜测。例如自定义推拉腿计划可写：

```json
{
  "plan": {
    "main_lift_day_map": {
      "杠铃卧推": "推A",
      "负重引体": "拉A",
      "杠铃深蹲": "腿A",
      "硬拉": "腿B"
    }
  }
}
```

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

构建器必须按索引顺序投影全部有效复盘记录：索引有多少条，工作台 `reviews` 就生成多少条，不得截取最近 5 条或设置其他固定数量上限。

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
  "sync_mode": "incremental",
  "source_queried_at": "2026-01-05T22:30:00+08:00",
  "latest_training_record_date": "2026-01-05",
  "latest_bodyweight_record_date": "2026-01-05",
  "snapshot_generated_at": "2026-01-05T22:31:00+08:00",
  "bodyweight": [{"date": "2026-01-05", "kg": 70.0, "note": "最近实测"}],
  "baseline_kg": 70.0,
  "baseline_note": "周期基线",
  "sessions": [{"date": "2026-01-05", "day": "上肢A"}],
  "latest_by_exercise": {},
  "main_lifts": [{"name": "卧推", "week": 1, "value": 50, "detail": "50kg 4×5 @7", "date": "2026-01-05"}],
  "activity": [{"date": "2026-01-05", "steps": 8000, "cardio_minutes": 25}],
  "note": "数据来源说明"
}
```

### 查询时间与构建时间

- `source_queried_at`：连接器实际完成数据源查询的时间；无新查询的本地重建不得推进。
- `latest_training_record_date`：查询结果中最新训练记录的真实日期。
- `latest_bodyweight_record_date`：查询结果中最新体重记录的真实日期。
- `snapshot_generated_at`：本地快照文件生成时间，不代表 Notion 在此刻新增了训练记录。
- `last_sync`：旧输入兼容字段。缺少 `source_queried_at` 时会被当作其兼容值；新快照应写上述四个明确字段。

工作台自身构建时间由 `meta.updated_at` 和本地来源核验时间记录。没有传入 `--notion` 时，构建器只会使用正式页中的缓存，写入 `sync.source_state=cached`、`sync.merge_mode=preserved`，不得推进 `source_queried_at`、`last_success` 或上次查询尝试时间。

### full 与 incremental 模式

每份新快照应在 JSON 写明 `sync_mode`，也可在命令中使用 `--notion-mode incremental|full`；两处同时提供时必须一致。旧快照未声明模式时只为兼容按 `incremental` 处理并输出警告。

- `incremental`：只含新增或补充记录。构建器按稳定键与正式页历史合并，不得清空未出现在本次输入中的旧记录。
- `full`：声明四类历史是完整快照。若缺少正式页已有稳定键，默认拒绝，以防把局部查询误当全量历史。
- `--replace-main-lift-history`：仅允许配合 `full` 使用。它表示人工已核验整份 `main_lifts`，允许该字段权威纠错、删减或替换；不影响其他历史字段。

所有新增历史记录的 `date` 必须使用完整 `YYYY-MM-DD`。稳定键分别为：`bodyweight=完整日期`、`sessions=完整日期+day`、`main_lifts=归一化动作名+完整日期`、`activity=完整日期`。因此跨年同月同日不会合并，不同周期中同为 W1 的主项实际也会保留为两个点；`week` 只是该记录所属周期内的展示周次，不再作为跨周期身份键。

旧数据中的 `MM-DD` 会按同一快照的 `latest_training_record_date`（体重优先使用 `latest_bodyweight_record_date`）、`source_queried_at`、`snapshot_generated_at`、旧 `last_sync` 依次补全年份。同一年的旧 `08-15` 与新 `2026-08-15` 会归为同一稳定记录；如果快照没有任何可确定年份的元数据，构建器拒绝含 `MM-DD` 的历史，而不是用系统当前年份猜测。

同一稳定键已有非空事实与新输入不同即拒绝刷新；新输入只补充旧记录缺失字段时允许合并。`activity` 每个日期最多一条日汇总，可含 `steps`、`cardio_minutes`，因此也不会因局部快照丢失旧日期。

`main_lifts` 只写已经完成的主项强度职责记录。常见动作别名会归一为 `负重引体`、`卧推`、`深蹲`、`硬拉`；每条记录的 `date` 必须在 `sessions` 中存在，且训练日必须匹配当前计划得到的主项职责映射。缺失、过期、冲突或解析失败时拒绝刷新或显示待同步，不得把旧记录、未来计划值或容量日记录冒充当前事实。

推荐命令：

```powershell
python "<skill>/scripts/Build-FitnessWorkbenchData.py" --project "<项目根目录>" --notion "<notion-data.json>" --notion-mode incremental --check-only
python "<skill>/scripts/Build-FitnessWorkbenchData.py" --project "<项目根目录>" --notion "<完整-notion-data.json>" --notion-mode full --replace-main-lift-history --check-only
```
