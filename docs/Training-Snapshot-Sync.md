# 更新 Skill、HTML 和训练记录

这三项分别维护：安装新的 Skill 不会自动替换已经生成的 HTML；刷新 HTML 的数据块也不会改变界面功能；公开源码不包含任何使用者的真实记录。

## 训练记录已经支持哪些能力

工作台支持逐组重量、次数与 RPE、本机正式记录、训练日历、有效组统计、纠错历史和备份。旧网页可能尚未升级到含本机记录的模板。先按 [升级说明](UPGRADE.md) 检查，已知官方界面走受保护升级；定制页面必须保留现有功能并审阅差异，不静默换成另一套界面。

## 将已授权的云端记录投影到 HTML

Agent 先读取使用者当前账号的完整分页历史，并冻结本次 revision/hash；不要把凭据、账号或真实快照放进仓库。支持两种只读输入：

- 原有 PostgreSQL 导出的 `source=CloudBase PostgreSQL`，含实际 `queried_at` 和同次 `sessions/exercises/sets`。
- 正常同步接口导出的 `source=fitness_cloud.training_snapshot`，含实际 `queried_at` 和原接口的 `snapshot`，后者保留 `revision/hash/history/activeSession/pagination`。全部历史页合并后 `offset=0/hasMore=false/total=history.length`；不能把局部页当完整历史。

```powershell
python skills/lzheng-fitness-workbench-builder/scripts/Refresh-FitnessWorkbench.py --project "<个人训练项目>" --training-snapshot "<项目外私有快照.json>" --backup-dir "<项目外备份目录>"
```

刷新链冻结输入并记录哈希，再依次执行构建检查、原子写入和正式检查。只使用已保存、标为完成且有实际次数的组；未提交草稿、计划组和零次尝试不算成功组。未结束场次保留原状态。实际动作名、处方角色、原接口周次与当前计划的日历周分开保留。

投影记录在现有训练历史中只读展示，不会导入浏览器数据库或写回原云端，也不会因为快照存在而自动登录。纠错应在原系统完成后重新同步。没有新查询时标记缓存，快照日期不会因重新构建而变新。旧 Notion 数据只补历史和其他职责，不冒充当前云训练。

`formal_refreshed`、`release_prepared`、`deployed`、`online_verified` 分开报告。匿名公开包继续排除私人记录；私人 HTML 的更新不能被称为公开仓库或网站已经上线。

## 知识与规则更新

[知识入口](../knowledge/README.md)把共同训练协议、专家模块与专业 Skill 连接起来。维护者新增的未审定文章保留其核验状态；不要为追求“最新”而发布私人资料、原书或尚未审定的正文。
