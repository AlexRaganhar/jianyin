"""Page markers, filename safety, and small Markdown helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PAGE_MARKER_RE = re.compile(r"(?m)^<!-- PDF page (\d+) -->\s*$")
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


@dataclass(frozen=True)
class PageRange:
    number: int
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


def page_anchored_text(pages: list[str]) -> str:
    blocks = []
    for index, page in enumerate(pages, start=1):
        blocks.append(f"<!-- PDF page {index} -->\n{page.strip()}")
    return "\n\n".join(blocks).rstrip() + "\n" if blocks else ""


def page_ranges(text: str) -> list[PageRange]:
    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return [PageRange(1, 0, len(text))]
    ranges: list[PageRange] = []
    for index, marker in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        try:
            number = int(marker.group(1))
        except (TypeError, ValueError):
            number = index + 1
        ranges.append(PageRange(number, marker.start(), end))
    return ranges


def strip_page_markers(text: str) -> str:
    return PAGE_MARKER_RE.sub("", text)


def safe_stem(name: str, *, fallback: str = "document", max_length: int = 80) -> str:
    value = Path(str(name)).name
    value = _INVALID_FILENAME_RE.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if value.lower().endswith((".md", ".markdown", ".txt", ".docx", ".pdf")):
        value = Path(value).stem
    if not value or value.upper() in _RESERVED_NAMES:
        value = fallback
    return value[:max_length].rstrip(" .") or fallback


def unique_filename(directory: Path, stem: str, suffix: str) -> Path:
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate
