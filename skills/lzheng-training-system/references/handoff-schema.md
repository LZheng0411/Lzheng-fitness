# LZHENG_HANDOFF schema 1

交接文件只传递已确认事实、产物路径与下一步动作，不复制用户数据库。保存到 `个人训练系统/工作台与工具/交接记录/`；文件名为 `YYYYMMDD-HHMM-<event>.json`。

```json
{
  "schema": 1,
  "source_skill": "lzheng-strength-training-review",
  "target_skill": "lzheng-fitness-workbench-builder",
  "user_system_id": "local",
  "event_type": "training_review_completed",
  "created_at": "2026-08-14T00:00:00+08:00",
  "artifacts": [{"type": "review", "path": "训练复盘与状态/训练复盘/example.md"}],
  "requires": {"refresh_workbench": true, "merge_into_current_plan": false},
  "warnings": []
}
```

仅当相关事实已确认时创建。完成专业产物后运行总控的 `process-handoffs`；它只消费已确认产物，刷新成功后回写 `delivery.status: refreshed`，失败时保留交接记录并写入 `delivery.status: failed`，不得宣称工作台已同步。

- `refresh_workbench: true`：由总控刷新唯一正式工作台；未提供新 Notion 导出时会保留页面内最近一次已核验数据，并重新做新鲜度判断。
- `merge_into_current_plan: true`：总控只标记 `awaiting_merge`，绝不让专项周期直接替代当前计划。
- `artifacts[].path` 必须是项目根目录内已存在的相对路径；越界或缺失时拒绝消费。
