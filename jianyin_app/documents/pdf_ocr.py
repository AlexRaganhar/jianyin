"""Local scanned-PDF OCR integration through the sibling pdf-to-markdown tool."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from ..config import pdf_to_markdown_candidates
from ..detection.base import CancelCheck, ProgressCallback, emit_progress
from ..errors import OcrError, OperationCancelled
from .markdown import page_anchored_text

PROGRESS_FILE = "progress.json"
PAGES_DIR = "pages"

OcrRunner = Callable[..., Any]


@dataclass(frozen=True)
class OcrRunResult:
    total_pages: int
    completed_pages: int
    failed_pages: tuple[int, ...]


@dataclass(frozen=True)
class OcrTextResult:
    text: str
    page_count: int
    failed_pages: tuple[int, ...]


def find_pdf_to_markdown_dir() -> Path:
    for candidate in pdf_to_markdown_candidates():
        if (candidate / "main.py").is_file() or (candidate / "pdf2md").is_dir():
            return candidate
    raise OcrError(
        "未找到本地 pdf-to-markdown OCR 工具。请设置 "
        "JIANYIN_PDF_TO_MARKDOWN_DIR，或把它放在项目同级目录。"
    )


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise OcrError("OCR 输出文本无法读取。")


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def progress_snapshot(workdir: Path) -> dict[str, int] | None:
    payload = _read_json(workdir / PROGRESS_FILE)
    if payload is None:
        return None
    total = payload.get("total")
    done = payload.get("done")
    failed = payload.get("failed")
    if not isinstance(total, int) or total < 0 or not isinstance(done, list) or not isinstance(failed, list):
        return None
    completed = len({page for page in done if isinstance(page, int) and page > 0})
    failed_count = len({page for page in failed if isinstance(page, int) and page > 0})
    return {"total_pages": total, "completed_pages": completed, "failed_pages": failed_count}


def _page_number(path: Path) -> int:
    try:
        return int(path.stem.split("_")[-1])
    except ValueError:
        return 0


def read_ocr_pages(workdir: Path, markdown_path: Path) -> OcrTextResult:
    pages_dir = workdir / PAGES_DIR
    page_files = sorted(pages_dir.glob("page_*.txt"), key=_page_number) if pages_dir.is_dir() else []
    if page_files:
        pages = [_read_text(page_file) for page_file in page_files]
        snapshot = _read_json(workdir / PROGRESS_FILE) or {}
        failed_raw = snapshot.get("failed")
        failed: list[int] = []
        if isinstance(failed_raw, list):
            failed = sorted({page for page in failed_raw if isinstance(page, int) and page > 0})
        return OcrTextResult(
            text=page_anchored_text(pages),
            page_count=len(pages),
            failed_pages=tuple(failed),
        )

    if markdown_path.is_file():
        text = _read_text(markdown_path)
        if text.strip():
            return OcrTextResult(text=text if text.endswith("\n") else text + "\n", page_count=1, failed_pages=())
    pages_txt = markdown_path.with_suffix(".pages.txt")
    if pages_txt.is_file():
        text = _read_text(pages_txt)
        if text.strip():
            return OcrTextResult(text=text if text.endswith("\n") else text + "\n", page_count=1, failed_pages=())
    raise OcrError("OCR 转换没有产生可审阅文本。")


def default_ocr_runner(
    input_pdf: Path,
    output_markdown: Path,
    workdir: Path,
    *,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
) -> OcrRunResult:
    tool_dir = find_pdf_to_markdown_dir()
    tool_python = tool_dir / ".venv" / "Scripts" / "python.exe"
    interpreter = tool_python if tool_python.is_file() else Path(sys.executable)
    command = [
        str(interpreter),
        str(tool_dir / "main.py"),
        str(input_pdf),
        "-o",
        str(output_markdown),
        "--txt",
        "--workdir",
        str(workdir),
    ]
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(tool_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise OcrError("本地 OCR 工具无法启动。") from error

    previous: tuple[int, int, int] | None = None
    while True:
        if cancel is not None and cancel():
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                pass
            raise OperationCancelled()
        snapshot = progress_snapshot(workdir)
        if snapshot is not None:
            marker = (
                snapshot["total_pages"],
                snapshot["completed_pages"],
                snapshot["failed_pages"],
            )
            if marker != previous:
                emit_progress(progress, {"stage": "ocr_progress", **snapshot})
                previous = marker
        returncode = process.poll()
        if returncode is not None:
            break
        time.sleep(0.25)

    snapshot = progress_snapshot(workdir)
    if snapshot is not None:
        marker = (snapshot["total_pages"], snapshot["completed_pages"], snapshot["failed_pages"])
        if marker != previous:
            emit_progress(progress, {"stage": "ocr_progress", **snapshot})
    if not output_markdown.is_file() and not (workdir / PAGES_DIR).is_dir():
        raise OcrError("OCR 转换未完成，未生成可导入文本。")
    if returncode != 0 and not (workdir / PAGES_DIR).is_dir() and not output_markdown.is_file():
        raise OcrError("OCR 转换失败，未生成可导入文本。")

    final = snapshot or {
        "total_pages": 0,
        "completed_pages": 0,
        "failed_pages": 0,
    }
    failed: list[int] = []
    payload = _read_json(workdir / PROGRESS_FILE) or {}
    raw_failed = payload.get("failed")
    if isinstance(raw_failed, list):
        failed = sorted({page for page in raw_failed if isinstance(page, int) and page > 0})
    return OcrRunResult(
        total_pages=int(final.get("total_pages", 0)),
        completed_pages=int(final.get("completed_pages", 0)),
        failed_pages=tuple(failed),
    )
