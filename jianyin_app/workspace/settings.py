"""Workspace settings persistence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..config import WorkspaceSettings
from ..errors import ConfigurationError
from .paths import atomic_write_text, read_json


def settings_from_workspace(payload: Mapping[str, Any]) -> WorkspaceSettings:
    settings = payload.get("settings")
    if not isinstance(settings, Mapping):
        return WorkspaceSettings()
    return WorkspaceSettings.from_dict(settings)


def load_settings(workspace_file: Path) -> WorkspaceSettings:
    payload = read_json(workspace_file)
    return settings_from_workspace(payload)


def save_settings(workspace_file: Path, settings: WorkspaceSettings) -> None:
    payload = read_json(workspace_file)
    payload["settings"] = settings.as_dict()
    atomic_write_text(workspace_file, _json_text(payload))


def _json_text(payload: Mapping[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def validate_settings(settings: WorkspaceSettings) -> None:
    try:
        settings.model_config()
    except ConfigurationError:
        raise
