# Lzheng Fitness Skills

可独立下载、离线运行的个人训练 Agent Skills。v2 将计划、专项周期、训练复盘、停训接回、系统总控与健身工作台组合为一个可迁移的本地训练闭环。

公开包不含任何个人训练数据、账号信息或绝对路径。工作台使用内置的饿狼视觉素材；该素材已获本仓库维护者授权，离线安装时会被复制到新项目。

## 包含内容

| Skill | 用途 | 可单独安装 |
| --- | --- | --- |
| `lzheng-fitness-plan` | 训练建档、安全筛查、完整计划与 HTML | 是 |
| `lzheng-training-return` | 停训、漏练或条件变化后的接回 | 是 |
| `lzheng-strength-cycle-planner` | 单个力量动作的 8—12 周周期 | 是 |
| `lzheng-strength-training-review` | 单次、滚动、基准与周训练复盘 | 是 |
| `lzheng-training-system` | 新电脑初始化、迁移、诊断、升级保护和整套校验 | 与工作台构建器配套 |
| `lzheng-fitness-workbench-builder` | 从计划、复盘和可选动态数据生成响应式离线工作台 | 与系统总控配套 |

前四个是专业能力；后两个负责把这些结果收束为单一主源和可离线打开的工作台。动态数据连接是可选输入，不要求任何云服务。

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

## 新电脑快速验证

完成安装后，在一个新的空文件夹运行：

```bash
python <skills目录>/lzheng-training-system/scripts/lzheng_training_system.py bootstrap --target "<空目录>"
python <skills目录>/lzheng-training-system/scripts/lzheng_training_system.py doctor --root "<空目录>"
```

`bootstrap` 会生成匿名示例工作台、示例计划、复盘索引和全部本地图片。它不会生成真实重量；把示例计划替换为你确认过的计划、完成首练复盘后，再作为正式训练系统使用。

可直接打开新目录中的 `个人训练系统/健身工作台.html`。页面支持桌面、平板和手机，不依赖在线资源。

## 使用示例

```text
使用 $lzheng-fitness-plan 根据我的目标、近期训练、每周时间和器械条件制定计划。
使用 $lzheng-strength-cycle-planner 为卧推制定 8 周周期。
使用 $lzheng-strength-training-review 复盘我今天的训练并给出下一次处方。
使用 $lzheng-training-system 帮我在新电脑建立、检查并迁移整个训练系统。
使用 $lzheng-fitness-workbench-builder 根据我的当前计划和复盘搭建离线健身工作台。
```

## 发布前验证

```bash
python tools/validate_bundle.py
```

验证会检查六个 Skill 的元数据、链接、隐私残留和脚本语法，渲染既有 HTML 输出，校验工作台资源，并在临时空目录中完成整套安装、初始化与诊断。

## 边界

本项目提供一般训练规划与记录支持，不是医疗诊断或康复建议。出现胸部不适、晕厥、异常气短、锐痛、麻木、放射痛、明显功能受限或症状持续加重时，应停止常规高强度训练并寻求专业评估。

训练知识来源见 [来源登记](knowledge/06-lzheng-source-register.md)。素材使用说明见 [ASSET-NOTICE.md](ASSET-NOTICE.md)。

## License

MIT © 2026 Lzheng
