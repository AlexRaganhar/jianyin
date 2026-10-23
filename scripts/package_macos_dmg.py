#!/usr/bin/env python3
"""Build a macOS DMG with the Q4 model and the bundled OCR engine.

The DMG contains ``JianYin.app`` with the model inside
``Contents/MacOS/models/openai-privacy-filter-q4`` and an ``Applications``
symlink for drag-and-drop installation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from release_common import copy_docs, sha256, stage_model  # noqa: E402

from jianyin_app.config import MODEL_DIR_NAME  # noqa: E402
from jianyin_app.model.download import validate_model_directory  # noqa: E402


def build_dmg(*, app: Path, model_dir: Path, output: Path, version: str, arch: str) -> dict[str, object]:
    if not app.is_dir():
        raise SystemExit(f"application bundle not found: {app}")
    model_root = validate_model_directory(model_dir)
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tempfile.TemporaryDirectory(prefix="jianyin-dmg-", dir=str(output.parent)) as temporary:
        staging = Path(temporary) / "stage"
        staging.mkdir()
        target_app = staging / "JianYin.app"
        subprocess.run(["ditto", str(app), str(target_app)], check=True)

        model_target = target_app / "Contents" / "MacOS" / "models" / MODEL_DIR_NAME
        stage_model(model_root, model_target)
        copy_docs(staging)

        usage = ROOT / "docs" / "MACOS_WITH_MODEL.md"
        if usage.is_file():
            shutil.copy2(usage, staging / "使用说明-含模型版.md")

        (staging / "Applications").symlink_to("/Applications")

        command = [
            "hdiutil",
            "create",
            "-volname",
            "笺隐 JianYin",
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(output),
        ]
        print("$ " + " ".join(command), flush=True)
        subprocess.run(command, check=True)

    if not output.is_file():
        raise SystemExit(f"DMG was not created: {output}")
    return {
        "status": "ok",
        "output": str(output),
        "size": output.stat().st_size,
        "sha256": sha256(output),
        "version": version,
        "arch": arch,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a macOS JianYin DMG with Q4 model")
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--arch", default="arm64")
    args = parser.parse_args(argv)
    result = build_dmg(
        app=args.app,
        model_dir=args.model_dir,
        output=args.output,
        version=args.version,
        arch=args.arch,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
