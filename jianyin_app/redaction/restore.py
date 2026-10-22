"""Safe offset-verified restoration from a reviewed mapping."""

from __future__ import annotations

from typing import Any, Sequence
from typing import Mapping as TypingMapping

from ..errors import RestoreError
from .schema import DocumentText
from .schema import Mapping as CaseMapping


def restore_documents(
    documents: Sequence[DocumentText],
    mapping_payload: TypingMapping[str, Any],
) -> dict[str, str]:
    """Restore every document, refusing the whole job on any offset mismatch."""
    mapping = CaseMapping.from_dict(mapping_payload)
    if not documents:
        raise RestoreError("没有可还原的文档。")
    document_ids = {document.id for document in documents}
    if len(document_ids) != len(documents):
        raise RestoreError("待还原文档的 id 不唯一。")
    mapping_document_ids = {document.id for document in mapping.documents}
    if mapping.scope == "file" and len(documents) != 1:
        raise RestoreError("单文件映射只能还原一个文档。")
    if not document_ids.issubset(mapping_document_ids):
        raise RestoreError("映射不包含当前全部文档，无法安全还原。")

    result: dict[str, str] = {}
    for document in documents:
        changes = []
        for record in mapping.mappings:
            for occurrence in record.occurrences:
                if occurrence.document_id != document.id:
                    continue
                if occurrence.redacted_end > len(document.text):
                    raise RestoreError("映射偏移超出脱敏文本范围，无法安全还原。")
                changes.append((occurrence.redacted_start, occurrence.redacted_end, record.source, record.target))
        changes.sort(key=lambda item: item[0])
        _validate_changes(document.text, changes)

        parts: list[str] = []
        cursor = 0
        for start, end, source, _target in changes:
            parts.append(document.text[cursor:start])
            parts.append(source)
            cursor = end
        parts.append(document.text[cursor:])
        result[document.id] = "".join(parts)
    return result


def _validate_changes(text: str, changes: Sequence[tuple[int, int, str, str]]) -> None:
    previous_end = 0
    for start, end, source, target in changes:
        if start < 0 or end <= start or end > len(text):
            raise RestoreError("映射偏移无效，无法安全还原。")
        if start < previous_end:
            raise RestoreError("映射偏移发生重叠，无法安全还原。")
        if text[start:end] != target:
            raise RestoreError(
                "脱敏文本已被手工改动，无法按映射安全还原；未写入还原文件。"
            )
        if not source:
            raise RestoreError("映射缺少原始值，无法安全还原。")
        previous_end = end
