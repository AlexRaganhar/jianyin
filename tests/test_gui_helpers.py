from __future__ import annotations

from jianyin_app.documents.markdown import page_anchored_text, page_ranges
from jianyin_app.gui.formatting import (
    candidate_origin,
    case_status_label,
    clip_highlights,
    format_summary,
    page_label,
)
from jianyin_app.redaction.schema import CandidateRule


def test_clip_highlights_respects_page_offset() -> None:
    clipped = clip_highlights([(10, 15, "a"), (20, 25, "b")], base_offset=10, length=8)
    assert clipped == [(0, 5, "a")]


def test_page_ranges_and_anchor() -> None:
    text = page_anchored_text(["一", "二"])
    ranges = page_ranges(text)
    assert [item.number for item in ranges] == [1, 2]
    assert page_label(2) == "第 2 页"


def test_format_summary_is_human_readable() -> None:
    text = format_summary(
        {
            "document_count": 2,
            "detected_span_count": 3,
            "by_category": {"private_person": 2},
            "by_source": {"model": 2},
        }
    )
    assert "文档数：2" in text
    assert "姓名" in text
    assert "模型" in text


def test_candidate_origin_and_status() -> None:
    candidate = CandidateRule(
        id=1,
        category="private_person",
        source="张三",
        target="张某",
        detection_sources=["model", "rule:cn_name"],
    )
    assert "模型" in candidate_origin(candidate)
    assert "姓名线索" in candidate_origin(candidate)
    assert case_status_label("redacted") == "已脱敏"
    assert "待重新应用" in case_status_label("redacted", stale=True)

