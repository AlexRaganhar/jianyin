# pdf2md（笺隐内置）

本目录是 pdf-to-markdown 的内置副本，随笺隐一起分发，让扫描 PDF 在 Windows 和 macOS 上开箱即用。

上游已经按“一条流水线”重写：RapidOCR + PP-OCRv6 small ONNX、pypdfium2 渲染、
页面级 JSON 断点、直接生成 Markdown 和逐页文本；没有 PaddlePaddle、Torch、
Docling 或 HTML 中间层。

## 笺隐所做的唯一改动

- `Result` 增加 `pages` 字段，暴露每页 OCR 文本块；
- `convert_pdf` 增加 `on_page(page_no, target)` 回调，在每页检查点落盘后调用，
  供 GUI 显示进度并在页边界取消。

其余代码与上游一致。上游 README 保留为 `README-upstream.md`；许可为 MIT，见
同目录 `LICENSE`。
