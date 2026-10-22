"""Deterministic, case-consistent replacement target generation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable, Mapping

from ..detection.chinese_rules import load_surnames
from ..errors import PolicyError
from .policy import RuleSet, render_placeholder


def _target_number(template: str, target: str) -> int | None:
    if "{n}" not in template:
        return None
    pattern = re.escape(template).replace(re.escape("{n}"), r"(\d+)")
    match = re.fullmatch(pattern, target)
    return int(match.group(1)) if match else None


class TargetFactory:
    """Generate stable targets while preserving existing reviewed targets."""

    def __init__(
        self,
        rules: RuleSet,
        existing: Iterable[tuple[str, str, str]] | None = None,
    ) -> None:
        self._rules = rules
        self._targets: dict[tuple[str, str], str] = {}
        self._used_targets: dict[str, set[str]] = defaultdict(set)
        self._counters: dict[str, int] = defaultdict(int)
        self._person_counts: Counter[str] = Counter()
        self._single_surnames, self._compound_surnames = load_surnames()
        if existing:
            for category, source, target in existing:
                if source and target:
                    self.seed(category, source, target)

    def seed(self, category: str, source: str, target: str) -> None:
        key = (category, source)
        self._targets[key] = target
        self._used_targets[category].add(target)
        rule = self._rules.rule_for(category)
        if rule.get("strategy") == "placeholder":
            number = _target_number(str(rule.get("placeholder", "")), target)
            if number is not None:
                self._counters[category] = max(self._counters[category], number)
        elif rule.get("strategy") == "person_alias":
            fallback = rule.get("fallback_template")
            if isinstance(fallback, str):
                number = _target_number(fallback, target)
                if number is not None:
                    self._counters["private_person"] = max(
                        self._counters["private_person"], number
                    )
            if target and target[-1].isdigit():
                match = re.search(r"(\d+)$", target)
                if match:
                    self._person_counts[target[: match.start()]] = max(
                        self._person_counts[target[: match.start()]], int(match.group(1))
                    )
            elif target:
                self._person_counts[target] = max(self._person_counts[target], 1)

    def target_for(self, category: str, source: str, subtype: str | None = None) -> str:
        if not source:
            raise PolicyError("敏感信息原文不能为空。")
        key = (category, source)
        if key in self._targets:
            return self._targets[key]
        rule = self._rules.rule_for(category)
        strategy = rule.get("strategy")
        if strategy == "placeholder":
            template = str(rule.get("placeholder", "[敏感信息{n}]"))
            if "{n}" in template:
                self._counters[category] += 1
                target = render_placeholder(template, self._counters[category])
            else:
                target = template
        elif strategy == "mask_middle":
            target = self._mask_middle(source, rule)
        elif strategy == "person_alias":
            target = self._person_alias(source, rule)
        else:
            raise PolicyError(f"不支持的替换策略：{strategy!r}")

        if not target or target == source:
            fallback = str(rule.get("fallback_template") or "[敏感信息{n}]")
            self._counters[category] += 1
            target = render_placeholder(fallback, self._counters[category])
        if "\n" in target or "\r" in target:
            raise PolicyError("替换值不能包含换行。")
        if strategy != "person_alias" and source in target:
            raise PolicyError("替换值不能包含完整的原文值。")
        self._targets[key] = target
        self._used_targets[category].add(target)
        return target

    def _person_alias(self, source: str, rule: Mapping[str, object]) -> str:
        if source and "\u4e00" <= source[0] <= "\u9fff" and "某" not in source:
            surname = source[0]
            if source[:2] in self._compound_surnames:
                surname = source[:2]
            elif surname not in self._single_surnames:
                surname = ""
            if surname:
                base = surname + str(rule.get("chinese_suffix", "某"))
                self._person_counts[base] += 1
                count = self._person_counts[base]
                return base if count == 1 else base + str(count)
        fallback_template = rule.get("fallback_template")
        self._counters["private_person"] += 1
        number = self._counters["private_person"]
        if isinstance(fallback_template, str) and fallback_template:
            return render_placeholder(fallback_template, number)
        prefix = str(rule.get("fallback_prefix", "[姓名"))
        suffix = str(rule.get("fallback_suffix", "]"))
        return f"{prefix}{number}{suffix}"

    @staticmethod
    def _mask_middle(source: str, rule: Mapping[str, object]) -> str:
        keep_start = int(rule.get("keep_start", 3))
        keep_end = int(rule.get("keep_end", 3))
        mask_char = str(rule.get("mask_char", "*")) or "*"
        if keep_start + keep_end >= len(source):
            return mask_char[0] * len(source)
        prefix = source[:keep_start] if keep_start else ""
        suffix = source[-keep_end:] if keep_end else ""
        masked_length = len(source) - len(prefix) - len(suffix)
        return prefix + mask_char[0] * masked_length + suffix

    def reset(self) -> None:
        self._targets.clear()
        self._used_targets.clear()
        self._counters.clear()
        self._person_counts.clear()
