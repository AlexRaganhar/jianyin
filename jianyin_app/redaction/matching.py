"""Literal and boundary-aware rule matching."""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from ..detection.merge import protected_ranges
from ..errors import PolicyError
from .schema import MATCH_MODES, CandidateRule, DocumentText

_ASCII_WORD_RE = re.compile(r"^[A-Za-z0-9_]+$")


def resolve_match_mode(source: str, requested: str = "auto") -> str:
    if requested not in MATCH_MODES:
        raise PolicyError(f"不支持的匹配模式：{requested!r}")
    if requested != "auto":
        return requested
    if source.isdigit():
        return "digit_boundary"
    if _ASCII_WORD_RE.fullmatch(source):
        return "ascii_word"
    return "literal"


def find_occurrences(
    text: str,
    source: str,
    match_mode: str = "auto",
    *,
    protected: Sequence[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    if not source:
        return []
    mode = resolve_match_mode(source, match_mode)
    ranges = protected if protected is not None else protected_ranges(text)
    if mode == "literal":
        candidates: list[tuple[int, int]] = []
        start = 0
        while True:
            index = text.find(source, start)
            if index < 0:
                break
            candidates.append((index, index + len(source)))
            start = index + 1
    else:
        escaped = re.escape(source)
        if mode == "ascii_word":
            pattern = re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])")
        else:
            pattern = re.compile(rf"(?<!\d){escaped}(?!\d)")
        candidates = [(match.start(), match.end()) for match in pattern.finditer(text)]

    accepted: list[tuple[int, int]] = []
    for start, end in candidates:
        if any(start < range_end and end > range_start for range_start, range_end in ranges):
            continue
        accepted.append((start, end))
    return accepted


def candidate_match_mode(candidate: CandidateRule) -> str:
    if candidate.match_mode != "auto":
        return candidate.match_mode
    if candidate.subtype in {"cn_id", "cn_mobile", "cn_bank_card"}:
        return "digit_boundary"
    return resolve_match_mode(candidate.source, "auto")


def candidate_priority(candidate: CandidateRule) -> int:
    if candidate.is_manual:
        return 100
    if candidate.subtype in {"cn_id", "cn_mobile", "cn_bank_card"}:
        return 80
    if candidate.subtype in {"cn_name", "cn_landline", "cn_date", "cn_address"}:
        return 40
    if any(source.startswith("rule:") for source in candidate.detection_sources):
        return max(40, 50)
    if any(source == "model" for source in candidate.detection_sources):
        return 60
    return 50


def count_literal_occurrences(
    documents: Iterable[DocumentText],
    source: str,
    match_mode: str = "auto",
) -> int:
    total = 0
    for document in documents:
        total += len(find_occurrences(document.text, source, match_mode))
    return total
