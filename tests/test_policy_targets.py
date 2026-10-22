from __future__ import annotations

import pytest

from jianyin_app.errors import PolicyError
from jianyin_app.redaction.policy import RuleSet, default_ruleset, validate_target
from jianyin_app.redaction.targets import TargetFactory


def test_default_policy_has_expected_strategies() -> None:
    rules = default_ruleset()
    assert rules.schema_version == 2
    assert rules.rule_for("private_person")["strategy"] == "person_alias"
    assert rules.rule_for("private_phone")["strategy"] == "mask_middle"
    assert rules.rule_for("private_address")["placeholder"] == "[地址{n}]"


def test_numbered_placeholders_are_stable_per_source() -> None:
    factory = TargetFactory(default_ruleset())
    first = factory.target_for("private_address", "A 路 1 号")
    second = factory.target_for("private_address", "B 路 2 号")
    repeated = factory.target_for("private_address", "A 路 1 号")
    assert first == "[地址1]"
    assert second == "[地址2]"
    assert repeated == first


def test_person_alias_preserves_surname_and_handles_collisions() -> None:
    factory = TargetFactory(default_ruleset())
    assert factory.target_for("private_person", "张三") == "张某"
    assert factory.target_for("private_person", "张四") == "张某2"
    assert factory.target_for("private_person", "欧阳锋") == "欧阳某"
    assert factory.target_for("private_person", "Alice") == "[姓名1]"


def test_mask_middle_handles_short_and_long_values() -> None:
    factory = TargetFactory(default_ruleset())
    assert factory.target_for("private_phone", "13800138000") == "138*****000"
    assert factory.target_for("private_email", "alice@example.com") == "ali***********com"
    assert factory.target_for("account_number", "123") == "***"


def test_existing_target_seed_continues_numbering() -> None:
    factory = TargetFactory(
        default_ruleset(),
        existing=[("private_address", "旧地址", "[地址3]")],
    )
    assert factory.target_for("private_address", "新地址") == "[地址4]"


def test_old_schema_one_person_fallback_is_supported() -> None:
    rules = RuleSet.from_dict(
        {
            "schema_version": 1,
            "name": "old",
            "review_required": True,
            "default": {"strategy": "placeholder", "placeholder": "[X]"},
            "categories": {
                "private_person": {
                    "strategy": "person_alias",
                    "fallback_prefix": "[姓名",
                    "fallback_suffix": "]",
                }
            },
        }
    )
    factory = TargetFactory(rules)
    assert factory.target_for("private_person", "Alice") == "[姓名1]"


def test_invalid_policy_is_rejected() -> None:
    with pytest.raises(PolicyError):
        RuleSet.from_dict(
            {
                "default": {"strategy": "bogus"},
                "categories": {},
            }
        )


def test_validate_target_rejects_empty_or_source_leak() -> None:
    with pytest.raises(PolicyError):
        validate_target("Alice", "")
    with pytest.raises(PolicyError):
        validate_target("Alice", "Alice")
    with pytest.raises(PolicyError):
        validate_target("Alice", "[Alice]")

