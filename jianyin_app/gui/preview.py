"""Read-only document preview with category highlights and selection offsets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from .theme import FONT_UI, FONT_UI_SMALL, PALETTE

Highlight = tuple[int, int, str]


class PreviewPane:
    def __init__(
        self,
        parent: tk.Widget,
        *,
        kicker: str,
        title: str,
        subtitle: str,
        badge: str,
        badge_style: str,
        on_tag_click: Callable[[str], None] | None = None,
    ) -> None:
        self.on_tag_click = on_tag_click
        self.frame = ttk.Frame(parent, style="Paper.TFrame", padding=0)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(2, weight=1)
        color = PALETTE

        heading = tk.Frame(self.frame, background=color["paper"], padx=15, pady=11)
        heading.grid(row=0, column=0, sticky="ew")
        heading.columnconfigure(0, weight=1)
        tk.Label(
            heading,
            text=kicker,
            background=color["paper"],
            foreground=color["muted"],
            font=("Microsoft YaHei UI", 8, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            heading,
            text=title,
            background=color["paper"],
            foreground=color["ink_alt"],
            font=("Microsoft YaHei UI", 11, "bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.badge = tk.Label(
            heading,
            text=badge,
            background=color["redact_soft"] if badge_style == "blue" else color["accent_soft"],
            foreground=color["redact"] if badge_style == "blue" else color["accent_deep"],
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=7,
            pady=3,
        )
        self.badge.grid(row=0, column=1, rowspan=2, sticky="e")

        self.subtitle = tk.Label(
            self.frame,
            text=subtitle,
            background=color["paper"],
            foreground=color["muted"],
            font=FONT_UI_SMALL,
            anchor="w",
            padx=15,
            pady=6,
        )
        self.subtitle.grid(row=1, column=0, sticky="ew")

        text_frame = ttk.Frame(self.frame, style="Paper.TFrame")
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.text = tk.Text(
            text_frame,
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=18,
            pady=15,
            font=FONT_UI,
            background=color["paper"],
            foreground=color["text"],
            insertbackground=color["text"],
            selectbackground=color["accent_soft"],
            selectforeground=color["text"],
            state="disabled",
            spacing1=2,
            spacing3=3,
        )
        scrollbar = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.text.yview,
            style="Paper.Vertical.TScrollbar",
        )
        self.text.configure(yscrollcommand=scrollbar.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._base_offset = 0
        self._tags: set[str] = set()

    def ensure_tag(
        self,
        name: str,
        *,
        background: str,
        foreground: str = "#2B1B12",
        underline: bool = False,
    ) -> None:
        if name in self._tags:
            return
        self.text.tag_configure(
            name,
            background=background,
            foreground=foreground,
            underline=underline,
        )
        if self.on_tag_click is not None:
            self.text.tag_bind(name, "<Button-1>", lambda _event, tag=name: self.on_tag_click(tag))
        self._tags.add(name)

    def set_content(
        self,
        content: str,
        highlights: Sequence[Highlight] = (),
        *,
        base_offset: int = 0,
    ) -> None:
        self._base_offset = base_offset
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        for start, end, tag in highlights:
            if end <= start:
                continue
            if tag not in self._tags:
                self.ensure_tag(tag, background=PALETTE["accent_soft"])
            self.text.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")
        self.text.configure(state="disabled")

    def clear(self, message: str = "") -> None:
        self.set_content(message, [], base_offset=0)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.configure(text=text)

    def set_badge(self, text: str) -> None:
        self.badge.configure(text=text)

    def selection_range(self) -> tuple[int, int] | None:
        try:
            first = self.text.index("sel.first")
            last = self.text.index("sel.last")
        except tk.TclError:
            return None
        try:
            start = self.text.count("1.0", first, "chars")[0]
            end = self.text.count("1.0", last, "chars")[0]
        except (tk.TclError, TypeError):
            return None
        if start is None or end is None or end <= start:
            return None
        return self._base_offset + start, self._base_offset + end

    def scroll_to(self, offset: int) -> None:
        local = max(0, offset - self._base_offset)
        try:
            self.text.see(f"1.0+{local}c")
            self.text.mark_set("insert", f"1.0+{local}c")
            self.text.focus_set()
        except tk.TclError:
            pass

    def focus_text(self) -> None:
        self.text.focus_set()
