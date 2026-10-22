"""Configuration, paths, and small validated settings objects."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .errors import ConfigurationError

MODEL_REPOSITORY = "openai/privacy-filter"
MODEL_REVISION = "7ffa9a043d54d1be65afb281eddf0ffbe629385b"
MODEL_VARIANT = "q4"
MODEL_DIR_NAME = "openai-privacy-filter-q4"
MODEL_ENV_VARS = ("JIANYIN_MODEL_DIR", "OPF_MODEL_DIR")
CASE_WORKSPACE_ENV_VARS = ("JIANYIN_CASE_WORKSPACE", "OPF_CASE_WORKSPACE")
OCR_DIR_ENV_VARS = ("JIANYIN_PDF_TO_MARKDOWN_DIR", "OPF_PDF_TO_MARKDOWN_DIR")

DECODE_MODES = ("viterbi", "argmax")
DEFAULT_WINDOW_SIZE = 4096
DEFAULT_OVERLAP_TOKENS = 256
MAX_WINDOW_SIZE = 8192
MIN_WINDOW_SIZE = 512
MAX_TOKENS = 200_000
MAX_CHARACTERS = 2_000_000

CHINESE_RULE_IDS = (
    "cn_id",
    "cn_mobile",
    "cn_bank_card",
    "cn_name_context",
    "cn_landline",
    "cn_date",
    "cn_address",
)


def project_root() -> Path:
    """Return the editable project root, or the package parent when installed."""
    return Path(__file__).resolve().parents[1]


def _local_app_data() -> Path:
    """Return the per-user application data root for the current platform."""
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local"
    xdg = os.environ.get("XDG_DATA_HOME")
    return Path(xdg) if xdg else Path.home() / ".local" / "share"


def default_model_directory() -> Path:
    root = project_root()
    if (root / "pyproject.toml").is_file():
        return root / "models" / MODEL_DIR_NAME
    return _local_app_data() / "JianYin" / "models" / MODEL_DIR_NAME


def _writable_directory(path: Path) -> bool:
    """Return whether this process can create and write inside ``path``."""
    probe = path / f".jianyin_write_probe_{os.getpid()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def default_workspace_directory() -> Path:
    for name in CASE_WORKSPACE_ENV_VARS:
        configured = os.environ.get(name)
        if configured:
            return Path(configured).expanduser()
    candidates = [
        Path.home() / "Documents" / "JianYin Cases",
        project_root().parent / "JianYin Cases",
        Path.cwd() / "JianYin Cases",
    ]
    for candidate in candidates:
        if _writable_directory(candidate):
            return candidate
    return candidates[0]


def model_directory_candidates(explicit: str | Path | None = None) -> list[Path]:
    """Return model directories to try, most specific first."""
    values: list[Path] = []
    if explicit is not None:
        values.append(Path(explicit).expanduser())
    for name in MODEL_ENV_VARS:
        configured = os.environ.get(name)
        if configured:
            values.append(Path(configured).expanduser())
    values.append(default_model_directory())
    return values


def pdf_to_markdown_candidates() -> list[Path]:
    values: list[Path] = []
    for name in OCR_DIR_ENV_VARS:
        configured = os.environ.get(name)
        if configured:
            values.append(Path(configured).expanduser())
    root = project_root()
    values.extend(
        [
            root.parent / "pdf-to-markdown",
            root / "pdf-to-markdown",
        ]
    )
    return values


def _as_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"{field_name} 必须是整数。")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{field_name} 必须是整数。") from error


def _as_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, str)):
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"{field_name} 必须是布尔值。")


@dataclass
class ModelConfig:
    """Runtime settings for the local Q4 ONNX detector."""

    model_dir: str | None = None
    window_size: int = DEFAULT_WINDOW_SIZE
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
    decode_mode: str = "viterbi"
    device: str = "cpu"
    offline: bool = False
    max_tokens: int = MAX_TOKENS
    max_characters: int = MAX_CHARACTERS

    def validate(self) -> None:
        if self.device not in {"cpu", "auto"}:
            raise ConfigurationError("笺隐只支持 CPU 推理。")
        if self.decode_mode not in DECODE_MODES:
            raise ConfigurationError(f"不支持的解码模式：{self.decode_mode!r}")
        if not MIN_WINDOW_SIZE <= self.window_size <= MAX_WINDOW_SIZE:
            raise ConfigurationError(
                f"窗口大小必须在 {MIN_WINDOW_SIZE} 到 {MAX_WINDOW_SIZE} 之间。"
            )
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.window_size // 2:
            raise ConfigurationError("窗口重叠必须是非负数，且小于窗口大小的一半。")
        if self.max_tokens <= 0 or self.max_characters <= 0:
            raise ConfigurationError("文档长度限制必须是正整数。")

    def normalized(self) -> "ModelConfig":
        self.validate()
        return ModelConfig(
            model_dir=self.model_dir,
            window_size=self.window_size,
            overlap_tokens=self.overlap_tokens,
            decode_mode=self.decode_mode,
            device="cpu",
            offline=self.offline,
            max_tokens=self.max_tokens,
            max_characters=self.max_characters,
        )


@dataclass
class ChineseRuleOptions:
    """Per-rule switches for the local Chinese PII supplement."""

    cn_id: bool = True
    cn_mobile: bool = True
    cn_bank_card: bool = True
    cn_name_context: bool = True
    cn_landline: bool = False
    cn_date: bool = False
    cn_address: bool = False

    def enabled(self, rule_id: str) -> bool:
        value = getattr(self, rule_id, False)
        return bool(value)

    def enabled_rule_ids(self) -> tuple[str, ...]:
        return tuple(rule_id for rule_id in CHINESE_RULE_IDS if self.enabled(rule_id))

    def as_dict(self) -> dict[str, bool]:
        return {rule_id: self.enabled(rule_id) for rule_id in CHINESE_RULE_IDS}

    @classmethod
    def from_dict(cls, payload: Any) -> "ChineseRuleOptions":
        if not isinstance(payload, dict):
            return cls()
        values: dict[str, bool] = {}
        for rule_id in CHINESE_RULE_IDS:
            if rule_id in payload:
                values[rule_id] = _as_bool(payload[rule_id], f"chinese_rules.{rule_id}")
        return cls(**values)


@dataclass(frozen=True)
class DetectionOptions:
    """Which detection sources are enabled for one analysis run."""

    model_enabled: bool = True
    chinese: ChineseRuleOptions = field(default_factory=ChineseRuleOptions)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_enabled": self.model_enabled,
            "chinese_rules": self.chinese.as_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "DetectionOptions":
        if not isinstance(payload, dict):
            return cls()
        model_enabled = payload.get("model_enabled", True)
        return cls(
            model_enabled=_as_bool(model_enabled, "model_enabled"),
            chinese=ChineseRuleOptions.from_dict(payload.get("chinese_rules")),
        )


@dataclass
class WorkspaceSettings:
    """Non-sensitive settings persisted in ``workspace.json``."""

    model_dir: str | None = None
    policy_path: str | None = None
    chinese: ChineseRuleOptions = field(default_factory=ChineseRuleOptions)
    window_size: int = DEFAULT_WINDOW_SIZE
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS
    decode_mode: str = "viterbi"
    export_docx: bool = True

    def model_config(self, *, offline: bool = False) -> ModelConfig:
        return ModelConfig(
            model_dir=self.model_dir,
            window_size=self.window_size,
            overlap_tokens=self.overlap_tokens,
            decode_mode=self.decode_mode,
            device="cpu",
            offline=offline,
        ).normalized()

    def detection_options(self) -> DetectionOptions:
        return DetectionOptions(chinese=self.chinese)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_dir": self.model_dir,
            "policy_path": self.policy_path,
            "chinese_rules": self.chinese.as_dict(),
            "window_size": self.window_size,
            "overlap_tokens": self.overlap_tokens,
            "decode_mode": self.decode_mode,
            "export_docx": self.export_docx,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "WorkspaceSettings":
        if not isinstance(payload, dict):
            return cls()
        settings = cls(
            model_dir=payload.get("model_dir") or None,
            policy_path=payload.get("policy_path") or None,
            chinese=ChineseRuleOptions.from_dict(payload.get("chinese_rules")),
            window_size=_as_int(payload.get("window_size", DEFAULT_WINDOW_SIZE), "window_size"),
            overlap_tokens=_as_int(payload.get("overlap_tokens", DEFAULT_OVERLAP_TOKENS), "overlap_tokens"),
            decode_mode=str(payload.get("decode_mode", "viterbi")),
            export_docx=_as_bool(payload.get("export_docx", True), "export_docx"),
        )
        settings.model_config().validate()
        return settings


def settings_from_env() -> WorkspaceSettings:
    """Build settings from environment variables for CLI use."""
    return WorkspaceSettings(
        model_dir=os.environ.get("JIANYIN_MODEL_DIR") or os.environ.get("OPF_MODEL_DIR"),
    )


def ensure_within(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and ensure it stays inside ``root``."""
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ConfigurationError("文件路径越出了本地工作区。") from error
    return resolved


def unique_paths(values: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
