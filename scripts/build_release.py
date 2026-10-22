#!/usr/bin/env python3
"""Build the standalone JianYin desktop binaries with PyInstaller.

The offline Q4 model (~945 MB) is *not* bundled: it is downloaded on first run
into the per-user application data directory (or supplied via ``JIANYIN_MODEL_DIR``).

Usage:
    python scripts/build_release.py            # build for the current platform
    python scripts/build_release.py --check    # only print the command that would run
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "JianYin"
BUNDLE_ID = "io.github.alexraganhar.jianyin"
ICON_PNG = ROOT / "jianyin_app" / "assets" / "jianyin.png"
ICON_ICO = ROOT / "jianyin_app" / "assets" / "jianyin.ico"

# (icon_<n>x<n>.png pixel size, file name) pairs that ``iconutil`` expects.
ICONSET_SIZES: tuple[tuple[int, str], ...] = (
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
)


def run(command: list[str]) -> None:
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT)


def common_args() -> list[str]:
    return [
        str(ROOT / "scripts" / "run_gui.py"),
        "--noconfirm",
        "--clean",
        "--name",
        APP_NAME,
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        # Package data: data/*.json, data/*.txt and assets/* are read through
        # importlib.resources at runtime, so they must sit next to the package.
        "--collect-data",
        "jianyin_app",
        "--collect-submodules",
        "onnxruntime",
        # huggingface_hub exposes its public API through a lazy __getattr__
        # table, so PyInstaller's static analysis cannot see those imports.
        "--collect-submodules",
        "huggingface_hub",
        "--copy-metadata",
        "huggingface_hub",
        "--copy-metadata",
        "onnxruntime",
        "--copy-metadata",
        "tokenizers",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "IPython",
    ]


def make_icns() -> Path:
    """Convert the packaged PNG into an ``.icns`` bundle (macOS only)."""
    iconset = ROOT / "build" / f"{APP_NAME}.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir(parents=True, exist_ok=True)
    for pixels, name in ICONSET_SIZES:
        subprocess.run(
            ["sips", "-z", str(pixels), str(pixels), str(ICON_PNG), "--out", str(iconset / name)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    target = ROOT / "build" / f"{APP_NAME}.icns"
    run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)])
    return target


def build_args() -> list[str]:
    system = platform.system()
    if system == "Windows":
        return common_args() + [
            "--onefile",
            "--windowed",
            "--icon",
            str(ICON_ICO),
        ]
    if system == "Darwin":
        return common_args() + [
            "--windowed",
            "--osx-bundle-identifier",
            BUNDLE_ID,
            "--icon",
            str(make_icns()),
        ]
    raise SystemExit(f"unsupported platform: {system}")


def main() -> int:
    args = build_args()
    command = [sys.executable, "-m", "PyInstaller", *args]
    if "--check" in sys.argv:
        print(" ".join(command))
        return 0
    run(command)
    system = platform.system()
    if system == "Windows":
        print(f"\nbuilt: {ROOT / 'dist' / (APP_NAME + '.exe')}")
    else:
        print(f"\nbuilt: {ROOT / 'dist' / (APP_NAME + '.app')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
