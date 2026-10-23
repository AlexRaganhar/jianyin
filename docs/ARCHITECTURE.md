# 架构与取舍

笺隐只做一件事：把案件文档中的敏感信息变成可审阅、可还原的替换值。所有模块都围绕这
条链路存在，不能直接服务于它的部分不进入运行时。

## 一条主链路

```text
导入（TXT / Markdown / DOCX / PDF）
  → 文本提取（扫描 PDF 走内置 pdf2md）
  → 检测（Q4 ONNX 模型 + 可选中式规则）
  → 规则草稿（可审阅、可编辑）
  → 应用（案件级映射 + Markdown / DOCX）
  → 还原（按映射偏移校验后写回）
```

## 边界

| 层 | 职责 | 不负责 |
| --- | --- | --- |
| `documents/` | 读取文件、PDF 解密、OCR 适配、DOCX 导出 | 判断敏感信息 |
| `model/` | 加载本地 Q4 模型、窗口推理、Viterbi 解码 | 规则、文件 IO |
| `detection/` | 合并模型与中文规则、输出 `DetectionBatch` | 写文件 |
| `redaction/` | 草稿、匹配、替换、映射、还原校验 | GUI、工作区布局 |
| `workspace/` | 案件目录、原子写入、设置、导入编排 | 检测算法 |
| `gui/`、`cli.py` | 交互与进度展示 | 业务规则 |

## 明确删掉的东西

- **外部 `pdf-to-markdown` 依赖**：已内置为 `jianyin_app/vendor/pdf2md`，同一套
  RapidOCR PP-OCRv6 模型，Windows / macOS 共用。
- **OCR 子进程与 `progress.json`**：页面检查点本身就是进度来源；进程内调用
  `convert_pdf(..., on_page=...)`，取消在页边界生效，不再维护第二套状态。
- **PaddlePaddle / Torch / Docling**：上游已改用 RapidOCR + 直接 Markdown，
  运行时包因此少约 1 GB。
- **运行期模型下载**：冻结包不包含 `huggingface_hub`，不会在分析时偷偷联网。
  模型获取是显式的 `jianyin download-model` 或构建步骤。
- **`OPF_*` 环境变量**：只保留 `JIANYIN_*`，避免两套前缀。
- **未使用的辅助函数**：`with_source`、`batch_from_detections`、`load_ruleset`、
  `unique_path` 等没有调用方的代码已移除。

## 状态所有权

- 页面检查点：`<案件>/ocr/<源文件 SHA-256 前 16 位>/ocr.work/`，由 pdf2md 拥有；
  成功自动删除，取消/失败保留以便续跑。
- 案件映射：`rules/case-redaction.json`，schema `3`，包含原文偏移与替换值。
- 设置：`workspace.json`，只存非敏感选项。
- OCR 输出：`ocr/<哈希>/ocr.md` 与 `ocr.pages.txt`，供审计和重新导入使用。

## 打包

- Windows：PyInstaller `--onefile` → 便携 ZIP / Inno Setup 安装包。
- macOS：PyInstaller `.app` → 含 `Applications` 链接的 DMG（arm64 / x64）。
- 模型和 OCR 模型都随包分发；安装包不依赖 Python、网络或外部 OCR 工具。
