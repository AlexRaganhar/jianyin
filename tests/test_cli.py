from __future__ import annotations

import json

from jianyin_app import cli
from jianyin_app.errors import ModelNotFoundError
from tests.fakes import FakeDetector


def _fake_detector(*_args, **_kwargs) -> FakeDetector:
    return FakeDetector(
        [
            ("Alice", "private_person", None),
            ("13800138000", "private_phone", None),
        ]
    )


def test_cli_redact_writes_outputs_without_printing_sources(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_build_detector", _fake_detector)
    source = tmp_path / "材料.txt"
    source.write_text("Alice 的电话是 13800138000。\n", encoding="utf-8")
    output = tmp_path / "脱敏.md"
    mapping = tmp_path / "映射.json"
    code = cli.main(
        [
            "redact",
            "--input",
            str(source),
            "--output-md",
            str(output),
            "--mapping",
            str(mapping),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Alice" not in captured.out
    assert "13800138000" not in captured.out
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert "Alice" not in output.read_text(encoding="utf-8")
    assert "Alice" in mapping.read_text(encoding="utf-8")


def test_cli_restore_round_trips(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_build_detector", _fake_detector)
    source = tmp_path / "材料.md"
    source.write_text("Alice 的电话是 13800138000。\n", encoding="utf-8")
    redacted = tmp_path / "脱敏.md"
    mapping = tmp_path / "映射.json"
    assert cli.main(
        ["redact", "--input", str(source), "--output-md", str(redacted), "--mapping", str(mapping)]
    ) == 0
    restored = tmp_path / "还原.md"
    code = cli.main(
        ["restore", "--input", str(redacted), "--mapping", str(mapping), "--output-md", str(restored)]
    )
    assert code == 0
    assert restored.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_cli_analyze_then_apply(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(cli, "_build_detector", _fake_detector)
    source = tmp_path / "材料.txt"
    source.write_text("Alice 在这里。\n", encoding="utf-8")
    draft = tmp_path / "draft.json"
    assert cli.main(["analyze", "--input", str(source), "--draft", str(draft)]) == 0
    assert draft.is_file()
    output = tmp_path / "脱敏.md"
    mapping = tmp_path / "映射.json"
    assert cli.main(
        [
            "apply",
            "--input",
            str(source),
            "--draft",
            str(draft),
            "--output-md",
            str(output),
            "--mapping",
            str(mapping),
        ]
    ) == 0
    assert "Alice" not in output.read_text(encoding="utf-8")


def test_cli_refuses_overwrite_without_force(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cli, "_build_detector", _fake_detector)
    source = tmp_path / "材料.txt"
    source.write_text("Alice\n", encoding="utf-8")
    output = tmp_path / "脱敏.md"
    output.write_text("existing\n", encoding="utf-8")
    mapping = tmp_path / "映射.json"
    code = cli.main(
        ["redact", "--input", str(source), "--output-md", str(output), "--mapping", str(mapping)]
    )
    assert code == 1
    assert output.read_text(encoding="utf-8") == "existing\n"
    assert not mapping.exists()


def test_cli_model_error_writes_no_output(monkeypatch, tmp_path, capsys) -> None:
    def fail(*_args, **_kwargs):
        raise ModelNotFoundError()

    monkeypatch.setattr(cli, "_build_detector", fail)
    source = tmp_path / "材料.txt"
    source.write_text("Alice\n", encoding="utf-8")
    output = tmp_path / "脱敏.md"
    mapping = tmp_path / "映射.json"
    code = cli.main(
        ["redact", "--input", str(source), "--output-md", str(output), "--mapping", str(mapping)]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert not output.exists()
    assert not mapping.exists()
    assert "Alice" not in captured.err

