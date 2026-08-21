# Lzheng 力量训练复盘本地记录规范

每次复盘只创建或修订一个本地 Markdown 记录。用户指定目录时优先使用；否则先使用已初始化系统配置中的 `output_locations.reviews`，尚未建立系统配置时才使用 `LZHENG_FITNESS_HOME/reviews/` 或当前工作目录的 `lzheng-fitness-output/reviews/`。

## 文件名

- 周期单练：`YYYY-MM-DD-Wn-训练日-lzheng-training-review.md`
- 滚动或基准单练：`YYYY-MM-DD-rolling-训练日-lzheng-training-review.md`
- 周训练阶段：`YYYY-MM-DD-Wn-周训练阶段-lzheng-training-review.md`

单练日期取实际训练日期；周训练阶段日期取本周结案或正式复盘日期，并在正文写明覆盖日期。

## Frontmatter

```markdown
---
title: YYYY-MM-DD 训练日或周训练阶段 Lzheng 力量训练复盘
date: YYYY-MM-DD
week: W2
training_day: 上肢A / 周训练阶段
review_mode: cycle / rolling / baseline / weekly
status: 已复盘 / 待补全
source_type: external_record / chat / local
source_ref: "脱敏且可追溯的来源标识"
progression_basis: "current-plan-v02"
plan: "current-plan-v02"
external_source: ""
---
```

- 无周期单练使用 `week: 无周期`、`plan: ""`。
- 周复盘即使由周期驱动，`review_mode` 也写 `weekly`；周期版本写入 `progression_basis` 和 `plan`。
- 外部来源同时填写 `source_ref` 与 `external_source`；不得写入访问令牌。
- 用户体感、关键安全字段或重复问题的追问未完成时使用 `status: 待补全`；只能保存事实副本，不写成最终决策。

## 正文与去重

- 单练使用 [复盘输出规范](review-output-spec.md) 的单练顺序。
- 周复盘使用 [周训练复盘模板](weekly-review-template.md) 的八段结构。
- 外部来源用规范化的脱敏来源标识去重；聊天或本地来源用 `source_type + source_ref + 训练日期` 去重。
- 同一周复盘以 `week + 覆盖日期 + 当前计划版本` 去重。
- 同一来源已有记录时，在原文件末尾新增“复盘修订 - 日期”，不新建重复文件；更新索引摘要。

## 索引

索引表头：

| 日期 | 周次 | 训练日 | 主项判定 | 处方状态 | 复盘 |
| --- | --- | --- | --- | --- | --- |

处方状态使用：`当前计划不修改`、`待确认周期调整`、`滚动处方已给出`、`基准训练待执行` 或 `待确认结构调整`。
