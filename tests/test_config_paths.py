from __future__ import annotations

import sys

from jianyin_app import config


def test_frozen_app_prefers_model_beside_executable(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "JianYin.exe"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("JIANYIN_MODEL_DIR", raising=False)
    monkeypatch.delenv("OPF_MODEL_DIR", raising=False)

    portable = tmp_path / "models" / config.MODEL_DIR_NAME
    assert config.portable_model_directory() == portable
    assert config.default_model_directory() == (
        tmp_path / "local" / "JianYin" / "models" / config.MODEL_DIR_NAME
    )
    assert portable in config.model_directory_candidates()
