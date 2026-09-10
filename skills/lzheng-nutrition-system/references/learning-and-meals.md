# 来源学习、三餐规划与报餐

先读取用户当前的有效营养方案、真实记录和已确认食品标签。用户未要求改方法时，换菜单不能偷偷改算法或把作者方法替换为近似的固定宏量数值。未明确选择作者方法，不默认应用任何示例作者的系数。

学习来源由 `lzheng-video-learning` 负责，个人饮食由本 Skill 负责。来源说明、个人接受的目标、菜单估算和实际摄入分别保存；工作台只展示结果。学习示例不激活目标。

## 三餐规划数据

工作台 `workbench-data.nutrition_planner` 支持 `schema:1`、`food_library:[]`、`current_plan`。current_plan 使用 `version/title/target_version/target/meals`；target 包含 `version/method/macros`；meals 每项为 `name/foods`，food 为 `name/portion/macros`。宏量字段为 `calories/protein_g/carbs_g/fat_g`，未知值用 null。目标版本必须匹配，否则工作台不做达标判断。保留历史方案文件，计划刷新保留当前 planner 数据。

使用 `scripts/update_planner.py --html <正式工作台> --data <规划JSON> --backup-dir <项目外目录> --apply` 更新已确认的方案。参数JSON是整个nutrition_planner对象；默认只检查。页面日期与长期口味资料分开，用户可导出调整说明交给 Agent；不会把菜单记成摄入。

## 报餐规则

- 无照片也可报餐。优先用用户描述、实际品牌口味和标签；图片只是补充证据。
- 掌、拳、碗等参照保留原话，不能当成统一精确克数；不凭空添加用户明确没有的油或酱。
- 同一食品标签可复用，标签冲突保留两者来源并待校准。原图只保存用户自己的资料目录，不进入公共包。
- 餐前估算与饭后候选分开；需用户确认才入账，确认后可撤销。处理完成不等于吃过。
- 复盘只在缺少时用一句话询问体感，不重复收集已知反馈，不额外强制填写体感表单。

可选本机模型适配器位于公共仓库 `integrations/cloudbase/local-agent/CodexNutritionAdapter.ps1`；只处理用户提交的任务，使用本人的 Codex 登录。不要自动升级模型或启用常驻轮询。离线用户可以导出餐食请求交给当前 Agent 分析，再导入候选，确认后入账；不能把人工候选冒充 AI 识别。
