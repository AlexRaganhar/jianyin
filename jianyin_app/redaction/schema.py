"""Draft and mapping data contracts.

All offsets are Python string indices (Unicode code points).  Draft and final
mapping files contain original sensitive values by design; they are local-only
artifacts and must never be written to logs or bundled with exported documents.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from typing import Mapping as TypingMapping

from ..errors import DraftError, RestoreError

TOOL_NAME = "jianyin"
PRODUCT_NAME = "笺隐"
DRAFT_SCHEMA_VERSION = 1
MAPPING_SCHEMA_VERSION = 3
MATCH_MODES = {"auto", "literal", "ascii_word", "digit_boundary"}
SCOPES = {"case", "file"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_payload(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _require_str(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        raise DraftError(f"{field_name} 必须是非空字符串。")
    return value


def _require_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DraftError(f"{field_name} 必须是不小于 {minimum} 的整数。")
    return value


@dataclass(frozen=True)
class DocumentText:
    """One imported document used by the analysis/apply core."""

    id: str
    name: str
    text: str
    source_type: str = "text"
    extraction_method: str = "text"
    page_count: int = 1

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_name": self.name,
            "display_name": self.name,
            "source_type": self.source_type,
            "extraction_method": self.extraction_method,
            "page_count": self.page_count,
        }


@dataclass
class Occurrence:
    document_id: str
    start: int
    end: int
    source: str = "model"

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "start": self.start,
            "end": self.end,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "Occurrence":
        if not isinstance(payload, MappingABC):
            raise DraftError("occurrence 必须是 JSON 对象。")
        return cls(
            document_id=_require_str(payload.get("document_id"), "occurrence.document_id"),
            start=_require_int(payload.get("start"), "occurrence.start"),
            end=_require_int(payload.get("end"), "occurrence.end"),
            source=str(payload.get("source", "model")),
        )


@dataclass
class CandidateRule:
    id: int
    category: str
    source: str
    target: str
    subtype: str | None = None
    enabled: bool = True
    target_edited: bool = False
    apply_all: bool = True
    match_mode: str = "auto"
    detection_sources: list[str] = field(default_factory=list)
    detected_count: int = 0
    literal_count: int = 0
    note: str = ""
    occurrences: list[Occurrence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "subtype": self.subtype,
            "source": self.source,
            "target": self.target,
            "enabled": self.enabled,
            "target_edited": self.target_edited,
            "apply_all": self.apply_all,
            "match_mode": self.match_mode,
            "detection_sources": list(self.detection_sources),
            "detected_count": self.detected_count,
            "literal_count": self.literal_count,
            "note": self.note,
            "occurrences": [occurrence.to_dict() for occurrence in self.occurrences],
        }

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "CandidateRule":
        if not isinstance(payload, MappingABC):
            raise DraftError("candidate 必须是 JSON 对象。")
        match_mode = str(payload.get("match_mode", "auto"))
        if match_mode not in MATCH_MODES:
            raise DraftError(f"不支持的匹配模式：{match_mode!r}")
        raw_occurrences = payload.get("occurrences", [])
        if not isinstance(raw_occurrences, list):
            raise DraftError("candidate.occurrences 必须是数组。")
        raw_sources = payload.get("detection_sources", [])
        if not isinstance(raw_sources, list):
            raise DraftError("candidate.detection_sources 必须是数组。")
        return cls(
            id=_require_int(payload.get("id"), "candidate.id", minimum=1),
            category=_require_str(payload.get("category"), "candidate.category"),
            subtype=str(payload["subtype"]) if payload.get("subtype") is not None else None,
            source=_require_str(payload.get("source"), "candidate.source"),
            target=str(payload.get("target", "")),
            enabled=bool(payload.get("enabled", True)),
            target_edited=bool(payload.get("target_edited", False)),
            apply_all=bool(payload.get("apply_all", True)),
            match_mode=match_mode,
            detection_sources=[str(item) for item in raw_sources],
            detected_count=int(payload.get("detected_count", 0)),
            literal_count=int(payload.get("literal_count", 0)),
            note=str(payload.get("note", "")),
            occurrences=[Occurrence.from_dict(item) for item in raw_occurrences],
        )

    @property
    def is_manual(self) -> bool:
        return "manual" in self.detection_sources


@dataclass
class Draft:
    scope: str
    candidates: list[CandidateRule]
    model: TypingMapping[str, Any] = field(default_factory=dict)
    detection: TypingMapping[str, Any] = field(default_factory=dict)
    rules: TypingMapping[str, Any] = field(default_factory=dict)
    summary: TypingMapping[str, Any] = field(default_factory=dict)
    case: TypingMapping[str, Any] | None = None
    source_name: str | None = None
    created_at: str = field(default_factory=utc_now)
    schema_version: int = DRAFT_SCHEMA_VERSION
    tool: str = TOOL_NAME

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise DraftError(f"不支持的草稿 scope：{self.scope!r}")
        ids = [candidate.id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise DraftError("规则草稿中存在重复的 candidate id。")
        for candidate in self.candidates:
            if not candidate.category or not candidate.source:
                raise DraftError("规则草稿中存在缺少类别或原文的候选规则。")
            if candidate.match_mode not in MATCH_MODES:
                raise DraftError("规则草稿中存在不支持的匹配模式。")
            if candidate.target and "\n" in candidate.target:
                raise DraftError("替换值不能包含换行。")

    @property
    def digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "model": self.model,
            "detection": self.detection,
            "rules": self.rules,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }
        return sha256_payload(payload)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "tool": self.tool,
            "product": PRODUCT_NAME,
            "sensitive": True,
            "local_only": True,
            "created_at": self.created_at,
            "model": dict(self.model),
            "detection": dict(self.detection),
            "rules": dict(self.rules),
            "summary": dict(self.summary),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "draft_sha256": self.digest,
        }
        if self.case is not None:
            payload["case"] = dict(self.case)
        if self.source_name is not None:
            payload["source_name"] = self.source_name
        return payload

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "Draft":
        if not isinstance(payload, MappingABC):
            raise DraftError("规则草稿必须是 JSON 对象。")
        scope = str(payload.get("scope", "case"))
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list):
            raise DraftError("规则草稿缺少 candidates 数组。")
        case = payload.get("case")
        return cls(
            scope=scope,
            candidates=[CandidateRule.from_dict(item) for item in raw_candidates],
            model=dict(payload.get("model") or {}),
            detection=dict(payload.get("detection") or {}),
            rules=dict(payload.get("rules") or {}),
            summary=dict(payload.get("summary") or {}),
            case=dict(case) if isinstance(case, MappingABC) else None,
            source_name=str(payload["source_name"]) if payload.get("source_name") else None,
            created_at=str(payload.get("created_at") or utc_now()),
            schema_version=int(payload.get("schema_version", DRAFT_SCHEMA_VERSION)),
            tool=str(payload.get("tool", TOOL_NAME)),
        )


@dataclass
class MappingOccurrence:
    document_id: str
    source_start: int
    source_end: int
    redacted_start: int
    redacted_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "redacted_start": self.redacted_start,
            "redacted_end": self.redacted_end,
        }

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "MappingOccurrence":
        if not isinstance(payload, MappingABC):
            raise RestoreError("映射 occurrence 格式无效。")
        return cls(
            document_id=str(payload.get("document_id", "")),
            source_start=_as_mapping_int(payload.get("source_start"), "source_start"),
            source_end=_as_mapping_int(payload.get("source_end"), "source_end"),
            redacted_start=_as_mapping_int(payload.get("redacted_start"), "redacted_start"),
            redacted_end=_as_mapping_int(payload.get("redacted_end"), "redacted_end"),
        )


@dataclass
class MappingRecord:
    id: int
    category: str
    source: str
    target: str
    subtype: str | None = None
    source_kind: str = "model"
    rule_id: int | None = None
    occurrences: list[MappingOccurrence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "fixed",
            "category": self.category,
            "subtype": self.subtype,
            "source": self.source,
            "target": self.target,
            "source_kind": self.source_kind,
            "rule_id": self.rule_id,
            "occurrences": [occurrence.to_dict() for occurrence in self.occurrences],
        }

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "MappingRecord":
        if not isinstance(payload, MappingABC):
            raise RestoreError("映射记录格式无效。")
        raw_occurrences = payload.get("occurrences")
        if not isinstance(raw_occurrences, list):
            raise RestoreError("映射记录缺少 occurrences。")
        rule_id = payload.get("rule_id")
        return cls(
            id=_as_mapping_int(payload.get("id"), "id"),
            category=str(payload.get("category", "")),
            subtype=str(payload["subtype"]) if payload.get("subtype") is not None else None,
            source=str(payload.get("source", "")),
            target=str(payload.get("target", "")),
            source_kind=str(payload.get("source_kind", "model")),
            rule_id=_as_mapping_int(rule_id, "rule_id") if rule_id is not None else None,
            occurrences=[MappingOccurrence.from_dict(item) for item in raw_occurrences],
        )


@dataclass
class MappingDocument:
    id: str
    source_name: str
    display_name: str
    source_type: str = "text"
    extraction_method: str = "text"
    page_count: int = 1
    redacted_md: str | None = None
    redacted_docx: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "extraction_method": self.extraction_method,
            "page_count": self.page_count,
            "redacted_md": self.redacted_md,
            "redacted_docx": self.redacted_docx,
        }

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "MappingDocument":
        if not isinstance(payload, MappingABC):
            raise RestoreError("映射文档格式无效。")
        return cls(
            id=str(payload.get("id", "")),
            source_name=str(payload.get("source_name", "")),
            display_name=str(payload.get("display_name", payload.get("source_name", ""))),
            source_type=str(payload.get("source_type", "text")),
            extraction_method=str(payload.get("extraction_method", "text")),
            page_count=int(payload.get("page_count", 1)),
            redacted_md=str(payload["redacted_md"]) if payload.get("redacted_md") else None,
            redacted_docx=str(payload["redacted_docx"]) if payload.get("redacted_docx") else None,
        )


def _as_mapping_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RestoreError(f"映射字段 {field_name} 无效。")
    return value


@dataclass
class Mapping:
    scope: str
    documents: list[MappingDocument]
    mappings: list[MappingRecord]
    model: TypingMapping[str, Any] = field(default_factory=dict)
    detection: TypingMapping[str, Any] = field(default_factory=dict)
    rules: TypingMapping[str, Any] = field(default_factory=dict)
    summary: TypingMapping[str, Any] = field(default_factory=dict)
    case: TypingMapping[str, Any] | None = None
    source_name: str | None = None
    draft_sha256: str | None = None
    created_at: str = field(default_factory=utc_now)
    schema_version: int = MAPPING_SCHEMA_VERSION
    tool: str = TOOL_NAME

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise RestoreError(f"不支持的映射 scope：{self.scope!r}")
        if not self.documents:
            raise RestoreError("映射必须至少包含一个文档。")
        document_ids = [document.id for document in self.documents]
        if any(not document_id for document_id in document_ids):
            raise RestoreError("映射文档缺少 id。")
        if len(document_ids) != len(set(document_ids)):
            raise RestoreError("映射中存在重复的文档 id。")
        known_documents = set(document_ids)
        seen_occurrences: dict[str, list[tuple[int, int]]] = {document_id: [] for document_id in document_ids}
        for record in self.mappings:
            if not record.source or not record.target:
                raise RestoreError("映射记录缺少原文或替换值。")
            for occurrence in record.occurrences:
                if occurrence.document_id not in known_documents:
                    raise RestoreError("映射 occurrence 指向不存在的文档。")
                if occurrence.source_end <= occurrence.source_start or occurrence.redacted_end <= occurrence.redacted_start:
                    raise RestoreError("映射 occurrence 的偏移无效。")
                seen_occurrences[occurrence.document_id].append(
                    (occurrence.redacted_start, occurrence.redacted_end)
                )
        for _document_id, ranges in seen_occurrences.items():
            ordered = sorted(ranges)
            for (_start, end), (next_start, _next_end) in zip(ordered, ordered[1:], strict=False):
                if next_start < end:
                    raise RestoreError("映射 occurrence 在文档内发生重叠。")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "tool": self.tool,
            "product": PRODUCT_NAME,
            "sensitive": True,
            "local_only": True,
            "created_at": self.created_at,
            "model": dict(self.model),
            "detection": dict(self.detection),
            "rules": dict(self.rules),
            "draft_sha256": self.draft_sha256,
            "summary": dict(self.summary),
            "documents": [document.to_dict() for document in self.documents],
            "mappings": [record.to_dict() for record in self.mappings],
        }
        if self.case is not None:
            payload["case"] = dict(self.case)
        if self.source_name is not None:
            payload["source_name"] = self.source_name
        return payload

    @classmethod
    def from_dict(cls, payload: TypingMapping[str, Any]) -> "Mapping":
        if not isinstance(payload, MappingABC):
            raise RestoreError("映射文件必须是 JSON 对象。")
        if int(payload.get("schema_version", 0)) != MAPPING_SCHEMA_VERSION:
            raise RestoreError("映射版本不受支持；旧版映射请使用旧工具还原。")
        raw_documents = payload.get("documents")
        raw_mappings = payload.get("mappings")
        if not isinstance(raw_documents, list) or not isinstance(raw_mappings, list):
            raise RestoreError("映射文件缺少 documents 或 mappings。")
        case = payload.get("case")
        return cls(
            scope=str(payload.get("scope", "")),
            documents=[MappingDocument.from_dict(item) for item in raw_documents],
            mappings=[MappingRecord.from_dict(item) for item in raw_mappings],
            model=dict(payload.get("model") or {}),
            detection=dict(payload.get("detection") or {}),
            rules=dict(payload.get("rules") or {}),
            summary=dict(payload.get("summary") or {}),
            case=dict(case) if isinstance(case, MappingABC) else None,
            source_name=str(payload["source_name"]) if payload.get("source_name") else None,
            draft_sha256=str(payload["draft_sha256"]) if payload.get("draft_sha256") else None,
            created_at=str(payload.get("created_at") or utc_now()),
            schema_version=MAPPING_SCHEMA_VERSION,
            tool=str(payload.get("tool", TOOL_NAME)),
        )
