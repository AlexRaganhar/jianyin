"""Modal dialogs for rule editing, settings, and export."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from ..config import CHINESE_RULE_IDS, WorkspaceSettings
from ..model.labels import ALL_CATEGORIES, load_category_labels
from ..redaction.schema import CandidateRule
from .theme import FONT_UI, FONT_UI_SMALL, PALETTE

MATCH_MODE_LABELS = {
    "auto": "自动",
    "literal": "精确匹配",
    "ascii_word": "英文词边界",
    "digit_boundary": "数字边界",
}
MATCH_MODE_LOOKUP = {label: key for key, label in MATCH_MODE_LABELS.items()}

CHINESE_LABELS = {
    "cn_id": "身份证号",
    "cn_mobile": "手机号",
    "cn_bank_card": "银行卡号",
    "cn_name_context": "姓名线索（低置信）",
    "cn_landline": "座机号",
    "cn_date": "中文日期",
    "cn_address": "中文地址",
}


def _center(window: tk.Toplevel, parent: tk.Misc) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = parent.winfo_rootx() + max((parent.winfo_width() - width) // 2, 0)
    y = parent.winfo_rooty() + max((parent.winfo_height() - height) // 2, 0)
    window.geometry(f"+{x}+{y}")


class RuleDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        candidate: CandidateRule | None = None,
        source: str = "",
        category: str = "private_person",
        subtype: str | None = None,
        target: str = "",
        editing: bool = False,
    ) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.editing = editing
        self.title("编辑脱敏规则" if editing else "添加脱敏规则")
        self.configure(background=PALETTE["paper"])
        self.transient(parent)
        self.resizable(False, False)
        self.columnconfigure(1, weight=1)

        labels = load_category_labels()
        self._category_by_label: dict[str, str] = {}
        self._label_by_category: dict[str, str] = {}
        for value in ALL_CATEGORIES:
            label = labels.get(value, {}).get("label", value)
            self._category_by_label[label] = value
            self._label_by_category[value] = label
        if category not in self._label_by_category:
            self._label_by_category[category] = category
            self._category_by_label[category] = category

        row = 0
        self._label(row, "类别")
        self.category_var = tk.StringVar(value=self._label_by_category.get(category, category))
        category_box = ttk.Combobox(
            self,
            textvariable=self.category_var,
            values=list(self._category_by_label),
            state="readonly",
            font=FONT_UI_SMALL,
            width=32,
        )
        category_box.grid(row=row, column=1, sticky="ew", padx=(8, 14), pady=(14, 6))
        row += 1

        self._label(row, "原文")
        self.source_var = tk.StringVar(value=source)
        source_entry = ttk.Entry(self, textvariable=self.source_var, font=FONT_UI, width=36)
        source_entry.grid(row=row, column=1, sticky="ew", padx=(8, 14), pady=6)
        if editing:
            source_entry.configure(state="readonly")
        row += 1

        self._label(row, "子类型")
        self.subtype_var = tk.StringVar(value=subtype or "—")
        subtype_label = ttk.Label(self, textvariable=self.subtype_var, style="Status.TLabel")
        subtype_label.grid(row=row, column=1, sticky="w", padx=(8, 14), pady=6)
        row += 1

        self._label(row, "替换为")
        self.target_var = tk.StringVar(value=target)
        ttk.Entry(self, textvariable=self.target_var, font=FONT_UI, width=36).grid(
            row=row, column=1, sticky="ew", padx=(8, 14), pady=6
        )
        row += 1

        self._label(row, "匹配方式")
        self.match_var = tk.StringVar(value=MATCH_MODE_LABELS.get("auto", "自动"))
        mode_box = ttk.Combobox(
            self,
            textvariable=self.match_var,
            values=list(MATCH_MODE_LABELS.values()),
            state="readonly",
            font=FONT_UI_SMALL,
            width=32,
        )
        mode_box.grid(row=row, column=1, sticky="ew", padx=(8, 14), pady=6)
        row += 1

        self._label(row, "备注")
        self.note_var = tk.StringVar(value=candidate.note if candidate else "")
        ttk.Entry(self, textvariable=self.note_var, font=FONT_UI, width=36).grid(
            row=row, column=1, sticky="ew", padx=(8, 14), pady=6
        )
        row += 1

        self.enabled_var = tk.BooleanVar(value=candidate.enabled if candidate else True)
        self.apply_all_var = tk.BooleanVar(value=candidate.apply_all if candidate else True)
        checks = ttk.Frame(self, style="Paper.TFrame")
        checks.grid(row=row, column=1, sticky="w", padx=(8, 14), pady=6)
        ttk.Checkbutton(checks, text="启用", variable=self.enabled_var).pack(side="left")
        ttk.Checkbutton(checks, text="应用到全案件所有精确出现", variable=self.apply_all_var).pack(
            side="left", padx=(14, 0)
        )
        row += 1

        hint = ttk.Label(
            self,
            text="替换值留空时，应用前会按当前策略自动生成。",
            style="Status.TLabel",
        )
        hint.grid(row=row, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 0))
        row += 1

        buttons = ttk.Frame(self, style="Paper.TFrame", padding=(14, 10, 14, 14))
        buttons.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=self._cancel, style="Quiet.TButton").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="保存", command=self._save, style="Accent.TButton").pack(side="left")

        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()
        self.after(10, lambda: _center(self, parent))
        self.after(20, lambda: source_entry.focus_set() if not editing else self.focus_set())

    def _label(self, row: int, text: str) -> None:
        ttk.Label(self, text=text, style="Status.TLabel").grid(
            row=row, column=0, sticky="ne", padx=(14, 0), pady=(14, 6) if row == 0 else 6
        )

    def _save(self) -> None:
        source = self.source_var.get().strip()
        target = self.target_var.get().strip()
        if not source:
            messagebox.showwarning("缺少原文", "原文不能为空。", parent=self)
            return
        if "\n" in source or "\r" in source:
            messagebox.showwarning("原文无效", "原文不能包含换行。", parent=self)
            return
        if "\n" in target or "\r" in target:
            messagebox.showwarning("替换值无效", "替换值不能包含换行。", parent=self)
            return
        category = self._category_by_label.get(self.category_var.get(), "other")
        self.result = {
            "category": category,
            "source": source,
            "target": target,
            "enabled": bool(self.enabled_var.get()),
            "apply_all": bool(self.apply_all_var.get()),
            "match_mode": MATCH_MODE_LOOKUP.get(self.match_var.get(), "auto"),
            "note": self.note_var.get().strip(),
            "subtype": None if self.subtype_var.get() == "—" else self.subtype_var.get(),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> dict[str, Any] | None:
        self.wait_window(self)
        return self.result


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, settings: WorkspaceSettings) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.title("笺隐设置")
        self.configure(background=PALETTE["paper"])
        self.transient(parent)
        self.resizable(False, False)
        self.columnconfigure(1, weight=1)

        row = 0
        self._label(row, "模型目录")
        model_frame = ttk.Frame(self, style="Paper.TFrame")
        model_frame.grid(row=row, column=1, sticky="ew", padx=(8, 14), pady=(14, 6))
        model_frame.columnconfigure(0, weight=1)
        self.model_var = tk.StringVar(value=settings.model_dir or "")
        ttk.Entry(model_frame, textvariable=self.model_var, font=FONT_UI_SMALL).grid(row=0, column=0, sticky="ew")
        ttk.Button(model_frame, text="浏览", command=self._browse_model, style="Quiet.TButton").grid(
            row=0, column=1, padx=(6, 0)
        )
        row += 1

        self._label(row, "策略规则")
        policy_frame = ttk.Frame(self, style="Paper.TFrame")
        policy_frame.grid(row=row, column=1, sticky="ew", padx=(8, 14), pady=6)
        policy_frame.columnconfigure(0, weight=1)
        self.policy_var = tk.StringVar(value=settings.policy_path or "")
        ttk.Entry(policy_frame, textvariable=self.policy_var, font=FONT_UI_SMALL).grid(row=0, column=0, sticky="ew")
        ttk.Button(policy_frame, text="浏览", command=self._browse_policy, style="Quiet.TButton").grid(
            row=0, column=1, padx=(6, 0)
        )
        row += 1

        self._label(row, "中文补强")
        chinese_frame = ttk.Frame(self, style="Paper.TFrame")
        chinese_frame.grid(row=row, column=1, sticky="w", padx=(8, 14), pady=6)
        self.chinese_vars: dict[str, tk.BooleanVar] = {}
        for index, rule_id in enumerate(CHINESE_RULE_IDS):
            variable = tk.BooleanVar(value=settings.chinese.enabled(rule_id))
            self.chinese_vars[rule_id] = variable
            ttk.Checkbutton(chinese_frame, text=CHINESE_LABELS.get(rule_id, rule_id), variable=variable).grid(
                row=index // 3, column=index % 3, sticky="w", padx=(0, 12), pady=2
            )
        row += 1

        self._label(row, "窗口参数")
        window_frame = ttk.Frame(self, style="Paper.TFrame")
        window_frame.grid(row=row, column=1, sticky="w", padx=(8, 14), pady=6)
        self.window_var = tk.StringVar(value=str(settings.window_size))
        self.overlap_var = tk.StringVar(value=str(settings.overlap_tokens))
        ttk.Label(window_frame, text="窗口", style="Status.TLabel").pack(side="left")
        ttk.Spinbox(window_frame, from_=512, to=8192, increment=512, textvariable=self.window_var, width=7).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(window_frame, text="重叠", style="Status.TLabel").pack(side="left")
        ttk.Spinbox(window_frame, from_=0, to=4096, increment=64, textvariable=self.overlap_var, width=7).pack(
            side="left", padx=(4, 12)
        )
        row += 1

        self._label(row, "解码")
        self.decode_var = tk.StringVar(value=settings.decode_mode)
        ttk.Combobox(
            self,
            textvariable=self.decode_var,
            values=("viterbi", "argmax"),
            state="readonly",
            width=14,
        ).grid(row=row, column=1, sticky="w", padx=(8, 14), pady=6)
        row += 1

        self.export_var = tk.BooleanVar(value=settings.export_docx)
        ttk.Checkbutton(self, text="应用脱敏时同时生成 DOCX（文本重排）", variable=self.export_var).grid(
            row=row, column=1, sticky="w", padx=(8, 14), pady=6
        )
        row += 1

        buttons = ttk.Frame(self, style="Paper.TFrame", padding=(14, 10, 14, 14))
        buttons.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=self._cancel, style="Quiet.TButton").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="保存", command=self._save, style="Accent.TButton").pack(side="left")
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()
        self.after(10, lambda: _center(self, parent))

    def _label(self, row: int, text: str) -> None:
        ttk.Label(self, text=text, style="Status.TLabel").grid(
            row=row, column=0, sticky="ne", padx=(14, 0), pady=(14, 6) if row == 0 else 6
        )

    def _browse_model(self) -> None:
        selected = filedialog.askdirectory(title="选择 Q4 ONNX 模型目录", parent=self)
        if selected:
            self.model_var.set(selected)

    def _browse_policy(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择策略规则 JSON",
            filetypes=(("JSON 文件", "*.json"),),
            parent=self,
        )
        if selected:
            self.policy_var.set(selected)

    def _save(self) -> None:
        try:
            window_size = int(self.window_var.get())
            overlap_tokens = int(self.overlap_var.get())
        except ValueError:
            messagebox.showwarning("参数无效", "窗口和重叠必须是整数。", parent=self)
            return
        settings = WorkspaceSettings(
            model_dir=self.model_var.get().strip() or None,
            policy_path=self.policy_var.get().strip() or None,
            window_size=window_size,
            overlap_tokens=overlap_tokens,
            decode_mode=self.decode_var.get(),
            export_docx=bool(self.export_var.get()),
        )
        for rule_id, variable in self.chinese_vars.items():
            setattr(settings.chinese, rule_id, bool(variable.get()))
        try:
            settings.model_config().validate()
        except Exception as error:
            messagebox.showwarning("参数无效", str(error), parent=self)
            return
        self.result = settings
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> WorkspaceSettings | None:
        self.wait_window(self)
        return self.result


class ExportDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, *, default_dir: Path, current_name: str) -> None:
        super().__init__(parent)
        self.result: dict[str, Any] | None = None
        self.title("导出脱敏结果")
        self.configure(background=PALETTE["paper"])
        self.transient(parent)
        self.resizable(False, False)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="导出范围", style="Status.TLabel").grid(
            row=0, column=0, sticky="ne", padx=(14, 0), pady=(14, 6)
        )
        scope_frame = ttk.Frame(self, style="Paper.TFrame")
        scope_frame.grid(row=0, column=1, sticky="w", padx=(8, 14), pady=(14, 6))
        self.scope_var = tk.StringVar(value="current")
        ttk.Radiobutton(scope_frame, text=f"当前文档：{current_name}", variable=self.scope_var, value="current").pack(
            anchor="w"
        )
        ttk.Radiobutton(scope_frame, text="当前案件全部文档", variable=self.scope_var, value="all").pack(anchor="w")

        ttk.Label(self, text="导出格式", style="Status.TLabel").grid(
            row=1, column=0, sticky="ne", padx=(14, 0), pady=6
        )
        format_frame = ttk.Frame(self, style="Paper.TFrame")
        format_frame.grid(row=1, column=1, sticky="w", padx=(8, 14), pady=6)
        self.md_var = tk.BooleanVar(value=True)
        self.docx_var = tk.BooleanVar(value=True)
        self.mapping_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(format_frame, text="Markdown", variable=self.md_var).pack(side="left")
        ttk.Checkbutton(format_frame, text="Word (DOCX)", variable=self.docx_var).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(
            format_frame,
            text="映射 JSON（含原始值，谨慎外发）",
            variable=self.mapping_var,
        ).pack(side="left", padx=(12, 0))

        ttk.Label(self, text="目标文件夹", style="Status.TLabel").grid(
            row=2, column=0, sticky="ne", padx=(14, 0), pady=6
        )
        dir_frame = ttk.Frame(self, style="Paper.TFrame")
        dir_frame.grid(row=2, column=1, sticky="ew", padx=(8, 14), pady=6)
        dir_frame.columnconfigure(0, weight=1)
        self.dir_var = tk.StringVar(value=str(default_dir))
        ttk.Entry(dir_frame, textvariable=self.dir_var, font=FONT_UI_SMALL).grid(row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="浏览", command=self._browse, style="Quiet.TButton").grid(
            row=0, column=1, padx=(6, 0)
        )

        buttons = ttk.Frame(self, style="Paper.TFrame", padding=(14, 10, 14, 14))
        buttons.grid(row=3, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=self._cancel, style="Quiet.TButton").pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="导出", command=self._save, style="Accent.TButton").pack(side="left")
        self.bind("<Escape>", lambda _event: self._cancel())
        self.grab_set()
        self.after(10, lambda: _center(self, parent))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="选择导出目录", parent=self)
        if selected:
            self.dir_var.set(selected)

    def _save(self) -> None:
        if not (self.md_var.get() or self.docx_var.get() or self.mapping_var.get()):
            messagebox.showwarning("未选格式", "请至少选择一种导出内容。", parent=self)
            return
        target = self.dir_var.get().strip()
        if not target:
            messagebox.showwarning("缺少目录", "请选择导出目录。", parent=self)
            return
        self.result = {
            "scope": self.scope_var.get(),
            "include_md": bool(self.md_var.get()),
            "include_docx": bool(self.docx_var.get()),
            "include_mapping": bool(self.mapping_var.get()),
            "target_dir": Path(target),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> dict[str, Any] | None:
        self.wait_window(self)
        return self.result
