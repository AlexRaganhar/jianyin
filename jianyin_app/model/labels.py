"""Category labels, aliases, and display helpers."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

OFFICIAL_CATEGORIES: tuple[str, ...] = (
    "account_number",
    "private_address",
    "private_date",
    "private_email",
    "private_person",
    "private_phone",
    "private_url",
    "secret",
)

ALL_CATEGORIES: tuple[str, ...] = OFFICIAL_CATEGORIES + ("organization", "other")

CATEGORY_ALIASES: dict[str, str] = {
    "personal_name": "private_person",
    "personal_handle": "private_person",
    "personal_email": "private_email",
    "personal_phone": "private_phone",
    "personal_location": "private_address",
    "personal_date": "private_date",
    "personal_url": "private_url",
    "personal_gov_id": "account_number",
    "personal_fin_id": "account_number",
    "personal_health_id": "account_number",
    "personal_device_id": "account_number",
    "personal_vehicle_id": "account_number",
    "personal_property_id": "account_number",
    "personal_edu_id": "account_number",
    "personal_emp_id": "account_number",
    "personal_membership_id": "account_number",
    "personal_registry_id": "account_number",
    "personal_org": "organization",
    "secret_url": "secret",
}

SUBTYPE_LABELS: dict[str, str] = {
    "cn_id": "身份证号",
    "cn_mobile": "手机号",
    "cn_bank_card": "银行卡号",
    "cn_name": "姓名线索",
    "cn_landline": "座机号",
    "cn_date": "中文日期",
    "cn_address": "中文地址",
}

FALLBACK_LABELS: dict[str, str] = {
    "account_number": "账号 / 证件号",
    "private_address": "地址",
    "private_date": "日期",
    "private_email": "邮箱",
    "private_person": "姓名",
    "private_phone": "电话",
    "private_url": "链接",
    "secret": "密钥 / 密码",
    "organization": "单位 / 公司",
    "other": "其他敏感信息",
}


def load_category_labels() -> dict[str, dict[str, Any]]:
    """Load the bundled Chinese labels and highlight colors."""
    try:
        resource = files("jianyin_app").joinpath("data").joinpath("category_labels.json")
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    result: dict[str, dict[str, Any]] = {}
    for category in ALL_CATEGORIES:
        entry = payload.get(category)
        if isinstance(entry, dict):
            label = str(entry.get("label") or FALLBACK_LABELS[category])
            color = str(entry.get("color") or "#8C6A2F")
        else:
            label = FALLBACK_LABELS[category]
            color = "#8C6A2F"
        result[category] = {"label": label, "color": color}
    return result


def normalize_category(label: str) -> str:
    """Map model label spellings to the public category taxonomy."""
    value = label.strip()
    if value in ALL_CATEGORIES:
        return value
    if value in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[value]
    if value.startswith("other_"):
        return "other"
    return "other"


def category_display(category: str, subtype: str | None = None) -> str:
    labels = load_category_labels()
    base = labels.get(category, {}).get("label", FALLBACK_LABELS.get(category, "其他敏感信息"))
    if subtype and subtype in SUBTYPE_LABELS:
        return f"{base}（{SUBTYPE_LABELS[subtype]}）"
    return base


def source_display(source: str) -> str:
    if source == "model":
        return "模型"
    if source == "manual":
        return "手工"
    if source.startswith("rule:"):
        rule_id = source.split(":", 1)[1]
        return f"中文规则·{SUBTYPE_LABELS.get(rule_id, rule_id)}"
    pieces = []
    for piece in source.split("+"):
        pieces.append(source_display(piece))
    return " + ".join(pieces)
