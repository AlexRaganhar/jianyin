# 笺隐 · JianYin

[![CI](https://github.com/AlexRaganhar/jianyin/actions/workflows/ci.yml/badge.svg)](https://github.com/AlexRaganhar/jianyin/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> 笺纸之间，隐去姓名，留下事实。

**笺隐**是一个本地运行、可审阅、可还原的案件文档脱敏工作台。它使用 OpenAI Privacy Filter 的 Q4 ONNX 模型识别文本中的敏感信息，结合可开关的中文规则补强，先生成一份可编辑的“源值 → 替换值”规则草稿，再按规则统一脱敏案件内的全部文档，输出 Markdown、可选 DOCX 和映射 JSON。

* 全部推理、OCR、规则和输出都在本机完成，不调用外部 API。
* 不修改原始文件。
* 同一案件中，同一个敏感值在全部文档使用同一个替换值。
* 映射可以逐处还原；如果脱敏文本被手工改动，工具会拒绝还原而不是猜测。
* 模型主要基于英文训练，中文姓名、地址等必须人工复核。

> 本项目是独立重写的工具，不是 OpenAI 官方产品；不依赖任何旧项目目录。

## 1. 核心流程

```text
导入文件
  → 提取可审阅文本（PDF 保留页标记）
  → 模型识别 + 中文规则补强
  → 生成可编辑规则草稿（draft-rules.json）
  → 人工审阅：启用/停用、修改替换值、添加手工规则
  → 应用脱敏（案件级映射 + Markdown/DOCX）
  → 导出或按映射还原
```

## 2. 安装

要求：Windows 10/11、Python 3.12、约 1 GB 磁盘用于模型。

```powershell
git clone https://github.com/AlexRaganhar/jianyin.git
cd jianyin
.\scripts\setup.cmd
```

`setup.cmd` 会创建 `.venv`、安装依赖，并准备 Q4 模型：默认从官方 Hugging Face 仓库下载；如果你已有本地模型，可指定目录直接复制：

```powershell
.\scripts\setup.cmd -ModelSource "D:\path\to\openai-privacy-filter-q4"
```

也可以手工安装：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

然后让工具下载模型（约 945 MB）：

```powershell
.\.venv\Scripts\jianyin.exe download-model
```

如果你已经有完整 Q4 目录，也可以直接复制到项目的 `models\openai-privacy-filter-q4\`，或用 `--model-dir` 指向它。

### Windows 含模型便携版

如果不想安装 Python、也不想首次联网下载模型，可以直接下载 GitHub Release 中的 Windows 便携含模型包：

[JianYin-0.1.0-windows-x64-with-model.zip](https://github.com/AlexRaganhar/jianyin/releases/download/v0.1.0/JianYin-0.1.0-windows-x64-with-model.zip)（约 1 GB）

解压后双击 `启动笺隐.cmd` 即可。包内已经包含 `JianYin.exe`、完整的 Q4 ONNX 模型和启动器；不需要 Python，也不需要联网下载模型。SHA256 校验和见 Release 的 `SHA256SUMS-with-model-0.1.0.txt`。

不含模型的 Windows/macOS 便携包仍在同一 Release 中；它们首次启动时会从 Hugging Face 下载模型。

### macOS 含模型便携版

macOS 提供两个架构的含模型包：

- Apple Silicon：[JianYin-0.1.0-macos-arm64-with-model.zip](https://github.com/AlexRaganhar/jianyin/releases/download/v0.1.0/JianYin-0.1.0-macos-arm64-with-model.zip)
- Intel：[JianYin-0.1.0-macos-x64-with-model.zip](https://github.com/AlexRaganhar/jianyin/releases/download/v0.1.0/JianYin-0.1.0-macos-x64-with-model.zip)

解压后把 `JianYin.app` 拖进「应用程序」再打开。模型已放在 `JianYin.app/Contents/MacOS/models/` 内，不需要下载。构建没有 Apple 开发者签名，首次打开请右键 →「打开」，或执行 `xattr -cr /Applications/JianYin.app`。校验和见 `SHA256SUMS-with-model-macos-arm64-0.1.0.txt` / `SHA256SUMS-with-model-macos-x64-0.1.0.txt`。

模型来自 [openai/privacy-filter](https://huggingface.co/openai/privacy-filter)，固定 revision `7ffa9a043d54d1be65afb281eddf0ffbe629385b`，Apache-2.0。

截至 2026-10-22 核对：Hugging Face 最新 sha 仍为 `7ffa9a043d54d1be65afb281eddf0ffbe629385b`，[GitHub 仓库](https://github.com/openai/privacy-filter) 最新提交 `f7f00ca7fb86`（2026-04-22），与本地固定 revision 一致，暂无更新。

## 3. 启动

双击 `启动图形界面.cmd`，或：

```powershell
.\.venv\Scripts\jianyin-gui.exe
```

窗口标题为“笺隐 · 本地文档脱敏工作台”，窗口和任务栏使用“笺隐”印章图标（`jianyin_app/assets/jianyin.ico`）。默认优先使用 `Documents\JianYin Cases`；如果当前进程无法写入该目录（例如受 Windows 受控文件夹限制），会自动退到项目同级的 `JianYin Cases`，也可在“选择工作区”中更换。

### GUI 使用步骤

1. 新建案件。
2. 导入 TXT、Markdown、Word、文本 PDF、扫描 PDF；同一密码的 PDF 可用“批量解锁 PDF”。
3. 点击“分析敏感信息”，等待模型和中文规则完成。
4. 在“规则清单”中审阅：
   * 启用/停用规则；
   * 双击修改替换值；
   * 从原文选中文本后点“添加规则”；
   * 删除或重置替换值。
5. 点击“应用脱敏”，生成案件级映射、Markdown 和 DOCX（可在设置中关闭 DOCX）。
6. 点击“导出”选择 Markdown / DOCX / 映射 JSON；映射含原始敏感值，单独保存并谨慎外发。
7. 点击“还原”，按最新映射生成还原后的审阅文本。

左侧橙色/红色高亮表示模型或中文规则识别到的内容；右侧蓝色高亮表示映射中的替换值。页选择器可查看 PDF 的逻辑页。

## 4. CLI

CLI 与原项目一样，处理单个 TXT/Markdown 文件；Word/PDF 请使用 GUI。

```powershell
# 一次完成分析 + 脱敏
.\.venv\Scripts\jianyin.exe redact `
  --input .\材料.md `
  --output-md .\材料-脱敏.md `
  --output-docx .\材料-脱敏.docx `
  --mapping .\材料-映射.json

# 先生成规则草稿，人工审阅后再应用
.\.venv\Scripts\jianyin.exe analyze --input .\材料.md --draft .\draft.json
.\.venv\Scripts\jianyin.exe apply `
  --input .\材料.md `
  --draft .\draft.json `
  --output-md .\材料-脱敏.md `
  --mapping .\材料-映射.json

# 还原
.\.venv\Scripts\jianyin.exe restore `
  --input .\材料-脱敏.md `
  --mapping .\材料-映射.json `
  --output-md .\材料-还原.md

# 下载模型
.\.venv\Scripts\jianyin.exe download-model
```

常用参数：

| 参数                      | 说明                   |            |
| ----------------------- | -------------------- | ---------- |
| `--model-dir`           | 本地 Q4 ONNX 模型目录      |            |
| `--rules`               | 策略规则 JSON（类别 → 替换策略） |            |
| `--chinese-rules`       | 中文补强规则配置 JSON        |            |
| `--no-chinese`          | 关闭中文补强               |            |
| \`--decode-mode viterbi | argmax\`             | 默认 viterbi |
| `--max-tokens`          | 推理窗口 token 数，默认 4096 |            |
| `--overlap-tokens`      | 窗口重叠，默认 256          |            |
| `--offline`             | 禁止下载模型               |            |
| `--force`               | 允许覆盖已有输出             |            |
| `--progress`            | 向 stderr 输出不含原文的聚合进度 |            |

stdout 只输出聚合 JSON 状态，不打印原文或替换值；错误写到 stderr。

## 5. 输出与映射

案件工作区布局：

```text
<workspace>/
  workspace.json
  logs/app.log
  cases/<uuid>/
    case.json
    sources/                原始文件；加密 PDF 另有 .encrypted.pdf
    extracted/              用于审阅和模型识别的文本
    outputs/redacted/       脱敏 .md / .docx
    outputs/restored/       还原 .md / .docx
    rules/draft-rules.json  规则草稿（含原文，敏感）
    rules/case-redaction.json  最终映射（含原文，敏感）
    rules/archive/          旧映射归档（最多 5 份）
    ocr/                    扫描 PDF 的本地 OCR 过程文件
```

最终映射使用 `schema_version: 3`，包含：

* 案件、模型、检测配置和策略元数据；
* 每份文档的处理摘要和输出路径；
* 每条规则的类别、原文、替换值、来源、命中位置；
* 脱敏前后字符偏移。

**映射 JSON 包含原始敏感值，必须只保存在受控本地路径，不要作为普通材料外发。**

还原时工具会逐处检查“该偏移处的脱敏值是否仍等于映射中的 target”。只要有一处被手工修改，整次还原都会拒绝，不写部分文件。

## 6. 中文补强

OpenAI Privacy Filter 的标签体系主要是英文语境。笺隐额外提供本地中文规则，默认开启：

| 规则   | 默认 | 说明                       |
| ---- | -- | ------------------------ |
| 身份证号 | 开  | 18 位 + 校验码               |
| 手机号  | 开  | 11 位大陆手机号，数字边界           |
| 银行卡号 | 开  | 16–19 位 + Luhn 校验        |
| 姓名线索 | 开  | 角色/姓名上下文 + 姓氏表 + 停用词，低置信 |
| 座机号  | 关  | 区号 + 7–8 位               |
| 中文日期 | 关  | `YYYY年M月D日`              |
| 中文地址 | 关  | 省市区 + 街道/路/号             |

姓名线索只识别窄上下文，例如“被告人张三”“姓名：李四”“我叫欧阳锋”，并排除“人民法院”“有限公司”等词。它仍可能误报，规则清单会标注“中文规则·姓名线索”，请逐条复核。

在“设置”中可以逐项关闭中文规则。

## 7. 替换策略

内置策略 `jianyin_app/data/default_rules.json`：

* 姓名：中文保留姓/复姓 + “某”，同姓冲突追加 2、3；非中文名使用 `[姓名1]`；
* 电话/邮箱/账号/证件号：保留首尾 3 位，中间用 `*`；
* 地址/日期/链接/密钥：编号占位符，如 `[地址1]`、`[密钥1]`；
* 单位/其他：`[单位1]`、`[敏感信息1]`。

策略规则文件可以自定义类别和模板，模板支持 `{n}` 编号。旧版 `schema_version: 1` 的策略规则仍可读取。

## 8. 扫描 PDF 与 OCR

扫描 PDF 会调用本机的 [pdf-to-markdown](../pdf-to-markdown)（PP-OCRv6 + Docling），不上传外部服务。

查找顺序：

1. `JIANYIN_PDF_TO_MARKDOWN_DIR`
2. `OPF_PDF_TO_MARKDOWN_DIR`
3. 项目同级目录 `pdf-to-markdown`

OCR 工具不存在时会明确报错，不会静默改用在线 OCR。OCR 部分页失败时仍导入已有页，并在文档记录中写入警告。

## 9. 隐私与边界

* 除首次下载模型外不访问网络；不调用外部 API、不上传案卷。
* 映射、草稿、OCR 中间文件和源文件都只在本地工作区。
* 日志只记录案件/文档 ID、错误码和阶段；不记录原文、替换值或密码。
* PDF 密码只在内存中使用，不写配置、日志或映射。
* 所有输出原子写入；失败不留半成品。
* 原始文件始终保留；DOCX 是文本重排导出，不复刻原 Word/PDF 版式。
* 模型和中文规则都可能误报或漏报；本工具不是匿名化或合规保证，导出前必须人工复核。

## 10. 测试

```powershell
.\scripts\verify.cmd
```

或手工：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q -m slow
.\.venv\Scripts\python.exe -m compileall -q jianyin_app
.\.venv\Scripts\python.exe -m pip check
```

`-m slow` 需要本地模型；默认测试使用假模型，不需要下载。

## 11. 常见问题

**模型缺失/下载失败**\
指定 `--model-dir`，或运行 `jianyin download-model`；离线时把完整 Q4 目录放到 `models\openai-privacy-filter-q4`。

**中文姓名没有识别**\
模型对中文姓名较弱。确认设置中“姓名线索”已开启；仍漏检时，在原文中选中姓名，点“添加规则”。

**还原被拒绝**\
脱敏文本被手工修改，偏移已无法安全匹配。请从原始文件重新应用脱敏，或使用归档映射对应旧版本。

**DOCX 版式与原件不同**\
这是设计选择：笺隐只做可审阅的文本重排，不做不可靠的 DOCX/PDF 版式重写。原始文件始终保留。

**OCR 不可用**\
安装并配置 `pdf-to-markdown`，或设置 `JIANYIN_PDF_TO_MARKDOWN_DIR`。

## 12. 目录

```text
jianyin/
  jianyin_app/     Python 包（模型、检测、规则、文档、工作区、GUI、CLI）
  tests/           单元与集成测试
  scripts/         setup / verify / 真实模型 smoke
  docs/            映射、规则、GUI 流程文档
  models/          Q4 ONNX 模型（不进入版本控制）
  启动图形界面.cmd
```

## 13. 参与贡献与安全

- 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)
- 安全与隐私边界：[SECURITY.md](SECURITY.md)
- 请不要在 Issue、PR、截图或 CI 日志中放入真实案卷、姓名、身份证号、联系方式、映射 JSON 或密码；复现问题请使用合成数据。
- 如果这个项目对你有帮助，欢迎 Star、Issue 和 Pull Request。

## 14. 许可

* 代码：Apache-2.0。
* 模型：OpenAI Privacy Filter，Apache-2.0；见 [NOTICE](NOTICE)。
* “openai/privacy-filter”模型名称与相关商标归 OpenAI 所有；笺隐不是 OpenAI 官方产品。
