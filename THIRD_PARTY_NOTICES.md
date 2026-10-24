# 第三方组件与许可

笺隐（JianYin）包含或链接以下第三方组件。各组件的完整许可文本见
[`third_party_licenses/`](third_party_licenses/)，并会随 Windows 安装包、Windows 便携包和
macOS DMG 一起分发。

## 内置 OCR：pdf-to-markdown（pdf2md）

- 上游项目：<https://github.com/AlexRaganhar/pdf-to-markdown>
- 版权：Copyright (c) 2026 AlexRaganhar
- 许可：MIT License（全文见 `third_party_licenses/pdf2md-MIT.txt`）
- 位置：`jianyin_app/vendor/pdf2md/`
- 修改说明：只增加了 `Result.pages` 和 `on_page` 进度回调，其余保持上游实现。
  上游本身已使用 RapidOCR + PP-OCRv6 small，不再依赖 PaddlePaddle、Torch 或 Docling。

## OCR 运行时与模型

| 组件 | 版本 | 许可 | 说明 |
| --- | --- | --- | --- |
| RapidOCR | 3.9+ | Apache-2.0 | OCR 推理封装；`third_party_licenses/rapidocr-LICENSE` |
| PP-OCRv6 small det/rec + cls | 随 RapidOCR | Apache-2.0 | 模型权重版权归百度/PaddleOCR 权利人；详见 `third_party_licenses/rapidocr-MODEL_LICENSES.md` |
| ONNX Runtime | 1.20+ | MIT | CPU 推理 |
| pypdfium2 / PDFium | 5.x | BSD-3-Clause / Apache-2.0 | PDF 页面渲染；PDFium 及其他构建依赖的许可见 `third_party_licenses/pypdfium2-*` |
| OpenCV (headless) | 5.x | Apache-2.0 | RapidOCR 图像处理 |
| NumPy | 2.x | BSD-3-Clause | 数值计算 |
| Pillow | 13.x | MIT-CMU | 图像读取 |
| pypdf | 6.x | BSD-3-Clause | PDF 元数据与解密 |
| Shapely | 2.x | BSD-3-Clause | RapidOCR 后处理 |
| pyclipper | 1.x | MIT | RapidOCR 后处理 |
| OmegaConf | 2.x | BSD-3-Clause | RapidOCR 配置 |
| colorlog | 6.x | MIT | RapidOCR 日志 |
| six | 1.x | MIT | 兼容层 |

## 隐私过滤模型

OpenAI Privacy Filter 模型不在本文件中重复列出：其来源、固定 revision 和 Apache-2.0
许可见根目录 [`NOTICE`](NOTICE)，以及随包模型目录中的 `MODEL_NOTICE.txt`。

## 说明

- 本项目自身以 Apache-2.0 发布，见 [`LICENSE`](LICENSE)。
- 上述组件仍受各自许可约束；本文件不改变其许可条款。
- 如果你再分发笺隐的二进制包，请保留本文件与 `third_party_licenses/` 目录。
