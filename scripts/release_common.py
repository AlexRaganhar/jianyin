#!/usr/bin/env python3
"""Shared release-bundle helpers: model files, notices, checksums.

One source of truth for the five Q4 files and the model notice keeps the
portable ZIP, Windows installer and macOS DMG identical.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from jianyin_app.config import MODEL_REPOSITORY, MODEL_REVISION

ROOT = Path(__file__).resolve().parents[1]

MODEL_FILES: tuple[str, ...] = (
    "config.json",
    "tokenizer.json",
    "viterbi_calibration.json",
    "onnx/model_q4.onnx",
    "onnx/model_q4.onnx_data",
)

MODEL_NOTICE = f"""OpenAI Privacy Filter

Repository: {MODEL_REPOSITORY}
Revision: {MODEL_REVISION}
License: Apache License 2.0
Source: https://huggingface.co/openai/privacy-filter

This folder is a local copy bundled with JianYin for offline model loading.
The model is an aid, not an anonymization or compliance guarantee. Manual
review is required for legal, medical, financial, and other high-risk material.
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_docs(target: Path) -> None:
    """Copy the licence/notice set into a release staging directory."""
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "README.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, target / name)
    licenses = ROOT / "third_party_licenses"
    if licenses.is_dir():
        shutil.copytree(licenses, target / "third_party_licenses")


def stage_model(model_root: Path, target: Path) -> None:
    """Copy the Q4 files, model notice and per-file checksums."""
    sums: list[str] = []
    for relative in MODEL_FILES:
        source = model_root / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        sums.append(f"{sha256(destination)}  {relative.replace(chr(92), '/')}")
    (target / "MODEL_NOTICE.txt").write_text(MODEL_NOTICE, encoding="utf-8", newline="\n")
    (target / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
