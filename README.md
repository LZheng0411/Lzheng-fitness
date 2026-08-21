# Lzheng Fitness Skills

可独立下载、离线运行的个人训练 Agent Skills。v2 将计划、专项周期、训练复盘、停训接回、系统总控与健身工作台组合为一个可迁移的本地训练闭环。

完整的阶段、用户输入、读取文件和产出契约见 [Markdown 文档](SYSTEM-FLOW.md)；需要逐项浏览检查时打开 [HTML 检查版](SYSTEM-FLOW.html)。

公开包不含任何个人训练数据、账号信息或绝对路径。工作台使用内置的饿狼视觉素材；该素材已获本仓库维护者授权，离线安装时会被复制到新项目。

## 包含内容

| Skill | 用途 | 可单独安装 |
| --- | --- | --- |
| `lzheng-fitness-plan` | 训练建档、安全筛查、完整计划与 HTML | 是 |
| `lzheng-training-return` | 停训、漏练或条件变化后的接回 | 是 |
| `lzheng-strength-cycle-planner` | 单个力量动作的 8—12 周周期 | 是 |
| `lzheng-strength-training-review` | 单次、滚动、基准与周训练复盘 | 是 |
| `lzheng-training-expert-library` | 六个来源限定专家模块、选择协议和验证状态 | 是；安装四个专业 Skill 时自动带上 |
| `lzheng-training-system` | 新电脑初始化、迁移、诊断、升级保护和整套校验 | 与工作台构建器配套 |
| `lzheng-fitness-workbench-builder` | 从计划、复盘和可选动态数据生成响应式离线工作台 | 与系统总控配套 |

前四个是专业能力；专家库是它们共同读取的内部知识层；后两个负责把结果收束为单一主源和可离线打开的工作台。动态数据连接是可选输入，不要求任何云服务。

专家库包含 Alan Aragon、Brad Schoenfeld、Brukner 与 Khan、Dan John、Eric Helms 和 Greg Nuckols 六个完整蒸馏模块。每个模块带来源/版本边界、覆盖矩阵、判断框架、问题路由、知识卡、职责边界和真实验证状态；不含原书、文章快照或私人训练数据。安装任一计划、周期、复盘或接回 Skill 时，安装器会自动带上专家库。

所有单文件 HTML 都使用仓库内固定模板：完整计划、力量周期和健身工作台各有唯一页面结构与职责。AI 只能填写经过校验的计划或工作台数据，不能临时改导航、换视觉主题或手写另一套页面。

## 安装

需要 Python 3.10 或更新版本；不需要第三方 Python 包。

```bash
python tools/install.py --platform codex --all
```

也可安装到隔离目录，便于验证：

```bash
python tools/install.py --target-root ./test-agent --all
```

安装器默认拒绝覆盖已有 Skill。确认替换时才添加 `--force`；原目录会先备份。

## 安装后直接开始

不要先阅读 README 或寻找命令。新开一个 AI 对话后，只需说：

```text
开始建立我的健身系统。
```

AI 会先问你想增肌、减脂、提升力量还是综合改善；再完成建档、动作重量校准、正式计划、工作台和后续复盘。没有训练记录时，AI 会逐步指导你为每个动作选出安全的工作重量，不会要求你自行猜测。

## 新电脑快速验证

完成安装后，在一个新的空文件夹运行：

```bash
python <skills目录>/lzheng-training-system/scripts/lzheng_training_system.py bootstrap --target "<空目录>"
python <skills目录>/lzheng-training-system/scripts/lzheng_training_system.py doctor --root "<空目录>"
```

`bootstrap` 会生成匿名示例工作台、示例计划、复盘索引和全部本地图片。它不会生成真实重量；完成建档与动作重量校准后，AI 会接入正式计划并把下一次明确处方写回工作台。

可直接打开新目录中的 `个人训练系统/健身工作台.html`。页面支持桌面、平板和手机，不依赖在线资源。

工作台中的“完整训练计划”使用相对 HTML 链接，不要求目录本身是 Obsidian 仓库；整套目录复制、移动或改名后仍可从浏览器打开。复盘和状态档案是 Markdown，放入 Obsidian 仓库时可继续使用 Obsidian 深链。

初始化后，正式产物优先收进同一个健身知识库：完整计划位于 `个人训练系统/训练与周期/当前周期`，专项力量周期位于 `个人训练系统/训练与周期/力量周期`，复盘位于 `个人训练系统/训练复盘与状态/训练复盘`，状态快照和接回卡位于 `个人训练系统/训练复盘与状态/状态档案`。临时渲染和备份不进入这些目录。

## 使用示例

```text
使用 $lzheng-fitness-plan 根据我的目标、近期训练、每周时间和器械条件制定计划。
使用 $lzheng-strength-cycle-planner 为卧推制定 8 周周期。
使用 $lzheng-strength-training-review 复盘我今天的训练并给出下一次处方。
使用 $lzheng-training-expert-library 检查这个问题应读取哪一个来源限定专家模块。
使用 $lzheng-training-system 帮我在新电脑建立、检查并迁移整个训练系统。
使用 $lzheng-fitness-workbench-builder 根据我的当前计划和复盘搭建离线健身工作台。
```

## 发布前验证

```bash
python tools/validate_bundle.py
```

验证会检查七个 Skill 的元数据、链接、隐私残留和脚本语法，另外核验六个专家模块的来源边界、知识文件、路由样例与安全分流；随后渲染既有 HTML 输出、校验工作台资源，并在临时空目录中完成整套安装、初始化、目录移动和诊断。工作台包含路径迁移与周切换回归闸门：固定盘符、移动后失效的完整计划链接、旧周日期、混合 Wn、漏掉今日处方、训练频率不符或“自重”被历史重量覆盖都会阻止验证。

## 边界

本项目提供一般训练规划与记录支持，不是医疗诊断或康复建议。出现胸部不适、晕厥、异常气短、锐痛、麻木、放射痛、明显功能受限或症状持续加重时，应停止常规高强度训练并寻求专业评估。

训练知识来源见 [来源登记](knowledge/06-lzheng-source-register.md)。素材使用说明见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。

## License

MIT © 2026 Lzheng
