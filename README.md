# Lzheng Fitness Skills

可独立下载、离线运行的个人健身 Agent Skills。v3.2.0 新增独立导航与已有页面安全升级，支持本机训练完成、训练日历与纠错恢复、餐食和照片保存、手动营养候选与确认入账。AI 计划与复盘需要支持 Skill 的 AI 助手；网页不自带照片识别模型。

完整的阶段、用户输入、读取文件和产出契约见 [Markdown 文档](SYSTEM-FLOW.md)；需要逐项浏览检查时打开 [HTML 检查版](SYSTEM-FLOW.html)。

第一次接触本地 Agent 或不会写代码，可以直接阅读 [新手小白搭建个人健身系统指南](BEGINNER-GUIDE.md)。它从准备电脑、让 AI 安装，到建档、第一次训练、日常复盘、换壁纸和迁移新电脑逐步说明。

需要把纯静态网站以零现金成本发布到 CloudBase，可阅读 [CloudBase 免费静态网站上线：Agent 新手教程](docs/CloudBase-Free-Static-Hosting-Beginner.md)。它不依赖 Notion 或本项目的个人数据，默认由 Agent 完成检查、上传、线上核验和回退。

公开包不含任何个人训练数据、账号信息或绝对路径。工作台使用仓库内置的项目视觉素材，离线安装时会把动态背景和静态兜底一起复制到新项目。

## 包含内容

| Skill | 用途 | 可单独安装 |
| --- | --- | --- |
| `lzheng-fitness-plan` | 训练建档、安全筛查、完整计划与 HTML | 是 |
| `lzheng-training-return` | 停训、漏练或条件变化后的接回 | 是 |
| `lzheng-strength-cycle-planner` | 单个力量动作的 8—12 周周期 | 是 |
| `lzheng-strength-training-review` | 单次、滚动、基准与周训练复盘 | 是 |
| `lzheng-training-expert-library` | 六个来源限定专家模块、选择协议和验证状态 | 是；安装四个专业 Skill 时自动带上 |
| `lzheng-nutrition-system` | 营养建档、日型宏量目标、餐食确认链与两周复盘契约 | 是 |
| `lzheng-training-system` | 新电脑初始化、迁移、诊断、升级保护和整套校验 | 与工作台构建器配套 |
| `lzheng-fitness-workbench-builder` | 从计划、复盘和可选动态数据生成响应式离线工作台 | 与系统总控配套 |

计划、周期、复盘、接回与营养是专业能力；专家库是它们共同读取的内部知识层；系统总控与工作台构建器负责把结果收束为单一主源和可离线打开的页面。动态数据连接是可选输入，不要求任何云服务。

专家库包含 Alan Aragon、Brad Schoenfeld、Brukner 与 Khan、Dan John、Eric Helms 和 Greg Nuckols 六个完整蒸馏模块。每个模块带来源/版本边界、覆盖矩阵、判断框架、问题路由、知识卡、职责边界和真实验证状态；不含原书、文章快照或私人训练数据。安装任一计划、周期、复盘或接回 Skill 时，安装器会自动带上专家库。

所有单文件 HTML 都使用仓库内固定模板：完整计划、力量周期和健身工作台各有唯一页面结构与职责。AI 只能填写经过校验的计划或工作台数据，不能临时改导航、换视觉主题或手写另一套页面。

日常计划修改和训练复盘会先调用紧凑只读检查，只加载当前计划、执行基准和本次复盘等必要主源，不把整份大型工作台 HTML、历史目录或无关发布协议塞进 Agent 上下文。完整校验仍由脚本执行，因此节省上下文不会降低数据与页面结构检查。

## 安装

已有工作台侧栏缺失或更新后仍是旧界面时，直接让 AI：“检查并修复我的工作台侧栏，保留记录和壁纸。”新版提供独立界面升级通道；更新 Skill 与刷新数据不会自动替换旧 HTML。支持的官方旧版经过识别、备份、同路径替换与浏览器验证后才报告界面升级成功。未知自定义会明确停止并给出差异。[升级方法与恢复边界](skills/lzheng-fitness-workbench-builder/references/ui-upgrade.md)。

