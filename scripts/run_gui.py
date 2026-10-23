"""Frozen-app entry point for the JianYin desktop GUI.

``pyproject.toml`` exposes ``jianyin-gui`` as a console script, but PyInstaller
needs a real module to import. This script is that module, and it also carries a
``--self-check`` switch so CI can verify a packaged build on a headless runner
(no window server is required: ``tkinter.Tcl()`` starts an interpreter without
opening a display, which still proves the bundled Tcl/Tk data files are found).
"""

from __future__ import annotations

import sys

APP_NAME = "JianYin"

REQUIRED_RESOURCES: tuple[str, ...] = (
    "data/category_labels.json",
    "data/chinese_rules.json",
    "data/chinese_surnames.txt",
    "data/default_rules.json",
    "assets/jianyin.png",
    "assets/jianyin.ico",
)


def self_check() -> int:
    import tkinter
    from importlib.resources import files

    import onnxruntime  # noqa: F401
    import tokenizers  # noqa: F401

    from jianyin_app import config
    from jianyin_app.gui import app as gui_app  # noqa: F401
    from jianyin_app.model.download import find_existing_model
    from jianyin_app.vendor.pdf2md.ocr import OcrEngine

    root = files("jianyin_app")
    missing = [name for name in REQUIRED_RESOURCES if not root.joinpath(*name.split("/")).is_file()]
    if missing:
        print("self-check failed: missing resources " + ", ".join(missing), flush=True)
        return 2

    # Instantiate the bundled OCR engine: this verifies the PP-OCRv6 models
    # and ONNX Runtime native libraries are present, not just importable.
    OcrEngine()

    interpreter = tkinter.Tcl()
    patchlevel = interpreter.eval("info patchlevel")
    model_dir = find_existing_model() or config.default_model_directory()

    print(
        f"self-check ok: python {sys.version.split()[0]}, "
        f"tk {patchlevel}, onnxruntime {onnxruntime.__version__}, "
        f"ocr models ok, model dir {model_dir}",
        flush=True,
    )
    return 0


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    if "--version" in sys.argv:
        from jianyin_app import __version__

        print(__version__, flush=True)
        return 0
    from jianyin_app.gui.app import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
