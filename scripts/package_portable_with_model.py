#!/usr/bin/env python3
"""Build a Windows portable JianYin package with the Q4 model included.

The package contains the PyInstaller ``JianYin.exe``, the five required Q4
ONNX files, a launcher that points ``JIANYIN_MODEL_DIR`` at the bundled model,
license/notice files, model checksums and a short Chinese usage note.

This script is used by ``.github/workflows/release.yml`` and can be run
locally after building ``JianYin.exe`` with ``scripts/build_release.py``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_common import copy_docs, sha256, stage_model  # noqa: E402

from jianyin_app.config import MODEL_DIR_NAME  # noqa: E402
from jianyin_app.model.download import validate_model_directory  # noqa: E402

LAUNCHER = """@echo off
setlocal
set "JIANYIN_MODEL_DIR=%~dp0models\\{model_dir}"
start "" "%~dp0JianYin.exe"
endlocal
""".format(model_dir=MODEL_DIR_NAME)

USAGE = """# 笺隐 · Windows 含模型便携版

本包已经包含 PyInstaller 打包的 `JianYin.exe`、完整的 Q4 ONNX 模型，以及内置的
pdf-to-markdown OCR 引擎（PP-OCRv6 small）。不需要安装 Python，也不需要联网下载模型或
OCR 组件。

## 使用

1. 解压整个文件夹到本地目录。
2. 双击 `启动笺隐.cmd`。
3. 首次启动即可分析文档，包括扫描 PDF。

也可以直接运行 `JianYin.exe`：程序会优先查找 `models/openai-privacy-filter-q4` 中随包携带的模型。

## 注意

- 解压路径可以包含中文，但不要把程序放在只读目录。
- 映射 JSON、规则草稿和 OCR 中间文件包含原始敏感值，请只保存在受控本地位置。
- 扫描 PDF 的 OCR 在本机完成，不上传外部服务；首次识别会有几秒模型加载时间。
- 模型主要基于英文训练，中文姓名、地址等必须人工复核。
- 本工具不是匿名化、合规或法律保证。

模型来源与许可见 `models/openai-privacy-filter-q4/MODEL_NOTICE.txt`、根目录 `LICENSE`、
`NOTICE` 和 `THIRD_PARTY_NOTICES.md`。
"""


def build_bundle(
    *,
    exe: Path,
    model_dir: Path,
    output: Path,
    version: str,
) -> dict[str, object]:
    if not exe.is_file():
        raise SystemExit(f"executable not found: {exe}")
    model_root = validate_model_directory(model_dir)

    bundle_name = f"JianYin-{version}-windows-x64-with-model"
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tempfile.TemporaryDirectory(prefix="jianyin-portable-", dir=str(output.parent)) as temporary:
        staging = Path(temporary) / bundle_name
        staging.mkdir()
        shutil.copy2(exe, staging / "JianYin.exe")

        model_target = staging / "models" / MODEL_DIR_NAME
        stage_model(model_root, model_target)
        copy_docs(staging)

        (staging / "启动笺隐.cmd").write_text(
            LAUNCHER.replace("\n", "\r\n"), encoding="ascii", newline=""
        )
        (staging / "使用说明.md").write_text(USAGE, encoding="utf-8", newline="\n")

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{bundle_name}/{path.relative_to(staging).as_posix()}")

    return {
        "status": "ok",
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": sha256(output),
        "version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Windows portable JianYin bundle with Q4 model")
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="0.2.0")
    args = parser.parse_args(argv)
    result = build_bundle(
        exe=args.exe,
        model_dir=args.model_dir,
        output=args.output,
        version=args.version,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