界面升级的实际写入阶段另需 Node.js、Playwright 与 Chromium，用于真实页面验收；日常使用和只读检查不增加这项依赖。

需要 Python 3.10 或更新版本；不需要第三方 Python 包。

```bash
python tools/install.py --platform codex --all
```

也可安装到隔离目录，便于验证：

```bash
python tools/install.py --target-root ./test-agent --all
```

每次安装都会在复制前后核对完整文件清单和 SHA-256，并把结果记录到 Agent 根目录下的 `.lzheng-fitness/install-state.json`。可以随时只读检查当前安装是否与这份仓库一致：

```bash
python tools/install.py --platform codex --all --verify
python tools/install.py --target-root ./test-agent --all --verify
```

检查会明确列出缺失、被修改和额外出现的文件，不会安装或覆盖任何内容。安装器默认拒绝覆盖已有 Skill；确认替换前先运行 `--verify`，再添加 `--force`。旧目录会完整备份到 Agent 根目录下的 `.lzheng-fitness/backups/<时间>/`，不会留在活动 `skills/` 目录中。需要指定位置时使用 `--backup-root <目录>`；相对路径从 `--target-root` 解析，并且不能放在活动 `skills/` 目录内。

私人 Notion 获取器、账号配置或其他本机适配器不要放进公开 Skill 目录。建议放在 Agent 根目录下的 `.lzheng-fitness/private-adapters/`；安装器不会修改这里。若旧 Skill 内已有额外文件，`--force` 会把它们完整保留在外部备份中，但不会未经审查自动混入新版公开核心。

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

`bootstrap` 会生成匿名示例工作台、示例计划、复盘索引和全部本地界面资源。它不会生成真实重量；完成建档与动作重量校准后，AI 会接入正式计划并把下一次明确处方写回工作台。

可直接打开新目录中的 `个人训练系统/健身工作台.html`。页面支持桌面、平板和手机，不依赖在线资源。

工作台中的“完整训练计划”由按钮直接打开，不要求用户填写路径，也不要求目录是 Obsidian 仓库。复盘、复盘索引和状态档案可以直接在工作台中阅读；安装 Obsidian 后才会额外显示可选编辑入口。整套目录复制、移动或改名后，系统会以当前位置解析文件并自动迁移旧配置。

初始化后，正式产物优先收进同一个健身知识库：完整计划位于 `个人训练系统/训练与周期/当前周期`，专项力量周期位于 `个人训练系统/训练与周期/力量周期`，复盘位于 `个人训练系统/训练复盘与状态/训练复盘`，状态快照和接回卡位于 `个人训练系统/训练复盘与状态/状态档案`，营养契约位于 `个人训练系统/工作台与工具/饮食工作台`。临时渲染和备份不进入这些目录。

## 替换工作台壁纸

已经生成工作台后，可以直接交给 AI 一张图片，或一张图片加一个 MP4。脚本会备份原壁纸、更新页面、自动检查，失败时恢复原版本。

纯静态背景：

```bash
python <skills目录>/lzheng-fitness-workbench-builder/scripts/Replace-FitnessWorkbenchBackground.py --project "<个人训练系统目录>" --image "<新壁纸.png>"
```

动态背景：

```bash
python <skills目录>/lzheng-fitness-workbench-builder/scripts/Replace-FitnessWorkbenchBackground.py --project "<个人训练系统目录>" --image "<静态兜底.png>" --video "<动态背景.mp4>"
```

只传图片时会关闭旧视频。完整参数、桌面/手机取景和首次初始化用法见 [壁纸替换指南](skills/lzheng-fitness-workbench-builder/references/background-replacement.md)。

## 使用示例

