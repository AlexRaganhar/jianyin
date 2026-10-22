"""Case-level orchestration around the pure analysis/apply/restore core."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..config import DetectionOptions
from ..detection.base import CancelCheck, Detector, ProgressCallback, check_cancelled, emit_progress
from ..documents.docx_export import export_docx
from ..documents.markdown import safe_stem, unique_filename
from ..errors import DocumentError, DraftError, RestoreError, WorkspaceError
from ..redaction.analysis import analyze_documents
from ..redaction.apply import Application, apply_draft
from ..redaction.policy import RuleSet
from ..redaction.restore import restore_documents
from ..redaction.schema import DocumentText, Draft
from .store import CaseWorkspace


def analyze_case(
    workspace: CaseWorkspace,
    case_id: str,
    detector: Detector,
    rules: RuleSet,
    *,
    detection_options: DetectionOptions | None = None,
    preserve_existing: bool = True,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> Draft:
    case = workspace.get_case(case_id)
    documents = workspace.document_texts(case_id)
    if not documents:
        raise DraftError("请先向当前案件导入至少一个文件。")
    existing: Draft | None = None
    if preserve_existing and workspace.draft_path(case_id).is_file():
        try:
            existing = workspace.read_draft(case_id)
        except Exception:
            existing = None
    draft = analyze_documents(
        documents,
        detector,
        rules,
        detection_options,
        scope="case",
        case={"id": case_id, "name": str(case.get("name", ""))},
        existing_draft=existing,
        preserve_existing=preserve_existing,
        progress=progress,
        cancel=cancel,
    )
    workspace.write_draft(case_id, draft)
    workspace.update_case(case_id, status="analyzed", draft_sha256=draft.digest)
    return draft


def _redacted_paths(workspace: CaseWorkspace, case_id: str, documents: Sequence[DocumentText]) -> tuple[dict[str, str], dict[str, str]]:
    md_paths: dict[str, str] = {}
    docx_paths: dict[str, str] = {}
    for document in documents:
        md_paths[document.id] = workspace.relative_path(
            case_id, workspace.redacted_text_path(case_id, document.id)
        )
        docx_paths[document.id] = workspace.relative_path(
            case_id, workspace.redacted_docx_path(case_id, document.id)
        )
    return md_paths, docx_paths


def apply_case(
    workspace: CaseWorkspace,
    case_id: str,
    draft: Draft,
    *,
    export_docx_enabled: bool = True,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> Application:
    workspace.get_case(case_id)
    documents = workspace.document_texts(case_id)
    if not documents:
        raise DraftError("当前案件没有可应用的文档。")
    md_paths, docx_paths = _redacted_paths(workspace, case_id, documents)
    metadata = workspace.document_metadata(case_id)
    result = apply_draft(
        documents,
        draft,
        document_metadata=metadata,
        redacted_md_paths=md_paths,
        redacted_docx_paths=docx_paths if export_docx_enabled else None,
    )
    total = len(documents)
    for index, document in enumerate(documents, start=1):
        check_cancelled(cancel)
        emit_progress(
            progress,
            {
                "stage": "apply_document",
                "document_index": index,
                "document_count": total,
                "document_id": document.id,
            },
        )
        workspace.write_redacted_text(case_id, document.id, result.documents[document.id])
        if export_docx_enabled:
            export_docx(
                result.documents[document.id],
                workspace.redacted_docx_path(case_id, document.id),
                title=f"脱敏文本 · {document.name}",
            )
            workspace.update_document(
                case_id,
                document.id,
                redacted_docx=md_paths[document.id].replace(".md", ".docx"),
            )
    workspace.write_mapping(case_id, result.mapping)
    workspace.update_case(
        case_id,
        status="redacted",
        applied_draft_sha256=draft.digest,
        applied_at=workspace.get_case(case_id).get("applied_at"),
    )
    emit_progress(progress, {"stage": "apply_finished", "summary": result.summary})
    return result


def restore_case(
    workspace: CaseWorkspace,
    case_id: str,
    *,
    export_docx_enabled: bool = True,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> dict[str, str]:
    case = workspace.get_case(case_id)
    mapping = workspace.read_mapping(case_id)
    mapped_case = mapping.get("case")
    if not isinstance(mapped_case, Mapping) or mapped_case.get("id") != case_id:
        raise RestoreError("映射不属于当前案件，无法还原。")
    redacted_documents: list[DocumentText] = []
    for document in case["documents"]:
        document_id = str(document["id"])
        redacted_path = workspace.redacted_text_path(case_id, document_id)
        try:
            text = redacted_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise DocumentError("脱敏文本缺失，无法还原。") from error
        redacted_documents.append(
            DocumentText(
                id=document_id,
                name=str(document.get("display_name", document.get("source_name", "文档"))),
                text=text,
                source_type=str(document.get("source_type", "text")),
                extraction_method=str(document.get("extraction_method", "text")),
                page_count=int(document.get("page_count", 1)),
            )
        )
    restored = restore_documents(redacted_documents, mapping)
    total = len(redacted_documents)
    for index, document in enumerate(redacted_documents, start=1):
        check_cancelled(cancel)
        emit_progress(
            progress,
            {
                "stage": "restore_document",
                "document_index": index,
                "document_count": total,
                "document_id": document.id,
            },
        )
        workspace.write_restored_text(case_id, document.id, restored[document.id])
        if export_docx_enabled:
            export_docx(
                restored[document.id],
                workspace.restored_docx_path(case_id, document.id),
                title=f"还原文本 · {document.name}",
            )
            workspace.update_document(
                case_id,
                document.id,
                restored_docx=workspace.relative_path(
                    case_id, workspace.restored_docx_path(case_id, document.id)
                ),
            )
    workspace.update_case(case_id, status="restored")
    emit_progress(progress, {"stage": "restore_finished", "document_count": total})
    return restored


def is_mapping_stale(case: Mapping[str, Any], draft: Draft | None) -> bool:
    if draft is None:
        return True
    applied = case.get("applied_draft_sha256")
    return applied != draft.digest


def export_documents(
    workspace: CaseWorkspace,
    case_id: str,
    document_ids: Sequence[str],
    target_dir: str | Path,
    *,
    include_md: bool = True,
    include_docx: bool = True,
    include_mapping: bool = False,
) -> list[Path]:
    directory = Path(target_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    case = workspace.get_case(case_id)
    documents = {str(item["id"]): item for item in case["documents"]}
    exported: list[Path] = []
    for document_id in document_ids:
        document = documents.get(document_id)
        if document is None:
            raise WorkspaceError("选中的文档不存在。")
        redacted_path = workspace.redacted_text_path(case_id, document_id)
        if not redacted_path.is_file():
            raise DocumentError("该文档还没有脱敏结果，请先应用脱敏。")
        stem = safe_stem(str(document.get("display_name", document.get("source_name", "文档"))))
        if include_md:
            target = unique_filename(directory, f"{stem}-脱敏", ".md")
            shutil.copy2(redacted_path, target)
            exported.append(target)
        if include_docx:
            docx_path = workspace.redacted_docx_path(case_id, document_id)
            if not docx_path.is_file():
                export_docx(redacted_path.read_text(encoding="utf-8"), docx_path)
            target = unique_filename(directory, f"{stem}-脱敏", ".docx")
            shutil.copy2(docx_path, target)
            exported.append(target)
    if include_mapping:
        mapping = workspace.mapping_path(case_id)
        if mapping.is_file():
            target = unique_filename(directory, "案件脱敏映射", ".json")
            shutil.copy2(mapping, target)
            exported.append(target)
    return exported
