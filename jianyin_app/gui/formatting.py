"""Pure formatting helpers used by the Tkinter views."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ..model.labels import category_display, source_display
from ..redaction.schema import CandidateRule


def clip_highlights(
    highlights: Iterable[tuple[int, int, str]],
    *,
    base_offset: int,
    length: int,
) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    for start, end, tag in highlights:
        local_start = max(0, start - base_offset)
        local_end = min(length, end - base_offset)
        if local_end > local_start:
            result.append((local_start, local_end, tag))
    return result


def page_label(number: int) -> str:
    return f"第 {number} 页"


def shorten(value: str, limit: int = 80) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def candidate_origin(candidate: CandidateRule) -> str:
    sources = candidate.detection_sources or ["manual"]
    return " + ".join(source_display(source) for source in sources)


def candidate_label(candidate: CandidateRule) -> str:
    return category_display(candidate.category, candidate.subtype)


def candidate_counts(candidate: CandidateRule) -> str:
    return f"{candidate.detected_count} / {candidate.literal_count}"


def format_summary(summary: Mapping[str, Any]) -> str:
    lines: list[str] = []
    mapping = [
        ("文档数", "document_count"),
        ("识别命中", "detected_span_count"),
        ("候选规则", "candidate_rule_count"),
        ("规则命中", "applied_occurrence_count"),
        ("已应用规则", "applied_rule_count"),
        ("未命中规则", "unmatched_rule_count"),
        ("跳过重叠", "skipped_overlap_count"),
        ("字面命中", "literal_occurrence_count"),
    ]
    for label, key in mapping:
        if key in summary:
            lines.append(f"{label}：{summary[key]}")
    by_category = summary.get("by_category")
    if isinstance(by_category, Mapping) and by_category:
        lines.append("")
        lines.append("按类别：")
        for category, count in by_category.items():
            lines.append(f"  {category_display(str(category))}：{count}")
    by_source = summary.get("by_source")
    if isinstance(by_source, Mapping) and by_source:
        lines.append("")
        lines.append("按来源：")
        for source, count in by_source.items():
            lines.append(f"  {source_display(str(source))}：{count}")
    return "\n".join(lines) if lines else "暂无摘要。"


def format_paths(paths: Sequence[object], limit: int = 8) -> str:
    values = [str(path) for path in paths]
    if not values:
        return "没有导出文件。"
    lines = values[:limit]
    if len(values) > limit:
        lines.append(f"……以及另外 {len(values) - limit} 个文件")
    return "\n".join(lines)


def case_status_label(status: str | None, *, stale: bool = False) -> str:
    if stale:
        return "规则已修改，待重新应用"
    return {
        "new": "新建",
        "imported": "已导入",
        "analyzed": "已分析",
        "redacted": "已脱敏",
        "restored": "已还原",
    }.get(str(status or ""), "未知状态")


def document_status(document: Mapping[str, Any]) -> str:
    if document.get("restored_path"):
        return "已还原"
    if document.get("redacted_path"):
        return "已脱敏"
    return "已导入"
