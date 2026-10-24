# 参与贡献

感谢你愿意改进笺隐。这个项目优先保证**本地运行、可审阅、可还原**，任何改动都不应削弱这三点。

## 开发环境

```powershell
git clone https://github.com/AlexRaganhar/jianyin.git
cd jianyin
.\scripts\setup.cmd -SkipModel
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check jianyin_app tests
```

默认测试使用假检测器，不需要下载 945 MB 模型；真实模型测试标记为 `slow`，没有本地模型时会自动跳过：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m slow
```

## 代码约定

- Python 3.10+，类型标注优先，面向 Windows 桌面。
- 新增检测逻辑必须同时补测试，尤其是边界、重叠、偏移和还原测试。
- 不要改变映射 schema 的偏移语义，除非同时提供迁移和文档。
- GUI 改动要保证：不阻塞主线程、可取消、错误提示不包含原文。
- 规则/映射/日志不得在状态文本、异常消息或 CI 输出中打印原始敏感值。

## 不要提交

- `models/`、`.venv/`、案件工作区、输出文件、映射 JSON、规则草稿、OCR 中间文件；
- 真实案卷或任何真实个人信息；
- 密钥、令牌、密码。

`.gitignore` 已覆盖常见本地文件；提交前请再检查 `git status`。

## Pull Request

请说明：

1. 改动解决的问题；
2. 对隐私、还原和兼容性的影响；
3. 已运行的测试命令；
4. 如果是 GUI 改动，附上合成数据截图（不要使用真实案卷）。

## 许可证

提交贡献即表示同意以本项目的 Apache-2.0 许可证发布。
