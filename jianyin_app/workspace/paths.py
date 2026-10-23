"""Atomic writes and safe workspace path resolution."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import WorkspaceError

_UUID_HEX_RE = re.compile(r"^[0-9a-f]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise WorkspaceError("无法创建本地工作区目录。") from error
    return path


def atomic_write_text(path: Path, content: str) -> Path:
    ensure_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="")
        os.replace(temporary, path)
    except OSError as error:
        raise WorkspaceError("无法写入本地文件。") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def write_json(path: Path, payload: Any) -> Path:
    return atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WorkspaceError("本地文件不存在。") from error
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceError("本地 JSON 文件无法读取。") from error
    if not isinstance(payload, dict):
        raise WorkspaceError("本地 JSON 文件格式无效。")
    return payload


def validate_case_id(case_id: str) -> str:
    if not _UUID_HEX_RE.fullmatch(case_id):
        raise WorkspaceError("案件标识无效。")
    return case_id


def validate_document_id(document_id: str) -> str:
    if not _UUID_HEX_RE.fullmatch(document_id):
        raise WorkspaceError("文档标识无效。")
    return document_id


def resolve_within(root: Path, relative: str | Path) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise WorkspaceError("文件路径越出了本地工作区。")
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise WorkspaceError("文件路径越出了本地工作区。") from error
    return candidate


def relative_to(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise WorkspaceError("文件路径越出了本地工作区。") from error
