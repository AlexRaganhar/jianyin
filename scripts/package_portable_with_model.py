#!/usr/bin/env python3
"""Build a Windows portable JianYin package with the Q4 model included.

The package contains the PyInstaller ``JianYin.exe``, the five required Q4
ONNX files, a launcher that points ``JIANYIN_MODEL_DIR`` at the bundled model,
license/notice files, model checksums and a short Chinese usage note.

This script is used by ``.github/workflows/with-model.yml`` and can be run
locally after building ``JianYin.exe`` with ``scripts/build_release.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jianyin_app.config import MODEL_DIR_NAME, MODEL_REPOSITORY, MODEL_REVISION  # noqa: E402
from jianyin_app.model.download import validate_model_directory  # noqa: E402

MODEL_FILES: tuple[str, ...] = (
    "config.json",
    "tokenizer.json",
    "viterbi_calibration.json",
    "onnx/model_q4.onnx",
    "onnx/model_q4.onnx_data",
)

LAUNCHER = """@echo off
setlocal
set "JIANYIN_MODEL_DIR=%~dp0models\\{model_dir}"
start "" "%~dp0JianYin.exe"
endlocal
""".format(model_dir=MODEL_DIR_NAME)

MODEL_NOTICE = f"""OpenAI Privacy Filter

Repository: {MODEL_REPOSITORY}
Revision: {MODEL_REVISION}
License: Apache License 2.0
Source: https://huggingface.co/openai/privacy-filter

This folder is a local copy bundled with JianYin for offline model loading.
The model is an aid, not an anonymization or compliance guarantee. Manual
review is required for legal, medical, financial, and other high-risk material.
"""

USAGE = """# 笺隐 · Windows 含模型便携版

本包已经包含 PyInstaller 打包的 `JianYin.exe` 和完整的 Q4 ONNX 模型，不需要安装 Python，也不需要联网下载模型。

## 使用

1. 解压整个文件夹到本地目录。
2. 双击 `启动笺隐.cmd`。
3. 首次启动即可分析文档。

也可以直接运行 `JianYin.exe`：程序会优先查找 `models/openai-privacy-filter-q4` 中随包携带的模型。

## 注意

- 解压路径可以包含中文，但不要把程序放在只读目录。
- 映射 JSON、规则草稿和 OCR 中间文件包含原始敏感值，请只保存在受控本地位置。
- 扫描 PDF OCR 仍需要本机安装 `pdf-to-markdown`；它不是本包的一部分。
- 模型主要基于英文训练，中文姓名、地址等必须人工复核。
- 本工具不是匿名化、合规或法律保证。

模型来源与许可见 `models/openai-privacy-filter-q4/MODEL_NOTICE.txt`、根目录 `LICENSE` 和 `NOTICE`。
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        for relative in MODEL_FILES:
            source = model_root / relative
            target = model_target / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        for name in ("LICENSE", "NOTICE", "README.md"):
            source = ROOT / name
            if source.is_file():
                shutil.copy2(source, staging / name)

        (staging / "启动笺隐.cmd").write_text(
            LAUNCHER.replace("\n", "\r\n"), encoding="ascii", newline=""
        )
        (staging / "使用说明.md").write_text(USAGE, encoding="utf-8", newline="\n")
        (model_target / "MODEL_NOTICE.txt").write_text(MODEL_NOTICE, encoding="utf-8", newline="\n")

        model_sums = []
        for relative in MODEL_FILES:
            model_sums.append(f"{_sha256(model_target / relative)}  {relative.replace(chr(92), '/')}")
        (model_target / "SHA256SUMS.txt").write_text(
            "\n".join(model_sums) + "\n", encoding="utf-8", newline="\n"
        )

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{bundle_name}/{path.relative_to(staging).as_posix()}")

    return {
        "status": "ok",
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": _sha256(output),
        "version": version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Windows portable JianYin bundle with Q4 model")
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="0.1.0")
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
