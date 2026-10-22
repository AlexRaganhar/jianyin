"""Analyze documents into a reviewable, editable rule draft."""

from __future__ import annotations

from collections import Counter, OrderedDict
from typing import Any, Mapping, Sequence

from ..config import DetectionOptions
from ..detection.base import (
    CancelCheck,
    DetectionBatch,
    Detector,
    ProgressCallback,
    check_cancelled,
    emit_progress,
)
from ..detection.merge import canonicalize
from ..errors import DraftError
from .matching import count_literal_occurrences
from .policy import RuleSet
from .schema import CandidateRule, DocumentText, Draft, Occurrence, utc_now
from .targets import TargetFactory


def _document_order(documents: Sequence[DocumentText]) -> list[DocumentText]:
    ids = [document.id for document in documents]
    if len(ids) != len(set(ids)):
        raise DraftError("待分析文档的 id 不唯一。")
    return list(documents)


def _new_candidate(
    *,
    candidate_id: int,
    category: str,
    subtype: str | None,
    source: str,
    target: str,
    detection_sources: list[str],
    enabled: bool = True,
    target_edited: bool = False,
    apply_all: bool = True,
    match_mode: str = "auto",
    note: str = "",
    occurrences: list[Occurrence] | None = None,
    detected_count: int = 0,
) -> CandidateRule:
    return CandidateRule(
        id=candidate_id,
        category=category,
        subtype=subtype,
        source=source,
        target=target,
        enabled=enabled,
        target_edited=target_edited,
        apply_all=apply_all,
        match_mode=match_mode,
        detection_sources=detection_sources,
        detected_count=detected_count,
        literal_count=0,
        note=note,
        occurrences=occurrences or [],
    )


