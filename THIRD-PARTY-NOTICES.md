# 第三方许可与来源

Lzheng 自有代码与 Skill 使用根目录 MIT 许可。以下独立材料不适用根 MIT，安装或再分发时保留各自许可。

| 路径 | 原作者／项目 | 许可与范围 |
| --- | --- | --- |
| `third_party/dbs-learning/` | dontbesilent / [dbskill](https://github.com/dontbesilent2025/dbskill) | CC BY-NC 4.0；非商业分享和改编，署名、链接许可、注明修改；商业使用需另行授权 |
| `third_party/cangjie/LICENSE` | [kangarooking/cangjie-skill](https://github.com/kangarooking/cangjie-skill) | MIT；此处只保留许可与固定版本出处，工具由用户按需安装官方版本 |

`dbs-learning/SKILL.md` 原样收录，没有改名或内容修改。确切上游提交在各自 `UPSTREAM.json`。`dbs-learning` 不属于主体 MIT Skill 列表，不由 `--all` 隐式安装。使用 `python tools/install_learning.py --platform codex --dbs-learning` 明确安装此非商业学习组件。主体视频来源工具不依赖它也可工作。

仓颉按官方说明从上述上游地址安装到当前 Agent；安装和调用时读取其原版 Skill。两者的许可不授予原书籍、视频、图像等输入材料的再分发权。
