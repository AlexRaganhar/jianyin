"""Rule review table used by the main workspace."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

from ..redaction.schema import CandidateRule
from .formatting import candidate_counts, candidate_label, candidate_origin, shorten
from .theme import FONT_UI_SMALL


class RulesPanel(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_select: Callable[[CandidateRule | None], None] | None = None,
        on_add: Callable[[], None] | None = None,
        on_edit: Callable[[CandidateRule | None], None] | None = None,
        on_delete: Callable[[CandidateRule | None], None] | None = None,
        on_toggle: Callable[[CandidateRule | None], None] | None = None,
        on_reset: Callable[[CandidateRule | None], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Paper.TFrame")
        self.on_select = on_select
        self.on_add = on_add
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_toggle = on_toggle
        self.on_reset = on_reset
        self._candidates: list[CandidateRule] = []
        self._visible: list[CandidateRule] = []
        self._filter = tk.StringVar()

        toolbar = ttk.Frame(self, style="Paper.TFrame", padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        ttk.Label(
            toolbar,
            text="过滤",
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))
        entry = ttk.Entry(toolbar, textvariable=self._filter, width=20, font=FONT_UI_SMALL)
        entry.grid(row=0, column=1, sticky="w")
        self._filter.trace_add("write", lambda *_args: self.refresh())
        buttons = ttk.Frame(toolbar, style="Paper.TFrame")
        buttons.grid(row=0, column=2, sticky="e")
        self._button(buttons, "添加规则", self._add).pack(side="left", padx=(6, 0))
        self._button(buttons, "编辑", self._edit).pack(side="left", padx=(6, 0))
        self._button(buttons, "启停", self._toggle).pack(side="left", padx=(6, 0))
        self._button(buttons, "重置替换值", self._reset).pack(side="left", padx=(6, 0))
        self._button(buttons, "删除", self._delete).pack(side="left", padx=(6, 0))

        tree_frame = ttk.Frame(self, style="Paper.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        columns = ("enabled", "category", "source", "target", "counts", "origin", "note")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Rules.Treeview",
            height=6,
        )
        headings = {
            "enabled": "启用",
            "category": "类别",
            "source": "原文",
            "target": "替换为",
            "counts": "命中/字面",
            "origin": "来源",
            "note": "备注",
        }
        widths = {
            "enabled": 44,
            "category": 120,
            "source": 190,
            "target": 150,
            "counts": 76,
            "origin": 120,
            "note": 120,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=40, anchor="w", stretch=column in {"source", "target", "note"})
        self.tree.tag_configure("disabled", foreground="#9A9288")
        scrollbar = ttk.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.tree.yview,
            style="Paper.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.tree.bind("<Double-1>", self._double_click)

    @staticmethod
    def _button(parent: ttk.Frame, text: str, command: Callable[[], None]) -> ttk.Button:
        return ttk.Button(parent, text=text, command=command, style="Quiet.TButton")

    def set_candidates(self, candidates: Sequence[CandidateRule]) -> None:
        selected = self.selected_candidate()
        selected_id = selected.id if selected else None
        self._candidates = list(candidates)
        self.refresh()
        if selected_id is not None:
            self.select_candidate(selected_id)

    def refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        needle = self._filter.get().strip().lower()
        self._visible = []
        for candidate in self._candidates:
            haystack = " ".join(
                [
                    candidate.category,
                    candidate.subtype or "",
                    candidate.source,
                    candidate.target,
                    candidate.note,
                    " ".join(candidate.detection_sources),
                ]
            ).lower()
            if needle and needle not in haystack:
                continue
            self._visible.append(candidate)
            self.tree.insert(
                "",
                "end",
                iid=str(candidate.id),
                values=(
                    "是" if candidate.enabled else "否",
                    candidate_label(candidate),
                    shorten(candidate.source, 40),
                    shorten(candidate.target, 28),
                    candidate_counts(candidate),
                    shorten(candidate_origin(candidate), 26),
                    shorten(candidate.note, 24),
                ),
                tags=() if candidate.enabled else ("disabled",),
            )

    def selected_candidate(self) -> CandidateRule | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            candidate_id = int(selection[0])
        except ValueError:
            return None
        return next((candidate for candidate in self._candidates if candidate.id == candidate_id), None)

    def select_candidate(self, candidate_id: int) -> None:
        iid = str(candidate_id)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    def _selected(self, _event: object | None = None) -> None:
        if self.on_select is not None:
            self.on_select(self.selected_candidate())

    def _double_click(self, _event: object | None = None) -> None:
        if self.on_edit is not None:
            self.on_edit(self.selected_candidate())

    def _add(self) -> None:
        if self.on_add is not None:
            self.on_add()

    def _edit(self) -> None:
        if self.on_edit is not None:
            self.on_edit(self.selected_candidate())

    def _delete(self) -> None:
        if self.on_delete is not None:
            self.on_delete(self.selected_candidate())

    def _toggle(self) -> None:
        if self.on_toggle is not None:
            self.on_toggle(self.selected_candidate())

    def _reset(self) -> None:
        if self.on_reset is not None:
            self.on_reset(self.selected_candidate())
