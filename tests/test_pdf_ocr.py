from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from jianyin_app.documents.pdf_ocr import run_ocr
from jianyin_app.errors import OperationCancelled

FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\msyh.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    pytest.skip("no CJK font available for the OCR integration test")


def _scanned_pdf(path: Path) -> None:
    image = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(image)
    draw.text((100, 100), "借款合同（节选）", font=_font(40), fill="black")
    draw.text((100, 220), "甲方：张伟，身份证号码 110101199003071234，", font=_font(30), fill="black")
    draw.text((100, 300), "联系电话 13800138000。", font=_font(30), fill="black")
    image.save(path, "PDF", resolution=200.0)


def test_bundled_ocr_reads_scanned_pdf(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    _scanned_pdf(source)
    output = tmp_path / "ocr" / "ocr.md"
    events: list[dict] = []

    result = run_ocr(source, output, progress=events.append)

    assert result.page_count == 1
    assert result.failed_pages == ()
    assert output.is_file()
    assert "身份证号码" in result.text
    assert "13800138000" in result.text
    assert "<!-- PDF page 1 -->" in result.text
    assert any(event.get("stage") == "ocr_progress" for event in events)


def test_cancel_is_reported_before_any_work(tmp_path: Path) -> None:
    with pytest.raises(OperationCancelled):
        run_ocr(tmp_path / "missing.pdf", tmp_path / "out.md", cancel=lambda: True)


def test_failed_page_is_marked_in_imported_text(tmp_path: Path, monkeypatch) -> None:
    class FakeResult:
        pages = [[], []]
        failed_pages = [2]
        total_pages = 2

    monkeypatch.setattr(
        "jianyin_app.documents.pdf_ocr.convert_pdf",
        lambda *args, **kwargs: FakeResult(),
    )
    result = run_ocr(tmp_path / "scan.pdf", tmp_path / "ocr.md")
    assert result.failed_pages == (2,)
    assert "（第 2 页 OCR 失败）" in result.text
