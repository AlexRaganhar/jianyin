"""Persistent, local-only case workspace storage."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from ..config import WorkspaceSettings
from ..detection.base import CancelCheck, ProgressCallback, check_cancelled, emit_progress
from ..documents.importers import (
    ensure_supported,
    extract_docx,
    extract_pdf_pages,
    is_scanned_pdf,
    read_text_file,
    sha256_file,
    unlock_or_copy_pdf,
)
from ..documents.markdown import page_anchored_text
from ..documents.pdf_ocr import OcrRunner, default_ocr_runner, read_ocr_pages
from ..errors import DocumentError, OperationCancelled, WorkspaceError
from ..redaction.schema import DocumentText, Draft
from .paths import (
    atomic_write_text,
    ensure_dir,
    read_json,
    relative_to,
    resolve_within,
    utc_now,
    validate_case_id,
    validate_document_id,
    write_json,
)
from .settings import load_settings, save_settings


@dataclass(frozen=True)
class ImportFailure:
    display_name: str
    code: str
    message: str


@dataclass
class ImportOutcome:
    imported: list[dict[str, Any]] = field(default_factory=list)
    failures: list[ImportFailure] = field(default_factory=list)


class CaseWorkspace:
    """Stores source files, extracted text, outputs, and one case mapping."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.cases_root = self.root / "cases"
        self.logs_root = self.root / "logs"
        self.workspace_file = self.root / "workspace.json"
        ensure_dir(self.root)
        ensure_dir(self.cases_root)
        ensure_dir(self.logs_root)
        if not self.workspace_file.is_file():
            write_json(
                self.workspace_file,
                {
                    "schema_version": 1,
                    "tool": "jianyin",
                    "product": "笺隐",
                    "created_at": utc_now(),
                    "settings": WorkspaceSettings().as_dict(),
                },
            )
        try:
            self._settings = load_settings(self.workspace_file)
        except Exception:
            self._settings = WorkspaceSettings()

    @property
    def settings(self) -> WorkspaceSettings:
        return self._settings

    def save_settings(self, settings: WorkspaceSettings) -> None:
        settings.model_config().validate()
        save_settings(self.workspace_file, settings)
        self._settings = settings

    def _case_dir(self, case_id: str) -> Path:
        return self.cases_root / validate_case_id(case_id)

    def _case_file(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "case.json"

    def _read_case(self, case_id: str) -> dict[str, Any]:
        payload = read_json(self._case_file(case_id))
        if payload.get("id") != case_id or not isinstance(payload.get("documents"), list):
            raise WorkspaceError("本地案件数据格式无效。")
        return payload

    def _write_case(self, case_id: str, payload: dict[str, Any]) -> None:
        payload["updated_at"] = utc_now()
        write_json(self._case_file(case_id), payload)

    def list_cases(self) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for case_file in sorted(self.cases_root.glob("*/case.json")):
            try:
                payload = read_json(case_file)
            except WorkspaceError:
                continue
            if isinstance(payload.get("id"), str) and isinstance(payload.get("name"), str):
                cases.append(payload)
        return sorted(cases, key=lambda item: (str(item.get("created_at", "")), str(item["name"])))

    def create_case(self, name: str) -> dict[str, Any]:
        cleaned_name = " ".join(str(name).split())
        if not cleaned_name:
            raise WorkspaceError("案件名称不能为空。")
        if len(cleaned_name) > 120:
            raise WorkspaceError("案件名称太长（最多 120 字）。")
        case_id = uuid4().hex
        case_dir = self._case_dir(case_id)
        try:
            for relative in (
                "sources",
                "extracted",
                "outputs/redacted",
                "outputs/restored",
                "rules/archive",
                "ocr",
            ):
                ensure_dir(case_dir / relative)
        except WorkspaceError:
            raise
        now = utc_now()
        payload: dict[str, Any] = {
            "schema_version": 1,
            "tool": "jianyin",
            "product": "笺隐",
            "id": case_id,
            "name": cleaned_name,
            "created_at": now,
            "updated_at": now,
            "status": "new",
            "documents": [],
            "applied_draft_sha256": None,
            "applied_at": None,
        }
        self._write_case(case_id, payload)
        return payload

    def get_case(self, case_id: str) -> dict[str, Any]:
        return self._read_case(case_id)

    def update_case(self, case_id: str, **changes: Any) -> dict[str, Any]:
        payload = self._read_case(case_id)
        payload.update(changes)
        self._write_case(case_id, payload)
        return payload

    def case_dir(self, case_id: str) -> Path:
        self._read_case(case_id)
        return self._case_dir(case_id)

    def relative_path(self, case_id: str, path: Path) -> str:
        return relative_to(self._case_dir(case_id), path)

    def resolve_case_path(self, case_id: str, relative_path: str) -> Path:
        return resolve_within(self._case_dir(case_id), relative_path)

    def add_document(self, case_id: str, document: dict[str, Any]) -> dict[str, Any]:
        document_id = document.get("id")
        if not isinstance(document_id, str):
            raise WorkspaceError("文档标识无效。")
        validate_document_id(document_id)
        payload = self._read_case(case_id)
        if any(item.get("id") == document_id for item in payload["documents"]):
            raise WorkspaceError("该文档已在当前案件中。")
        payload["documents"].append(document)
        payload["status"] = "imported"
        self._write_case(case_id, payload)
        return document

    def get_document(self, case_id: str, document_id: str) -> dict[str, Any]:
        for document in self._read_case(case_id)["documents"]:
            if document.get("id") == document_id:
                return document
        raise WorkspaceError("选中的文档不存在。")

    def update_document(self, case_id: str, document_id: str, **changes: Any) -> dict[str, Any]:
        payload = self._read_case(case_id)
        for document in payload["documents"]:
            if document.get("id") == document_id:
                document.update(changes)
                self._write_case(case_id, payload)
                return document
        raise WorkspaceError("选中的文档不存在。")

    def document_text_path(self, case_id: str, document_id: str) -> Path:
        document = self.get_document(case_id, document_id)
        text_path = document.get("text_path")
        if not isinstance(text_path, str):
            raise WorkspaceError("该文档没有导入文本。")
        return self.resolve_case_path(case_id, text_path)

    def read_document_text(self, case_id: str, document_id: str) -> str:
        try:
            return self.document_text_path(case_id, document_id).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise WorkspaceError("导入文本无法读取。") from error

    def write_imported_text(self, case_id: str, document_id: str, text: str) -> Path:
        path = self._case_dir(case_id) / "extracted" / f"{validate_document_id(document_id)}.md"
        atomic_write_text(path, text)
        return path

    def redacted_text_path(self, case_id: str, document_id: str) -> Path:
        return self._case_dir(case_id) / "outputs" / "redacted" / f"{validate_document_id(document_id)}.md"

    def restored_text_path(self, case_id: str, document_id: str) -> Path:
        return self._case_dir(case_id) / "outputs" / "restored" / f"{validate_document_id(document_id)}.md"

    def redacted_docx_path(self, case_id: str, document_id: str) -> Path:
        return self._case_dir(case_id) / "outputs" / "redacted" / f"{validate_document_id(document_id)}.docx"

    def restored_docx_path(self, case_id: str, document_id: str) -> Path:
        return self._case_dir(case_id) / "outputs" / "restored" / f"{validate_document_id(document_id)}.docx"

    def draft_path(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "rules" / "draft-rules.json"

    def mapping_path(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "rules" / "case-redaction.json"

    def archive_dir(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "rules" / "archive"

    def write_draft(self, case_id: str, draft: Draft) -> Path:
        path = self.draft_path(case_id)
        write_json(path, draft.to_dict())
        return path

    def read_draft(self, case_id: str) -> Draft:
        return Draft.from_dict(read_json(self.draft_path(case_id)))

    def _archive_mapping(self, case_id: str) -> None:
        mapping = self.mapping_path(case_id)
        if not mapping.is_file():
            return
        archive = self.archive_dir(case_id)
        ensure_dir(archive)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = archive / f"case-redaction-{stamp}.json"
        counter = 2
        while destination.exists():
            destination = archive / f"case-redaction-{stamp}-{counter}.json"
            counter += 1
        try:
            shutil.copy2(mapping, destination)
        except OSError as error:
            raise WorkspaceError("无法归档旧映射文件。") from error
        archived = sorted(archive.glob("case-redaction-*.json"), key=lambda path: path.name)
        for old in archived[:-5]:
            try:
                old.unlink()
            except OSError:
                pass

    def write_mapping(self, case_id: str, payload: Mapping[str, Any]) -> Path:
        self._archive_mapping(case_id)
        path = self.mapping_path(case_id)
        write_json(path, payload)
        self.update_case(case_id, status="redacted", applied_at=utc_now())
        return path

    def read_mapping(self, case_id: str) -> dict[str, Any]:
        return read_json(self.mapping_path(case_id))

    def write_redacted_text(self, case_id: str, document_id: str, text: str) -> Path:
        path = self.redacted_text_path(case_id, document_id)
        atomic_write_text(path, text)
        self.update_document(case_id, document_id, redacted_path=self.relative_path(case_id, path))
        return path

    def write_restored_text(self, case_id: str, document_id: str, text: str) -> Path:
        path = self.restored_text_path(case_id, document_id)
        atomic_write_text(path, text)
        self.update_document(case_id, document_id, restored_path=self.relative_path(case_id, path))
        return path

    def document_texts(self, case_id: str) -> list[DocumentText]:
        case = self._read_case(case_id)
        documents: list[DocumentText] = []
        for document in case["documents"]:
            document_id = str(document["id"])
            documents.append(
                DocumentText(
                    id=document_id,
                    name=str(document.get("display_name", document.get("source_name", "文档"))),
                    text=self.read_document_text(case_id, document_id),
                    source_type=str(document.get("source_type", "text")),
                    extraction_method=str(document.get("extraction_method", "text")),
                    page_count=int(document.get("page_count", 1)),
                )
            )
        return documents

    def document_metadata(self, case_id: str) -> dict[str, dict[str, Any]]:
        case = self._read_case(case_id)
        result: dict[str, dict[str, Any]] = {}
        for document in case["documents"]:
            document_id = str(document["id"])
            result[document_id] = {
                "source_name": str(document.get("source_name", "")),
                "display_name": str(document.get("display_name", "")),
                "source_type": str(document.get("source_type", "text")),
                "extraction_method": str(document.get("extraction_method", "text")),
                "page_count": int(document.get("page_count", 1)),
            }
        return result

    def import_document(
        self,
        case_id: str,
        source_path: str | Path,
        *,
        password: str | None = None,
        ocr_runner: OcrRunner | None = None,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve()
        suffix = ensure_supported(source)
        if not source.is_file():
            raise DocumentError("选中的文件不存在。")
        case_dir = self.case_dir(case_id)
        document_id = uuid4().hex
        source_copy = case_dir / "sources" / f"{document_id}{suffix}"
        original_encrypted: Path | None = None
        ocr_dir: Path | None = None
        ocr_markdown: Path | None = None
        metadata: dict[str, Any] = {}
        created_paths: list[Path] = []
        try:
            check_cancelled(cancel)
            source_hash = sha256_file(source)
            if suffix == ".pdf":
                source_copy, original_encrypted, was_encrypted = unlock_or_copy_pdf(
                    source, source_copy, password
                )
                created_paths.append(source_copy)
                if original_encrypted is not None:
                    created_paths.append(original_encrypted)
                pages = extract_pdf_pages(source_copy)
                if is_scanned_pdf(pages):
                    ocr_dir = case_dir / "ocr" / document_id
                    ensure_dir(ocr_dir)
                    ocr_markdown = case_dir / "extracted" / f"{document_id}.ocr.md"
                    emit_progress(
                        progress,
                        {
                            "stage": "ocr_started",
                            "total_pages": len(pages),
                            "completed_pages": 0,
                            "failed_pages": 0,
                        },
                    )
                    if ocr_runner is not None:
                        ocr_runner(source_copy, ocr_markdown, ocr_dir)
                    else:
                        default_ocr_runner(
                            source_copy,
                            ocr_markdown,
                            ocr_dir,
                            progress=progress,
                            cancel=cancel,
                        )
                    ocr_text = read_ocr_pages(ocr_dir, ocr_markdown)
                    if ocr_markdown.is_file():
                        created_paths.append(ocr_markdown)
                    extracted_text = ocr_text.text
                    metadata.update(
                        {
                            "extraction_method": "pdf-to-markdown-ocr",
                            "page_count": ocr_text.page_count,
                            "ocr_workdir": self.relative_path(case_id, ocr_dir),
                            "ocr_markdown_path": self.relative_path(case_id, ocr_markdown),
                        }
                    )
                    if ocr_text.failed_pages:
                        metadata["warnings"] = [
                            "OCR 有 " + str(len(ocr_text.failed_pages)) + " 页失败，请人工复核。"
                        ]
                else:
                    extracted_text = page_anchored_text(pages)
                    metadata.update({"extraction_method": "pdf-text", "page_count": len(pages)})
                metadata["was_encrypted"] = was_encrypted
            elif suffix == ".docx":
                shutil.copy2(source, source_copy)
                created_paths.append(source_copy)
                extracted_text = extract_docx(source_copy)
                metadata.update({"extraction_method": "docx-text", "page_count": 1})
            else:
                shutil.copy2(source, source_copy)
                created_paths.append(source_copy)
                extracted_text, encoding = read_text_file(source_copy)
                metadata.update(
                    {"extraction_method": "text", "page_count": 1, "source_encoding": encoding}
                )

            text_path = self.write_imported_text(case_id, document_id, extracted_text)
            created_paths.append(text_path)
            record: dict[str, Any] = {
                "schema_version": 1,
                "id": document_id,
                "display_name": source.name,
                "source_name": source.name,
                "source_type": suffix.lstrip("."),
                "source_path": self.relative_path(case_id, source_copy),
                "text_path": self.relative_path(case_id, text_path),
                "source_sha256": source_hash,
                "created_at": utc_now(),
                **metadata,
            }
            if original_encrypted is not None:
                record["original_encrypted_path"] = self.relative_path(case_id, original_encrypted)
            duplicate = next(
                (
                    str(item["id"])
                    for item in self.get_case(case_id)["documents"]
                    if item.get("source_sha256") == source_hash
                ),
                None,
            )
            if duplicate:
                record["duplicate_of"] = duplicate
                record.setdefault("warnings", []).append("该文件与已导入文档内容相同。")
            self.add_document(case_id, record)
            emit_progress(progress, {"stage": "import_finished", "document_id": document_id})
            return record
        except Exception:
            for path in reversed(created_paths):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            if ocr_dir is not None:
                shutil.rmtree(ocr_dir, ignore_errors=True)
            raise

    def import_documents(
        self,
        case_id: str,
        source_paths: Sequence[str | Path],
        *,
        password: str | None = None,
        ocr_runner: OcrRunner | None = None,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> ImportOutcome:
        outcome = ImportOutcome()
        total = len(source_paths)
        for index, source_path in enumerate(source_paths, start=1):
            check_cancelled(cancel)
            emit_progress(
                progress,
                {
                    "stage": "file_started",
                    "file_index": index,
                    "total_files": total,
                    "file_name": Path(source_path).name,
                },
            )

            def document_progress(event: Mapping[str, Any], *, file_index: int = index) -> None:
                payload = dict(event)
                payload.update({"file_index": file_index, "total_files": total})
                emit_progress(progress, payload)

            try:
                record = self.import_document(
                    case_id,
                    source_path,
                    password=password,
                    ocr_runner=ocr_runner,
                    progress=document_progress,
                    cancel=cancel,
                )
            except OperationCancelled:
                raise
            except Exception as error:
                outcome.failures.append(
                    ImportFailure(
                        display_name=Path(source_path).name,
                        code=getattr(error, "code", type(error).__name__),
                        message=str(error),
                    )
                )
                emit_progress(
                    progress,
                    {"stage": "file_failed", "file_index": index, "total_files": total},
                )
            else:
                outcome.imported.append(record)
                emit_progress(
                    progress,
                    {"stage": "file_finished", "file_index": index, "total_files": total},
                )
        return outcome
