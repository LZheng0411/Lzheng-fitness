# 工作台壁纸替换

本功能用于替换已经生成的健身工作台背景，也可以在首次初始化时直接指定自定义背景。不要手工改 HTML、复制路径或覆盖不明文件；统一调用脚本，让它完成备份、引用更新和检查。

## 一、两种模式

### 纯静态背景

只提供图片。脚本会停用旧视频，页面始终使用新图片：

```powershell
python "<skill>/scripts/Replace-FitnessWorkbenchBackground.py" `
  --project "<个人训练系统目录>" `
  --image "<新壁纸.png>"
```

支持有效的 PNG、JPEG 和 WebP。脚本根据文件内容识别格式，不依赖用户手工改扩展名。

### 动态背景

同时提供图片和 MP4。图片是视频加载失败、减少动态效果和不支持自动播放时的静态兜底：

```powershell
python "<skill>/scripts/Replace-FitnessWorkbenchBackground.py" `
  --project "<个人训练系统目录>" `
  --image "<静态兜底.png>" `
  --video "<动态背景.mp4>"
```

不允许只有视频没有图片。

## 二、调整桌面和手机取景

图片主体不在合适位置时，可以直接调整取景，不需要编辑 CSS：

```powershell
python "<skill>/scripts/Replace-FitnessWorkbenchBackground.py" `
  --project "<个人训练系统目录>" `
  --image "<新壁纸.png>" `
  --desktop-position "55% center" `
  --mobile-position "72% center" `
  --nav-position "70% center"
```

取景只接受 `left`、`right`、`top`、`bottom`、`center`、百分比或像素值，脚本拒绝其他 CSS 内容。

## 三、首次初始化时使用自定义背景

初始化器已经接入相同功能：

```powershell
python "<skill>/scripts/Initialize-FitnessWorkbench.py" `
  --target "<新的空目录>" `
  --background-image "<静态兜底.png>" `
  --background-video "<可选动态背景.mp4>"
```

只传 `--background-image` 时创建纯静态工作台。可以再传 `--background-desktop-position` 和 `--background-mobile-position`。

## 四、脚本会自动完成什么

1. 检查工作台、图片和视频是否真实存在；
2. 验证图片和 MP4 的实际文件格式；
3. 把当前 HTML 和旧背景备份到 `历史与治理/背景备份/<时间>/`；
4. 复制并统一管理新素材；
5. 更新静态/动态模式、图片、视频和取景位置；
6. 运行 `Check-FitnessWorkbench.py`；
7. 检查失败时恢复原 HTML 和被替换的素材；
8. 成功时输出新素材路径和备份位置。

脚本不修改计划、复盘、状态档案、Notion 数据或 `workbench-data`。

## 五、完成标准

只有同时满足以下条件才能报告替换成功：

- 输出 `FITNESS_WORKBENCH_BACKGROUND: PASS`；
- 输出 `FITNESS_WORKBENCH_CHECK: PASS`；
- 纯静态模式不再引用旧视频；
- 动态模式包含新 MP4 和静态兜底；
- 备份目录包含替换前的 HTML 和背景素材；
- 整个工作台移动或制作发布副本后，新背景仍然存在；
- AI 已分别预览桌面和手机页面，文字对比度、人物取景和导航可读；自动检查通过不能代替视觉确认；
- 用户提供的素材具有合法使用和分发权限。

## 六、禁止做法

- 不要只覆盖图片但保留旧视频引用；
- 不要把用户电脑绝对路径写入 HTML；
- 不要使用网络图片地址代替本地素材；
- 不要跳过替换后的工作台检查；
- 不要把个人照片或无分发授权的素材提交到公开仓库。