def analyze_documents(
    documents: Sequence[DocumentText],
    detector: Detector,
    rules: RuleSet,
    detection_options: DetectionOptions | None = None,
    *,
    scope: str = "case",
    case: Mapping[str, Any] | None = None,
    source_name: str | None = None,
    existing_draft: Draft | None = None,
    preserve_existing: bool = True,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> Draft:
    """Run detection over all documents and group results into candidate rules."""
    ordered_documents = _document_order(documents)
    if not ordered_documents:
        raise DraftError("请先导入至少一个文档。")
    if scope == "case" and not case:
        raise DraftError("案件级分析缺少案件信息。")
    if scope not in {"case", "file"}:
        raise DraftError(f"不支持的分析范围：{scope!r}")

    options = detection_options or DetectionOptions()
    existing_candidates = existing_draft.candidates if (existing_draft and preserve_existing) else []
    existing_by_key = {(candidate.category, candidate.source): candidate for candidate in existing_candidates}
    factory = TargetFactory(
        rules,
        existing=[
            (candidate.category, candidate.source, candidate.target)
            for candidate in existing_candidates
            if candidate.target
        ],
    )

    grouped: OrderedDict[tuple[str, str], CandidateRule] = OrderedDict()
    warnings: list[str] = []
    stats: dict[str, Any] = {}
    detection_count = 0
    source_counts: Counter[str] = Counter()
    document_count = len(ordered_documents)

    for index, document in enumerate(ordered_documents, start=1):
        check_cancelled(cancel)
        emit_progress(
            progress,
            {
                "stage": "document_start",
                "document_index": index,
                "document_count": document_count,
                "document_id": document.id,
                "document_name": document.name,
            },
        )
        batch: DetectionBatch = detector.detect(
            document.text,
            progress=progress,
            cancel=cancel,
        )
        if batch.text != document.text:
            raise DraftError("检测结果与文档原文不一致。")
        canonical = canonicalize(document.text, batch.detections)
        detections = sorted(canonical.detections, key=lambda item: (item.start, item.end, item.category))
        detection_count += len(detections)
        warnings.extend(batch.warnings)
        for key, value in batch.stats.items():
            stats[key] = value

        for detection in detections:
            check_cancelled(cancel)
            if not detection.text:
                continue
            key = (detection.category, detection.text)
            existing = existing_by_key.get(key)
            candidate = grouped.get(key)
            if candidate is None:
                if existing is not None:
                    target = existing.target or factory.target_for(
                        detection.category, detection.text, detection.subtype
                    )
                    candidate = _new_candidate(
                        candidate_id=0,
                        category=detection.category,
                        subtype=detection.subtype or existing.subtype,
                        source=detection.text,
                        target=target,
                        detection_sources=list(existing.detection_sources),
                        enabled=existing.enabled,
                        target_edited=existing.target_edited,
                        apply_all=existing.apply_all,
                        match_mode=existing.match_mode,
                        note=existing.note,
                        occurrences=list(existing.occurrences),
                        detected_count=existing.detected_count,
                    )
                else:
                    target = factory.target_for(detection.category, detection.text, detection.subtype)
                    candidate = _new_candidate(
                        candidate_id=0,
                        category=detection.category,
                        subtype=detection.subtype,
                        source=detection.text,
                        target=target,
                        detection_sources=[],
                    )
                grouped[key] = candidate
            if detection.source not in candidate.detection_sources:
                candidate.detection_sources.append(detection.source)
            candidate.occurrences.append(
                Occurrence(
                    document_id=document.id,
                    start=detection.start,
                    end=detection.end,
                    source=detection.source,
                )
            )
            candidate.detected_count += 1
            if candidate.subtype is None and detection.subtype:
                candidate.subtype = detection.subtype
            source_counts[detection.source] += 1
        emit_progress(
            progress,
            {
                "stage": "document_finished",
                "document_index": index,
                "document_count": document_count,
                "document_id": document.id,
                "detected_span_count": len(detections),
            },
        )

    if preserve_existing:
        for existing in existing_candidates:
            key = (existing.category, existing.source)
            if key in grouped:
                continue
            candidate = _new_candidate(
                candidate_id=0,
                category=existing.category,
                subtype=existing.subtype,
                source=existing.source,
                target=existing.target or factory.target_for(existing.category, existing.source),
                detection_sources=list(existing.detection_sources) or ["manual"],
                enabled=existing.enabled,
                target_edited=existing.target_edited,
                apply_all=existing.apply_all,
                match_mode=existing.match_mode,
                note=existing.note,
                occurrences=list(existing.occurrences),
                detected_count=existing.detected_count,
            )
            if "manual" not in candidate.detection_sources:
                candidate.detection_sources.append("manual")
            grouped[key] = candidate

    candidates: list[CandidateRule] = []
    for index, candidate in enumerate(grouped.values(), start=1):
        candidate.id = index
        candidate.literal_count = count_literal_occurrences(
            ordered_documents,
            candidate.source,
            candidate.match_mode,
        )
        candidates.append(candidate)

    by_category: Counter[str] = Counter()
    for candidate in candidates:
        by_category[candidate.category] += candidate.detected_count
    summary = {
        "document_count": document_count,
        "detected_span_count": detection_count,
        "candidate_rule_count": len(candidates),
        "literal_occurrence_count": sum(candidate.literal_count for candidate in candidates),
        "by_category": dict(sorted(by_category.items())),
        "by_source": dict(sorted(source_counts.items())),
    }
    draft = Draft(
        scope=scope,
        candidates=candidates,
        model=dict(detector.metadata),
        detection=options.as_dict(),
        rules=rules.metadata(),
        summary=summary,
        case=dict(case) if case else None,
        source_name=source_name,
        created_at=utc_now(),
    )
    emit_progress(
        progress,
        {
            "stage": "analysis_finished",
            "document_count": document_count,
            "candidate_rule_count": len(candidates),
            "detected_span_count": detection_count,
            "warnings": list(dict.fromkeys(warnings)),
            "stats": stats,
        },
    )
    return draft