```text
使用 $lzheng-fitness-plan 根据我的目标、近期训练、每周时间和器械条件制定计划。
使用 $lzheng-strength-cycle-planner 为卧推制定 8 周周期。
使用 $lzheng-strength-training-review 复盘我今天的训练并给出下一次处方。
使用 $lzheng-training-expert-library 检查这个问题应读取哪一个来源限定专家模块。
使用 $lzheng-nutrition-system 根据我的目标、训练日型和饮食环境建立营养起点。
使用 $lzheng-training-system 帮我在新电脑建立、检查并迁移整个训练系统。
使用 $lzheng-fitness-workbench-builder 根据我的当前计划和复盘搭建离线健身工作台。
```

## 发布前验证

```bash
python tools/validate_bundle.py
```

验证会检查八个 Skill 的元数据、链接、隐私残留和脚本语法，另外核验六个专家模块与营养契约的来源边界、路由、安全分流和匿名默认值；随后渲染 HTML，校验工作台的训练档案、图片、视频、内置文档和计划入口，并在临时目录中完成初始化、改名移动、旧配置迁移、无 Obsidian 发布和故障拦截。

GitHub 自动检查同时运行 Linux 和 Windows 两组任务。两组都检查八个 Skill、隐私、匿名模板、数据库契约、渲染与安装迁移；Windows 组额外实际运行本地 Agent 的安全和并发测试。Linux 明确跳过这些 Windows 专用进程测试，不要求安装 Windows PowerShell；Windows 缺少 PowerShell 或任何一项测试失败仍会阻止检查通过。

## 本地记录与可选同步

工作台默认本地运行，不要求登录：完成训练后，逐组实际值和原计划快照进入当前浏览器的 IndexedDB；训练日历可查看肌群工作组统计、纠错和恢复上个版本，不改写原计划。训练未完成时只保留草稿，不计入已完成训练。

餐食可只写名称和说明，也可保存用户明确选择的照片。未填写营养数值时标记为“未识别”；可以根据标签、自己的估算或外部 AI 结果填写带来源说明的候选，单独确认后才计入合计。饭后情况与实际摄入候选独立保存，餐前估算保留；可撤销入账。不联网、不自动识别、不伪造模型结果。

浏览器数据不会自动写回 HTML 或跨设备同步。清理站点数据、无痕窗口关闭、浏览器更换或文件位置变化可能导致记录不可访问。请在“指南”导出**本地记录备份**，它包含本机正式训练、餐食和照片；只能导入空的本地记录库，避免覆盖已有数据。此备份不包含云端记录及旧版体重、有氧、体感资料。详细边界见 [离线记录与备份](docs/Offline-Records.md)。备份含私人数据，不能上传开源仓库。

需要自行部署同步时，阅读 [可选 CloudBase 适配器](integrations/cloudbase/README.md) 和 [一次运行手册](docs/CloudBase-Agent-Runbook.md)，先复制其匿名配置示例到仓库外。默认仍为 `local`，CloudBase 与本地 Agent 都是 disabled。网页只在用户点击刷新后读取一次已知任务状态，不做后台轮询。Windows 可选协议也只能触发一次 `-Once` 运行；诊断监听仍有 10 分钟和连续 3 次空队列/失败的硬上限。

已启用云端但连接失败时，正式云端写入仍会报错，不会悄悄改成另一套本地正式记录。v3.1.1 新增的本机正式训练、餐食和照片不会因登录而自动上传；迁移这些记录和配置私有模型适配需另行明确验收。此前的体重、有氧、体感等可选同步行为不因此改变。

开发者可额外运行 `npm ci`、`npx playwright install chromium` 和 `npm test`，验证真实浏览器中的本地保存、照片持久化、确认与撤销、事务失败、备份恢复和手机布局。Node.js 与 Playwright 仅用于开发验证，不是用户运行工作台的依赖。

## 边界

本项目提供一般训练规划与记录支持，不是医疗诊断或康复建议。出现胸部不适、晕厥、异常气短、锐痛、麻木、放射痛、明显功能受限或症状持续加重时，应停止常规高强度训练并寻求专业评估。

训练知识来源见 [来源登记](knowledge/06-lzheng-source-register.md)。素材使用说明见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。

## License

MIT © 2026 Lzheng
