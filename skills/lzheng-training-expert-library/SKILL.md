---
name: lzheng-training-expert-library
description: 为 Lzheng 计划、力量周期、训练复盘和停训接回 Skill 提供六个可移植、来源限定的训练专家模块，包含来源边界、覆盖矩阵、问题路由、知识卡、协作选择和验证状态；用于内部选择最少必要专家并保留分歧条件，不作为名人角色扮演、医疗诊断或独立动态处方入口。
---

# Lzheng 训练专家知识库

这是 Lzheng 健身套件的内部知识层。它让主 Skill 能读取完整蒸馏模块，而不是只依赖一页通用摘要。

## 使用顺序

1. 先读 [专家选择协议](references/expert-selection-contract.md)，把问题拆成会改变结论的变量。
2. 再读 [专家登记表](references/expert-registry.json)，选择最少必要专家；通常 1 位，只有独立变量或真实冲突才增加。
3. 进入 `references/experts/<expert-id>/`，先读 `module.json` 和入口文件，再按模块内部路由读取知识卡、框架或边界。
4. 只把来源限定判断交给计划、周期、复盘或接回 Skill；当前事实、最终处方、写入和安全分流仍归主 Skill。
5. 实际采用专家时按 [输出协议](references/expert-output-protocol.md) 展示；没有采用时不增加专家区块。

## 六个模块

- Alan Aragon：营养、宏量、补给、依从性和维持。
- Brad Schoenfeld：肌肥大机制、训练变量和增长测量。
- Brukner 与 Khan：仅在已获专业允许活动后处理保守康复进阶、返场验证和二级预防。
- Dan John：Point A、训练缺口、回到基础和低疲劳重复。
- Eric Helms：依从性、训练结构、渐进、减载和峰值。
- Greg Nuckols：力量瓶颈、专项性、变量实验、周期化和技术假设。

每个模块都包含版本边界和验证状态。`content_ready_entry_acceptance_pending` 表示内容、结构和路由已可审计，但真实主入口验收仍待完成；不得改写成“已全面验证”。

## 安全与版权边界

- 不复制或输出整本书、原始 PDF/EPUB、文章快照或大段原文。
- 不模拟专家本人，不声称代表其最新观点。
- 不用旧版书替代当前医疗指南、专业评估或公共安全标准。
- 疼痛、急性创伤、胸部不适、晕厥、异常气短、进行性神经症状、术后或疾病先走安全分流。
- 专家模块无权覆盖用户当次确认、当前计划、执行基准或动态记录。

## 验证

修改模块、登记表或选择协议后运行：

```powershell
python scripts/validate_expert_library.py
```

只有结构、隐私、链接、路由样例和状态一致性全部通过，才能声明公开专家库可安装、可访问。
