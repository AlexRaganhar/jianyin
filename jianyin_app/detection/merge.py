"""Canonical detection merging with page-marker protection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..errors import ModelOutputError
from .base import Detection, DetectionBatch

PAGE_MARKER_RE = re.compile(r"<!--\s*PDF page\s+\d+\s*-->", re.IGNORECASE)
_ANY_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def protected_ranges(text: str, *, all_comments: bool = False) -> list[tuple[int, int]]:
    pattern = _ANY_HTML_COMMENT_RE if all_comments else PAGE_MARKER_RE
    return [(match.start(), match.end()) for match in pattern.finditer(text)]


def overlaps_any(start: int, end: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(start < range_end and end > range_start for range_start, range_end in ranges)


@dataclass(frozen=True)
class CanonicalResult:
    detections: tuple[Detection, ...]
    skipped_overlap: int
    skipped_protected: int


def _merged_source(sources: Sequence[str]) -> str:
    parts: list[str] = []
    for source in sources:
        for piece in source.split("+"):
            if piece and piece not in parts:
                parts.append(piece)
    return "+".join(parts)


def _merge_same_range(items: Sequence[Detection]) -> Detection:
    ordered = sorted(items, key=lambda item: (-item.priority, item.source, item.category))
    winner = ordered[0]
    subtype_values = {item.subtype for item in items}
    subtype = winner.subtype if len(subtype_values) == 1 else None
    return Detection(
        category=winner.category,
        start=winner.start,
        end=winner.end,
        text=winner.text,
        source=_merged_source([item.source for item in items]),
        subtype=subtype,
        priority=max(item.priority for item in items),
    )


_PRECISE_RULE_SUBTYPES = {"cn_id", "cn_mobile", "cn_bank_card"}


def _combine(category: str, text: str, first: Detection, second: Detection, winner: Detection) -> Detection:
    return Detection(
        category=category,
        start=winner.start,
        end=winner.end,
        text=text[winner.start : winner.end],
        source=_merged_source([first.source, second.source]),
        subtype=winner.subtype,
        priority=max(first.priority, second.priority),
    )


def _pick_overlap(category: str, text: str, first: Detection, second: Detection) -> Detection:
    first_contains = first.start <= second.start and first.end >= second.end
    second_contains = second.start <= first.start and second.end >= first.end
    if second_contains and not first_contains and first.subtype in _PRECISE_RULE_SUBTYPES:
        return _combine(category, text, first, second, first)
    if first_contains and not second_contains and second.subtype in _PRECISE_RULE_SUBTYPES:
        return _combine(category, text, first, second, second)
    if second_contains and not first_contains and second.subtype == "cn_name":
        return _combine(category, text, first, second, second)
    if first_contains and not second_contains and first.subtype == "cn_name":
        return _combine(category, text, first, second, first)
    first_key = (first.priority, first.end - first.start)
    second_key = (second.priority, second.end - second.start)
    winner = first if first_key >= second_key else second
    return _combine(category, text, first, second, winner)


def _merge_overlapping_by_category(text: str, detections: Sequence[Detection]) -> list[Detection]:
    """Pick the best same-category span before cross-category priority.

    The model sometimes emits a one-character Chinese surname while the local
    rule detector emits the full name; conversely, the model may include a
    leading label (for example ``身份证号``) around a precise ID rule.  This
    selection step prefers the precise rule subtype for IDs/phone/cards and the
    full name rule for Chinese names, without unioning unrelated text.
    """
    by_category: dict[str, list[Detection]] = {}
    for detection in detections:
        by_category.setdefault(detection.category, []).append(detection)
    merged: list[Detection] = []
    for category, items in by_category.items():
        ordered = sorted(items, key=lambda item: (item.start, -item.end, -item.priority))
        current: Detection | None = None
        for item in ordered:
            if current is None:
                current = item
                continue
            if item.start < current.end:
                current = _pick_overlap(category, text, current, item)
            else:
                merged.append(current)
                current = item
        if current is not None:
            merged.append(current)
    return merged


def canonicalize(text: str, detections: Sequence[Detection]) -> CanonicalResult:
    """Validate offsets, protect page markers, and keep a deterministic span set."""
    protected = protected_ranges(text)
    candidates: list[Detection] = []
    skipped_protected = 0
    for detection in detections:
        if not detection.category:
            raise ModelOutputError("检测结果缺少类别。")
        if detection.start < 0 or detection.end <= detection.start or detection.end > len(text):
            raise ModelOutputError("检测结果超出原文边界。")
        if detection.text != text[detection.start : detection.end]:
            raise ModelOutputError("检测文本与原文偏移不一致，已拒绝写入可能错位的结果。")
        if overlaps_any(detection.start, detection.end, protected):
            skipped_protected += 1
            continue
        candidates.append(detection)

    by_range: dict[tuple[int, int], list[Detection]] = {}
    for detection in candidates:
        by_range.setdefault((detection.start, detection.end), []).append(detection)

    exact: list[Detection] = []
    for items in by_range.values():
        if len(items) == 1:
            exact.append(items[0])
            continue
        same_category: dict[str, list[Detection]] = {}
        for item in items:
            same_category.setdefault(item.category, []).append(item)
        for category_items in same_category.values():
            exact.append(_merge_same_range(category_items))

    merged = _merge_overlapping_by_category(text, exact)
    ordered = sorted(
        merged,
        key=lambda item: (item.start, -item.priority, -(item.end - item.start), item.source, item.category),
    )
    accepted: list[Detection] = []
    skipped_overlap = 0
    last_end = 0
    for detection in ordered:
        if detection.start < last_end:
            skipped_overlap += 1
            continue
        accepted.append(detection)
        last_end = detection.end
    return CanonicalResult(
        detections=tuple(accepted),
        skipped_overlap=skipped_overlap,
        skipped_protected=skipped_protected,
    )


def merge_batches(batches: Sequence[DetectionBatch]) -> DetectionBatch:
    if not batches:
        raise ModelOutputError("没有可合并的检测结果。")
    text = batches[0].text
    if any(batch.text != text for batch in batches):
        raise ModelOutputError("检测结果对应的原文不一致。")
    warnings: list[str] = []
    stats: dict[str, object] = {}
    detections: list[Detection] = []
    for batch in batches:
        detections.extend(batch.detections)
        warnings.extend(batch.warnings)
        for key, value in batch.stats.items():
            stats[key] = value
    canonical = canonicalize(text, detections)
    stats["canonical_span_count"] = len(canonical.detections)
    stats["skipped_overlap"] = canonical.skipped_overlap
    stats["skipped_protected"] = canonical.skipped_protected
    return DetectionBatch(
        text=text,
        detections=canonical.detections,
        warnings=tuple(dict.fromkeys(warnings)),
        stats=stats,
    )
