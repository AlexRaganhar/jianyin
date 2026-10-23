"""Scanned-PDF OCR through the bundled pdf2md pipeline.

The bundled pipeline (``jianyin_app/vendor/pdf2md``) owns rendering, OCR,
checkpointing and Markdown generation. JianYin only adapts its per-page blocks
back to the page-anchored text format used by the review UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..detection.base import CancelCheck, ProgressCallback, check_cancelled, emit_progress
from ..errors import OcrError, OperationCancelled
from ..vendor.pdf2md import convert_pdf
from ..vendor.pdf2md.markdown import blocks_to_text, failed_page_marker
from .markdown import page_anchored_text


@dataclass(frozen=True)
class OcrTextResult:
    text: str
    page_count: int
    failed_pages: tuple[int, ...]


OcrRunner = Callable[[Path, Path], OcrTextResult]


def run_ocr(
    input_pdf: Path,
    output_markdown: Path,
    *,
    source_path: Path | None = None,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
    threshold: float = 0.5,
) -> OcrTextResult:
    """OCR one PDF, reporting page progress and honoring cancellation."""
    check_cancelled(cancel)

    def on_page(page_no: int, total: int) -> None:
        # Called after the page checkpoint is durable, so raising here keeps
        # the finished page and loses at most the current in-flight page.
        check_cancelled(cancel)
        emit_progress(
            progress,
            {
                "stage": "ocr_progress",
                "total_pages": total,
                "completed_pages": page_no,
                "failed_pages": 0,
            },
        )

    try:
        result = convert_pdf(
            input_pdf,
            output_markdown,
            source_path=source_path,
            threshold=threshold,
            on_page=on_page,
            log=lambda _message: None,
        )
    except OperationCancelled:
        raise
    except Exception as error:
        raise OcrError("扫描 PDF 的 OCR 转换未完成。") from error

    failed = frozenset(result.failed_pages)
    pages = [
        failed_page_marker(page_no) if page_no in failed else blocks_to_text(blocks, threshold)
        for page_no, blocks in enumerate(result.pages, start=1)
    ]
    return OcrTextResult(
        text=page_anchored_text(pages),
        page_count=result.total_pages,
        failed_pages=tuple(result.failed_pages),
    )
