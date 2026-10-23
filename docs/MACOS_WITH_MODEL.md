# 笺隐 macOS 含模型便携版

这个包包含 `JianYin.app` 和完整的 Q4 ONNX 模型，不需要安装 Python，也不需要联网下载模型。

## 使用

1. 解压 zip。
2. 把 `JianYin.app` 拖进「应用程序」。
3. 双击启动。程序会优先使用 `JianYin.app/Contents/MacOS/models/openai-privacy-filter-q4` 中的随包模型。

## 首次打开提示

本构建没有 Apple 开发者签名。若 macOS 提示无法验证开发者：

- 在 Finder 中右键 `JianYin.app` →「打开」；或
- 在终端执行：

  ```bash
  xattr -cr /Applications/JianYin.app
  open /Applications/JianYin.app
  ```

## 注意

- 映射 JSON、规则草稿和 OCR 中间文件包含原始敏感值，只应保存在受控本地位置。
- 扫描 PDF OCR 仍需要本机安装 `pdf-to-markdown`；它不是本包的一部分。
- 模型主要基于英文训练，中文姓名、地址等必须人工复核。
- 本工具不是匿名化、合规或法律保证。

模型来源与许可见 `JianYin.app/Contents/MacOS/models/openai-privacy-filter-q4/MODEL_NOTICE.txt`、包内 `LICENSE` 和 `NOTICE`。
