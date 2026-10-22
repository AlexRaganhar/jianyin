"""Model directory validation and first-run download."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from ..config import (
    MODEL_DIR_NAME,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    default_model_directory,
    model_directory_candidates,
    unique_paths,
)
from ..detection.base import ProgressCallback, emit_progress
from ..errors import ModelDownloadError, ModelError, ModelNotFoundError

REQUIRED_MODEL_FILES: tuple[str, ...] = (
    "config.json",
    "tokenizer.json",
    "viterbi_calibration.json",
    "onnx/model_q4.onnx",
    "onnx/model_q4.onnx_data",
)

_MIN_MODEL_DATA_BYTES = 100 * 1024 * 1024
_MIN_ONNX_BYTES = 10 * 1024
_MIN_TOKENIZER_BYTES = 1024


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError(f"无法读取模型元数据：{path.name}") from error
    if not isinstance(payload, Mapping):
        raise ModelError(f"模型元数据格式无效：{path.name}")
    return payload


def _candidate_root(path: Path) -> Path:
    """Accept either the model directory or its parent ``models`` directory."""
    if (path / "config.json").is_file():
        return path
    child = path / MODEL_DIR_NAME
    if (child / "config.json").is_file():
        return child
    return path


def validate_model_directory(path: str | Path) -> Path:
    """Validate the minimum official Q4 ONNX bundle and return its root."""
    resolved = Path(path).expanduser().resolve()
    root = _candidate_root(resolved)
    if not root.is_dir():
        raise ModelNotFoundError(f"未找到本地模型目录：{resolved}")
    missing = [relative for relative in REQUIRED_MODEL_FILES if not (root / relative).is_file()]
    if missing:
        raise ModelNotFoundError("Q4 ONNX 模型目录不完整，缺少：" + "、".join(missing))

    data_path = root / "onnx" / "model_q4.onnx_data"
    onnx_path = root / "onnx" / "model_q4.onnx"
    tokenizer_path = root / "tokenizer.json"
    try:
        if data_path.stat().st_size < _MIN_MODEL_DATA_BYTES:
            raise ModelNotFoundError("Q4 ONNX 外部权重文件过小，可能下载不完整。")
        if onnx_path.stat().st_size < _MIN_ONNX_BYTES:
            raise ModelNotFoundError("Q4 ONNX 图文件过小，可能下载不完整。")
        if tokenizer_path.stat().st_size < _MIN_TOKENIZER_BYTES:
            raise ModelNotFoundError("tokenizer.json 过小，可能下载不完整。")
    except OSError as error:
        raise ModelNotFoundError("无法读取 Q4 ONNX 模型文件。") from error

    config = _read_json(root / "config.json")
    id2label = config.get("id2label")
    if not isinstance(id2label, Mapping) or len(id2label) < 2:
        raise ModelError("模型 config.json 缺少有效的 id2label。")
    calibration = _read_json(root / "viterbi_calibration.json")
    try:
        biases = calibration["operating_points"]["default"]["biases"]
    except (KeyError, TypeError) as error:
        raise ModelError("viterbi_calibration.json 格式无效。") from error
    if not isinstance(biases, Mapping):
        raise ModelError("viterbi_calibration.json 的校准参数无效。")
    return root


def find_existing_model(explicit: str | Path | None = None) -> Path | None:
    for candidate in unique_paths(model_directory_candidates(explicit)):
        try:
            return validate_model_directory(candidate)
        except ModelError:
            continue
    return None


def _download(
    destination: Path,
    *,
    progress: ProgressCallback | None = None,
) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as error:
        raise ModelDownloadError(
            "缺少 huggingface_hub，无法下载模型。请重新安装笺隐依赖。"
        ) from error

    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    emit_progress(
        progress,
        {
            "stage": "model_download",
            "message": "首次使用需下载约 945 MB 的 Q4 ONNX 模型。",
            "indeterminate": True,
        },
    )
    try:
        destination.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            local_dir=str(destination),
            allow_patterns=list(REQUIRED_MODEL_FILES),
        )
    except Exception as error:
        raise ModelDownloadError(
            "无法下载官方 Q4 ONNX 模型。请检查网络或代理后重试，"
            "也可以用 --model-dir 指向完整的本地模型目录。"
        ) from error
    return validate_model_directory(destination)


def ensure_model(
    explicit: str | Path | None = None,
    *,
    allow_download: bool = True,
    offline: bool = False,
    progress: ProgressCallback | None = None,
) -> Path:
    """Find a complete model, downloading it only when explicitly allowed."""
    if explicit is not None:
        return validate_model_directory(explicit)
    existing = find_existing_model()
    if existing is not None:
        return existing
    if not allow_download or offline:
        raise ModelNotFoundError(
            "未找到完整的 Q4 ONNX 模型。请运行 `jianyin download-model`，"
            "或用 --model-dir 指定本地模型目录。"
        )
    destination = default_model_directory()
    return _download(destination, progress=progress)


def download_model(
    destination: str | Path | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> Path:
    target = Path(destination).expanduser() if destination is not None else default_model_directory()
    if target.name != MODEL_DIR_NAME and not (target / "config.json").is_file():
        target = target / MODEL_DIR_NAME
    try:
        return validate_model_directory(target)
    except ModelError:
        pass
    return _download(target, progress=progress)
