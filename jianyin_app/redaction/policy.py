"""Replacement policy rules (categories and target strategies)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping

from ..errors import PolicyError

SUPPORTED_STRATEGIES = {"placeholder", "mask_middle", "person_alias"}
_TEMPLATE_RE = re.compile(r"\{n\}")


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PolicyError(f"规则文件必须包含 {name} 对象。")
    return value


def _validate_rule(rule: Mapping[str, Any], category: str) -> None:
    strategy = rule.get("strategy")
    if strategy not in SUPPORTED_STRATEGIES:
        raise PolicyError(f"规则 {category!r} 使用了不支持的 strategy：{strategy!r}")
    if strategy == "placeholder":
        placeholder = rule.get("placeholder")
        if not isinstance(placeholder, str) or not placeholder:
            raise PolicyError(f"规则 {category!r} 的 placeholder 必须是非空字符串。")
        if "\n" in placeholder or "\r" in placeholder:
            raise PolicyError(f"规则 {category!r} 的 placeholder 不能包含换行。")
    if strategy == "mask_middle":
        for key in ("keep_start", "keep_end"):
            value = rule.get(key, 3)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PolicyError(f"规则 {category!r} 的 {key} 必须是非负整数。")
        mask_char = rule.get("mask_char", "*")
        if not isinstance(mask_char, str) or not mask_char or "\n" in mask_char:
            raise PolicyError(f"规则 {category!r} 的 mask_char 无效。")
    if strategy == "person_alias":
        for key in ("chinese_suffix", "fallback_template", "fallback_prefix", "fallback_suffix"):
            value = rule.get(key)
            if value is not None and not isinstance(value, str):
                raise PolicyError(f"规则 {category!r} 的 {key} 必须是字符串。")
        fallback_template = rule.get("fallback_template")
        if fallback_template is not None and ("\n" in fallback_template or "\r" in fallback_template):
            raise PolicyError(f"规则 {category!r} 的 fallback_template 不能包含换行。")


@dataclass
class RuleSet:
    """Replacement policies keyed by privacy category."""

    name: str
    schema_version: int
    review_required: bool
    default_rule: dict[str, Any]
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuleSet":
        if not isinstance(payload, Mapping):
            raise PolicyError("规则文件必须是 JSON 对象。")
        default_rule = _require_mapping(payload.get("default"), "default")
        categories = _require_mapping(payload.get("categories"), "categories")
        schema_version = int(payload.get("schema_version", 1))
        if schema_version not in {1, 2}:
            raise PolicyError(f"不支持的政策规则版本：{schema_version}")
        _validate_rule(default_rule, "default")
        normalized_categories: dict[str, dict[str, Any]] = {}
        for category, rule in categories.items():
            if not isinstance(category, str) or not category:
                raise PolicyError("categories 中的类别名称必须是非空字符串。")
            if not isinstance(rule, Mapping):
                raise PolicyError(f"类别 {category!r} 的规则必须是 JSON 对象。")
            _validate_rule(rule, category)
            normalized_categories[category] = dict(rule)
        return cls(
            name=str(payload.get("name", "custom-rules")),
            schema_version=schema_version,
            review_required=bool(payload.get("review_required", True)),
            default_rule=dict(default_rule),
            categories=normalized_categories,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "RuleSet":
        rule_path = Path(path)
        try:
            payload = json.loads(rule_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise PolicyError(f"未找到规则文件：{rule_path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise PolicyError(f"规则文件不是有效 JSON：{rule_path}") from error
        return cls.from_dict(payload)

    def rule_for(self, category: str) -> dict[str, Any]:
        rule = dict(self.default_rule)
        rule.update(self.categories.get(category, {}))
        return rule

    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "schema_version": self.schema_version,
            "review_required": self.review_required,
        }


def default_ruleset() -> RuleSet:
    resource = files("jianyin_app").joinpath("data").joinpath("default_rules.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyError("无法读取内置默认规则。") from error
    return RuleSet.from_dict(payload)


def load_ruleset(path: str | Path | None) -> RuleSet:
    return RuleSet.from_path(path) if path else default_ruleset()


def validate_target(source: str, target: str) -> None:
    if not target:
        raise PolicyError("替换值不能为空。")
    if "\n" in target or "\r" in target:
        raise PolicyError("替换值不能包含换行。")
    if target == source:
        raise PolicyError("替换值不能与原文完全相同。")
    if source and source in target:
        raise PolicyError("替换值不能包含完整的原文值。")


def render_placeholder(template: str, number: int) -> str:
    return _TEMPLATE_RE.sub(str(number), template)
