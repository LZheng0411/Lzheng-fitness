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

仅当相关事实已确认时创建。完成专业产物后运行总控的 `process-handoffs`；它只消费已确认产物。只有单命令刷新回执同时证明 builder check、apply 与正式 checker 全部通过，才回写 `delivery.status: formal_refreshed`。失败时保留交接记录并写入 `delivery.status: failed`，不得宣称工作台已同步。

```json
{
  "delivery": {
    "status": "formal_refreshed",
    "processed_at": "2026-08-23T15:00:00+08:00",
    "detail": "正式工作台已重新构建且通过 checker；未准备发布副本、未部署、未验证线上。",
    "evidence": {
      "receipt_scope": "external-local",
      "receipt_file": "20260823-150000-000000-workbench-refresh.json",
      "receipt_sha256": "<sha256>",
      "formal_sha256": "<sha256>",
      "formal_data_sha256": "<sha256>",
      "formal_checker": "PASS"
    }
  }
}
```

回执保存在项目外的系统备份/临时证据目录；交接文件只保存文件名和哈希，不写入机器绝对路径。`refreshed` 是旧版成功状态，处理器继续跳过它以避免重复消费，但新记录一律使用更精确的 `formal_refreshed`。

- `refresh_workbench: true`：由总控刷新唯一正式工作台；未提供新 Notion 导出时会保留页面内最近一次已核验数据，并重新做新鲜度判断。
- `merge_into_current_plan: true`：总控只标记 `awaiting_merge`，绝不让专项周期直接替代当前计划。
- `event_type: nutrition_contract_updated`：`artifacts` 指向用户已确认的 `工作台与工具/饮食工作台/nutrition-contract-vNN.json`；它只请求刷新工作台数据，不代表营养候选已经入账，也不代表已经发布或部署。
- `artifacts[].path` 必须是项目根目录内已存在的相对路径；越界或缺失时拒绝消费。
- `formal_refreshed` 只证明本地正式 HTML 已刷新并通过 checker，不等于已生成发布副本，更不等于已部署或已验证线上。
- Notion 快照若声明增量或全量语义，运行 `process-handoffs` 时必须同步传入 `--notion-mode incremental|full`；命令行与快照声明冲突时拒绝刷新。
