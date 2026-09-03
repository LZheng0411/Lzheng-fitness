# CloudBase 与本地 Agent：一次运行手册

这份手册只说明公开边界。真实 CloudBase 环境、账号、队列导出方式、模型命令和归档目录必须保存在仓库外的私有适配器中。

以下任务队列流程仅适用于已明确配置云端和私有适配器的页面。本机模式下，训练和餐食无需登录即可保存，营养数值由用户填写并确认；本地归档按钮下载私人备份，不会创建模型任务。参见 [离线记录与备份](Offline-Records.md)。

## 用户看到的流程

1. 在工作台手动创建餐食识别、饭后校正、周复盘或本地归档任务。
2. 明确点击一次“运行 Agent”；未安装本机协议时，页面只提示手动运行命令。
3. 本机 Agent 领取一个任务并退出。模型输出只形成候选。
4. 回到页面点一次“刷新数据”，读取一次已知任务状态。
5. 用户检查候选；只有确认后的 `confirmed_nutrition` 才计入当天合计。

## 私有配置

在仓库外创建 JSON。下面只有字段示意，不是可直接连接云端的配置：

```json
{
  "queue_file": "<private exported queue json>",
  "adapter_command": "<private model adapter command>"
}
```

公共 runner 不访问 CloudBase，也不自带模型客户端。私有适配器负责安全导出/回写、幂等领取、凭证保护和输出 Schema 校验。

## Windows 显式协议

确认私有配置后，可手动运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrations\cloudbase\local-agent\Install-NutritionLocalAgent.ps1 -ConfigPath "<private-config.json>"
```

安装器只在当前 Windows 用户下注册 `lzheng-fitness-agent://run`。它不创建计划任务、不登录启动、不立即运行 Agent。网页不能通过 URI 传入本地路径；协议处理器只读取安装时确认的私有配置，并启动一次隐藏的 `-Once`。

## 失败与检查

- 空队列：0 次模型调用并退出。
- 同一队列并发：互斥锁只允许一个进程领取。
- 缺少配置或 runner：协议拒绝运行。
- 网页刷新：每次只读一次已知任务，无后台轮询。
- 候选失败：保留失败状态，不自动重试，不计入正式记录。

运行公开安全检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrations\cloudbase\local-agent\Test-LocalAgentSafety.ps1
```

真实账号、照片、跨设备同步、数据库迁移和本地归档仍需在用户自己的私有环境中逐项验收。
