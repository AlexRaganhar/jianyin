from __future__ import annotations

from jianyin_app.config import ChineseRuleOptions
from jianyin_app.detection.chinese_rules import ChineseRuleDetector, luhn_valid, valid_cn_id


def _detector(**kwargs) -> ChineseRuleDetector:
    return ChineseRuleDetector(ChineseRuleOptions(**kwargs))


def test_valid_cn_id_checksum() -> None:
    assert valid_cn_id("11010519491231002X")
    assert not valid_cn_id("440301198503121234")
    assert not valid_cn_id("110105194912310021")


def test_luhn_validation() -> None:
    assert luhn_valid("4111111111111111")
    assert not luhn_valid("6222020200112345678")


def test_standard_identifiers_are_detected() -> None:
    text = "手机13800138000，身份证11010519491231002X，银行卡4111111111111111。"
    detections = _detector().detect(text).detections
    by_subtype = {detection.subtype: detection.text for detection in detections}
    assert by_subtype["cn_mobile"] == "13800138000"
    assert by_subtype["cn_id"] == "11010519491231002X"
    assert by_subtype["cn_bank_card"] == "4111111111111111"


def test_name_context_and_stopwords() -> None:
    text = "被告人张三，男，住北京市。北京市第三中级人民法院于2024年5月1日作出判决。"
    detections = _detector().detect(text).detections
    names = [detection.text for detection in detections if detection.subtype == "cn_name"]
    assert "张三" in names
    assert all("法院" not in name for name in names)


def test_compound_surname_and_ethnic_name() -> None:
    text = "我叫欧阳锋。被害人阿卜杜拉·买买提。"
    names = [
        detection.text
        for detection in _detector().detect(text).detections
        if detection.subtype == "cn_name"
    ]
    assert "欧阳锋" in names
    assert "阿卜杜拉·买买提" in names


def test_already_masked_name_is_skipped() -> None:
    names = [
        detection.text
        for detection in _detector().detect("被告人张某，男。").detections
        if detection.subtype == "cn_name"
    ]
    assert "张某" not in names


def test_rules_can_be_disabled() -> None:
    text = "手机13800138000，身份证11010519491231002X。"
    detections = _detector(cn_mobile=False, cn_id=False).detect(text).detections
    assert not [item for item in detections if item.subtype in {"cn_mobile", "cn_id"}]

