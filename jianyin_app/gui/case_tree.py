"""Case/document navigation tree."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Mapping, Sequence

from .formatting import document_status
from .theme import FONT_UI


class CaseTree(ttk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_select: Callable[[str | None, str | None], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Sidebar.TFrame")
        self.on_select = on_select
        self.items: dict[str, tuple[str, str | None]] = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            self,
            show="tree",
            selectmode="browse",
            style="Case.Treeview",
        )
        scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.tree.yview,
            style="Sidebar.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("case", font=("Microsoft YaHei UI", 10, "bold"))
        self.tree.tag_configure("document", font=FONT_UI)
        self.tree.bind("<<TreeviewSelect>>", self._selected)

    def refresh(self, cases: Sequence[Mapping[str, Any]], *, select_case: str | None = None, select_document: str | None = None) -> None:
        self.items.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for case in cases:
            case_id = str(case.get("id", ""))
            if not case_id:
                continue
            documents = case.get("documents") if isinstance(case.get("documents"), list) else []
            case_item = f"case:{case_id}"
            self.tree.insert(
                "",
                "end",
                iid=case_item,
                text=f"{case.get('name', '未命名案件')}  ·  {len(documents)} 份",
                open=True,
                tags=("case",),
            )
            self.items[case_item] = (case_id, None)
            for document in documents:
                document_id = str(document.get("id", ""))
                if not document_id:
                    continue
                document_item = f"document:{case_id}:{document_id}"
                self.tree.insert(
                    case_item,
                    "end",
                    iid=document_item,
                    text=f"{document.get('display_name', '未命名文件')}  ·  {document_status(document)}",
                    tags=("document",),
                )
                self.items[document_item] = (case_id, document_id)

        desired: str | None = None
        if select_case and select_document:
            candidate = f"document:{select_case}:{select_document}"
            if self.tree.exists(candidate):
                desired = candidate
        if desired is None and select_case:
            candidate = f"case:{select_case}"
            if self.tree.exists(candidate):
                desired = candidate
        if desired is not None:
            self.tree.selection_set(desired)
            self.tree.focus(desired)
            self.tree.see(desired)

    def selection(self) -> tuple[str | None, str | None]:
        selected = self.tree.selection()
        if not selected:
            return None, None
        return self.items.get(selected[0], (None, None))

    def _selected(self, _event: object | None = None) -> None:
        if self.on_select is not None:
            case_id, document_id = self.selection()
            self.on_select(case_id, document_id)
