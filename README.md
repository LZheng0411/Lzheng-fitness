# Lzheng Fitness Skills

一套可独立下载、可追溯、无私人知识库依赖的健身 Agent Skills。四个 Skill 均以 `lzheng-` 命名，并携带完成任务所需的参考资料。v1.1.0 新增周训练阶段复盘与个人体感追问机制。

## 包含内容

| Skill | 用途 | 是否可单独安装 |
| --- | --- | --- |
| `lzheng-fitness-plan` | 问诊、安全筛查、P0—L3 分层、动作选择、完整计划与 HTML | 是 |
| `lzheng-training-return` | 停训 7 天、连续漏练 3 次或条件变化后的训练接回 | 是 |
| `lzheng-strength-cycle-planner` | 单个力量主项的 8—12 周周期和渐进曲线 HTML | 是 |
| `lzheng-strength-training-review` | 单练周期/滚动/基准复盘，以及周训练阶段复盘 | 是 |

`knowledge/` 保存经过重新组织的开源训练规则和来源登记。它不包含私人训练数据，也不复制整本版权书籍。

## 安装

需要 Python 3.10 或更高版本；Skill 本身和生成脚本不需要第三方 Python 包。

安装全部 Skill：

```bash
python tools/install.py --platform codex --all
```

只安装一个：

```bash
python tools/install.py --platform codex --skill lzheng-fitness-plan
```

支持的平台目录：

- `codex`：`$CODEX_HOME/skills`，未设置时为 `~/.codex/skills`
- `claude`：`~/.claude/skills`
- `agents`：`~/.agents/skills`

也可以把 `skills/lzheng-...` 整个目录复制到任意兼容 Agent 的 Skills 目录。目录名、`SKILL.md` 中的 `name` 和调用名必须保持一致。

安装到测试或自定义目录：

```bash
python tools/install.py --target-root ./test-agent --all
```

这会写入 `./test-agent/skills/`。默认拒绝覆盖现有 Skill；只有确认需要替换时才使用 `--force`。

## 使用

示例：

```text
使用 $lzheng-fitness-plan 根据我的目标、最近训练、每周时间和器械条件制定计划。
使用 $lzheng-training-return 帮我在停训两周后重新开始。
使用 $lzheng-strength-cycle-planner 为卧推制定 8 周周期。
使用 $lzheng-strength-training-review 复盘我今天的训练并给出下一次处方。
使用 $lzheng-strength-training-review 总结我这周训练；先问个人体感，再给出周度关键决策。
```

四个 Skill 可以协作，但不会把其他 Skill 视为必装依赖：

- 健身计划只有在用户明确询问或确认专项周期后才路由周期规划。
- 停训达到阈值时可路由训练接回。
- 训练复盘已内置周期调整摘要，即使没有安装周期规划也能完成复盘。
- 缺少协作 Skill 时，应说明可选能力未安装，继续完成当前 Skill 的核心任务。

## 可移植输出目录

用户指定目录时优先使用。否则可以设置：

```text
LZHENG_FITNESS_HOME=/path/to/my-fitness-data
```

未设置时，输出进入当前工作目录的 `lzheng-fitness-output/`。Skill 不要求 Obsidian、Notion 或任何云服务；外部训练记录只在用户授权且当前环境可访问时使用。

## 验证

发布、修改或安装前运行：

```bash
python tools/validate_bundle.py
```

验证器会检查：

- 四个 Skill 的命名、Frontmatter、元数据和内部链接；
- 私人绝对路径、私人项目名和隐私标识残留；
- Python 脚本语法；
- 健身计划 JSON → HTML → 一致性审计；
- 力量周期 JSON → 独立 HTML；
- 临时目录中的完整安装与文件一致性。

## 安全与证据

本项目提供一般训练规划和记录辅助，不提供医疗诊断。出现胸部异常不适、晕厥、异常气短、锐痛、麻木、放射痛、明显功能受限或持续加重症状时，不应使用普通高强度处方。

最新官方来源和书籍角色见 [Lzheng Fitness 来源登记](knowledge/06-lzheng-source-register.md)。每份输出应只列实际读取的来源。

## License

MIT © 2026 Lzheng
