from __future__ import annotations

from jianyin_app.detection.base import Detection, DetectionBatch
from jianyin_app.detection.merge import canonicalize, merge_batches


def _detection(category: str, start: int, end: int, text: str, source: str = "model", subtype=None, priority=60):
    return Detection(
        category=category,
        start=start,
        end=end,
        text=text,
        source=source,
        subtype=subtype,
        priority=priority,
    )


def test_same_range_sources_are_merged() -> None:
    text = "张三"
    result = canonicalize(
        text,
        [
            _detection("private_person", 0, 2, text, "model", priority=60),
            _detection("private_person", 0, 2, text, "rule:cn_name", "cn_name", priority=40),
        ],
    )
    assert len(result.detections) == 1
    assert result.detections[0].source == "model+rule:cn_name"
    assert result.detections[0].priority == 60


def test_model_single_surname_does_not_beat_full_name_rule() -> None:
    text = "被告人张三。"
    result = canonicalize(
        text,
        [
            _detection("private_person", 3, 4, "张", "model", priority=60),
            _detection("private_person", 3, 5, "张三", "rule:cn_name", "cn_name", priority=40),
        ],
    )
    assert len(result.detections) == 1
    assert result.detections[0].text == "张三"
    assert result.detections[0].subtype == "cn_name"


def test_precise_id_rule_wins_over_model_label_prefix() -> None:
    text = "身份证号11010519491231002X"
    result = canonicalize(
        text,
        [
            _detection("account_number", 0, len(text), text, "model", priority=60),
            _detection("account_number", 4, len(text), "11010519491231002X", "rule:cn_id", "cn_id", priority=80),
        ],
    )
    assert len(result.detections) == 1
    assert result.detections[0].text == "11010519491231002X"
    assert result.detections[0].subtype == "cn_id"


def test_page_markers_are_protected() -> None:
    text = "<!-- PDF page 1 -->\nAlice"
    result = canonicalize(
        text,
        [_detection("private_person", 0, len(text), text, "model")],
    )
    assert result.detections == ()
    assert result.skipped_protected == 1


def test_cross_category_priority_keeps_higher_priority() -> None:
    text = "13800138000"
    result = canonicalize(
        text,
        [
            _detection("account_number", 0, 11, text, "model", priority=60),
            _detection("private_phone", 0, 11, text, "rule:cn_mobile", "cn_mobile", priority=80),
        ],
    )
    assert len(result.detections) == 1
    assert result.detections[0].category == "private_phone"


def test_merge_batches_combines_warnings_and_stats() -> None:
    text = "Alice"
    batch = merge_batches(
        [
            DetectionBatch(text=text, detections=(_detection("private_person", 0, 5, text),), warnings=("a",)),
            DetectionBatch(text=text, detections=(), warnings=("a", "b")),
        ]
    )
    assert [warning for warning in batch.warnings] == ["a", "b"]
    assert batch.stats["canonical_span_count"] == 1

