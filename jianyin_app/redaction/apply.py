"""Apply reviewed candidate rules and build the final reversible mapping."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..detection.merge import protected_ranges
from ..errors import DraftError
from .matching import (
    candidate_match_mode,
    candidate_priority,
    find_occurrences,
)
from .schema import (
    CandidateRule,
    DocumentText,
    Draft,
    MappingDocument,
    MappingOccurrence,
    MappingRecord,
    utc_now,
)
from .schema import (
    Mapping as CaseMapping,
)


@dataclass
class Application:
    documents: dict[str, str]
    mapping: dict[str, Any]
    summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Span:
    document_id: str
    start: int
    end: int
    candidate: CandidateRule
    priority: int


def _validate_candidate(candidate: CandidateRule) -> None:
    if not candidate.source:
        raise DraftError("候选规则缺少原文。")
    if not candidate.target:
        raise DraftError("候选规则缺少替换值；请先在规则清单中补全。")
    if "\n" in candidate.target or "\r" in candidate.target:
        raise DraftError("替换值不能包含换行。")
    if candidate.target == candidate.source:
        raise DraftError("替换值不能与原文完全相同。")
    if candidate.target_edited and candidate.source in candidate.target:
        raise DraftError("手工替换值不能包含完整的原文值。")


def _candidate_spans(
    documents: Sequence[DocumentText],
    candidate: CandidateRule,
) -> list[_Span]:
    priority = candidate_priority(candidate)
    mode = candidate_match_mode(candidate)
    result: list[_Span] = []
    seen: set[tuple[str, int, int]] = set()
    for document in documents:
        if candidate.apply_all:
            occurrences = find_occurrences(document.text, candidate.source, mode)
        else:
            occurrences = [
                (item.start, item.end)
                for item in candidate.occurrences
                if item.document_id == document.id
            ]
        for start, end in occurrences:
            if not (0 <= start < end <= len(document.text)):
                continue
            if document.text[start:end] != candidate.source:
                continue
            if any(
                start < protected_end and end > protected_start
                for protected_start, protected_end in protected_ranges(document.text)
            ):
                continue
            key = (document.id, start, end)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                _Span(
                    document_id=document.id,
                    start=start,
                    end=end,
                    candidate=candidate,
                    priority=priority,
                )
            )
    return result


def _resolve_spans(spans: Sequence[_Span]) -> tuple[list[_Span], int]:
    ordered = sorted(
        spans,
        key=lambda item: (
            item.document_id,
            item.start,
            -item.priority,
            -(item.end - item.start),
            item.candidate.id,
        ),
    )
    accepted: list[_Span] = []
    skipped_overlap = 0
    last_end = 0
    current_document: str | None = None
    for span in ordered:
        if span.document_id != current_document:
            current_document = span.document_id
            last_end = 0
        if span.start < last_end:
            skipped_overlap += 1
            continue
        accepted.append(span)
        last_end = span.end
    return accepted, skipped_overlap


def apply_draft(
    documents: Sequence[DocumentText],
    draft: Draft,
    *,
    document_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    redacted_md_paths: Mapping[str, str] | None = None,
    redacted_docx_paths: Mapping[str, str] | None = None,
) -> Application:
    """Apply all enabled candidates, returning new texts and a mapping payload."""
    if not documents:
        raise DraftError("没有可应用的文档。")
    if len({document.id for document in documents}) != len(documents):
        raise DraftError("文档 id 不唯一。")
    if draft.scope == "file" and len(documents) != 1:
        raise DraftError("单文件草稿只能应用于一个文档。")

    warnings: list[str] = []
    spans: list[_Span] = []
    for candidate in draft.candidates:
        if not candidate.enabled:
            continue
        _validate_candidate(candidate)
        spans.extend(_candidate_spans(documents, candidate))
    accepted, skipped_overlap = _resolve_spans(spans)

    by_document: dict[str, list[_Span]] = {document.id: [] for document in documents}
    for span in accepted:
        by_document[span.document_id].append(span)

    texts: dict[str, str] = {}
    records: dict[int, MappingRecord] = {}
    by_category: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    for document in documents:
        document_spans = sorted(by_document[document.id], key=lambda item: item.start)
        parts: list[str] = []
        cursor = 0
        redacted_cursor = 0
        for span in document_spans:
            leading = document.text[cursor : span.start]
            parts.append(leading)
            redacted_cursor += len(leading)
            candidate = span.candidate
            record = records.get(candidate.id)
            if record is None:
                record = MappingRecord(
                    id=candidate.id,
                    category=candidate.category,
                    subtype=candidate.subtype,
                    source=candidate.source,
                    target=candidate.target,
                    source_kind="+".join(candidate.detection_sources) or "manual",
                    rule_id=candidate.id,
                    occurrences=[],
                )
                records[candidate.id] = record
            record.occurrences.append(
                MappingOccurrence(
                    document_id=document.id,
                    source_start=span.start,
                    source_end=span.end,
                    redacted_start=redacted_cursor,
                    redacted_end=redacted_cursor + len(candidate.target),
                )
            )
            parts.append(candidate.target)
            redacted_cursor += len(candidate.target)
            cursor = span.end
            by_category[candidate.category] += 1
            by_source[record.source_kind] += 1
        parts.append(document.text[cursor:])
        texts[document.id] = "".join(parts)

    metadata_by_id = dict(document_metadata or {})
    mapping_documents: list[MappingDocument] = []
    for document in documents:
        metadata = dict(document.metadata())
        metadata.update(metadata_by_id.get(document.id, {}))
        mapping_documents.append(
            MappingDocument(
                id=document.id,
                source_name=str(metadata.get("source_name", document.name)),
                display_name=str(metadata.get("display_name", document.name)),
                source_type=str(metadata.get("source_type", document.source_type)),
                extraction_method=str(metadata.get("extraction_method", document.extraction_method)),
                page_count=int(metadata.get("page_count", document.page_count)),
                redacted_md=(redacted_md_paths or {}).get(document.id),
                redacted_docx=(redacted_docx_paths or {}).get(document.id),
            )
        )

    applied_rule_count = len(records)
    enabled_count = sum(1 for candidate in draft.candidates if candidate.enabled)
    summary = {
        "document_count": len(documents),
        "rule_count": len(draft.candidates),
        "enabled_rule_count": enabled_count,
        "applied_rule_count": applied_rule_count,
        "unmatched_rule_count": max(enabled_count - applied_rule_count, 0),
        "detected_span_count": int(draft.summary.get("detected_span_count", 0)),
        "applied_occurrence_count": len(accepted),
        "skipped_overlap_count": skipped_overlap,
        "by_category": dict(sorted(by_category.items())),
        "by_source": dict(sorted(by_source.items())),
    }
    if skipped_overlap:
        warnings.append(f"有 {skipped_overlap} 处规则命中因重叠被跳过。")

    mapping = CaseMapping(
        scope=draft.scope,
        documents=mapping_documents,
        mappings=sorted(records.values(), key=lambda record: record.id),
        model=draft.model,
        detection=draft.detection,
        rules=draft.rules,
        summary=summary,
        case=draft.case,
        source_name=draft.source_name,
        draft_sha256=draft.digest,
        created_at=utc_now(),
    )
    return Application(
        documents=texts,
        mapping=mapping.to_dict(),
        summary=summary,
        warnings=warnings,
    )
