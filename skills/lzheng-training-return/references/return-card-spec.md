# 《Lzheng 个人训练接回卡》规范

## 文件信息

- 标题：`Lzheng 个人训练接回卡｜用户代号｜YYYY-MM-DD`
- 模式：`personal` 或 `client`
- 生成时间与时区
- 对应的中断前状态快照和当前状态快照
- 信息来源：用户确认、已授权外部记录、历史计划、推断、未知

## 卡片正文

### 1. 你现在处于什么状态

- 中断时长与主要原因；
- 恢复权限：正常 / 降级 / 最低 / 暂缓；
- 本周唯一主目标；
- 本周明确不做的事。

### 2. 48小时行动

- 具体日期或时间窗口；
- 地点和所需器械；
- 启动动作；
- 如果临时只有 10 分钟怎么办。

### 3. 第一次训练三档

用同一组字段列出正常、降级、最低三档：动作、组次或时长、RPE/RIR、休息、停止条件、完成后的记录项。

### 4. 七天安排

按 Day 1—Day 7 表示训练、恢复、记录和复盘，不要求每天训练。

### 5. 如何决定下一步

- 升级标准；
- 保持标准；
- 降级标准；
- 暂停并寻求评估的标准。

### 6. 待确认信息

分别列出已确认事实、推断、未知，以及哪项未知会改变计划。

### 7. 参考依据

简化显示本次实际读取的本地资料、联网核验、用户事实，以及每项资料支持的判断。不得把未读取的书籍列为来源。

## 状态快照字段

接回卡应伴随一个不可覆盖的状态快照，至少包含：

```text
snapshot_id
created_at
timezone
subject_code
mode
interruption_start
last_training_at
interruption_days
interruption_reasons
safety_status
current_symptoms
previous_plan_reference
previous_snapshot_reference
current_time_equipment_constraints
return_permission
confirmed
inferred
unknown
knowledge_sources
```

文件名须包含时间戳或唯一 ID。不得覆盖中断前状态档案。
