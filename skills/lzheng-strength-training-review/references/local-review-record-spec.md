# Lzheng 力量训练复盘本地记录规范

每次复盘只创建或修订一个本地 Markdown 记录。用户指定目录时优先使用；否则使用 `LZHENG_FITNESS_HOME/reviews/`，未设置环境变量时使用当前工作目录的 `lzheng-fitness-output/reviews/`。

## 文件名

- 周期模式：`YYYY-MM-DD-Wn-训练日-lzheng-training-review.md`
- 滚动或基准模式：`YYYY-MM-DD-rolling-训练日-lzheng-training-review.md`

日期取实际训练日期。训练日无法确认时写 `待确认训练日`。

## Frontmatter

```markdown
---
title: YYYY-MM-DD 训练日 Lzheng 力量训练复盘
date: YYYY-MM-DD
week: W2
training_day: 上肢A
review_mode: cycle
status: 已复盘
source_type: chat
source_ref: "user-message-YYYY-MM-DD"
progression_basis: "current-plan-v02"
plan: "current-plan-v02"
external_source: ""
---
```

- `review_mode` 只能为 `cycle`、`rolling` 或 `baseline`。
- 无周期记录使用 `week: 无周期`、`plan: ""`。
- `source_type` 使用 `external_record`、`chat` 或 `local`。
- 外部来源同时填写 `source_ref` 与 `external_source`；不得写入访问令牌。
- `status` 使用 `已复盘` 或 `待补全`。

## 正文结构

```markdown
# YYYY-MM-DD 训练日 Lzheng 力量训练复盘

## 复盘模式与依据

## 本次判定

| 动作 | 判断依据或当前处方 | 实际记录 | 判定与依据 |
| --- | --- | --- | --- |

## 恢复与干扰

## 渐进方式检查

## 下一次训练

| 动作 | 下一次重量与组次 | RPE 路径 | 执行要点 |
| --- | --- | --- | --- |

## 待确认周期调整 / 待确认结构调整

## 待补全记录
```

不得把聊天推测、未确认结构调整或未核验身体数据写成事实。

## 去重与索引

- 外部来源用规范化的脱敏来源标识去重。
- 聊天或本地来源用 `source_type + source_ref + 训练日期` 去重。
- 同一来源已有记录时不新建文件，在原文件末尾新增“复盘修订 - 时间”。
- 更新同目录 `INDEX.md`，然后重新读取记录和索引验证。

索引表头：

| 日期 | 周次 | 训练日 | 主项判定 | 处方状态 | 复盘 |
| --- | --- | --- | --- | --- | --- |

处方状态使用：`当前计划不修改`、`待确认周期调整`、`滚动处方已给出`、`基准训练待执行` 或 `待确认结构调整`。
