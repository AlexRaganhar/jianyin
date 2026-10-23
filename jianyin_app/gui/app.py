"""笺隐 desktop workspace."""

from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import tkinter as tk
from importlib.resources import as_file, files
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Mapping, Sequence

from ..config import ConfigurationError, WorkspaceSettings, default_workspace_directory
from ..detection.chinese_rules import ChineseRuleDetector
from ..detection.composite import CompositeDetector
from ..errors import JianYinError, OperationCancelled
from ..model.onnx_detector import OnnxPrivacyFilter
from ..redaction.matching import count_literal_occurrences
from ..redaction.policy import RuleSet, default_ruleset
from ..redaction.schema import CandidateRule, Draft
from ..redaction.targets import TargetFactory
from ..workspace.paths import ensure_dir
from ..workspace.service import (
    analyze_case,
    apply_case,
    export_documents,
    is_mapping_stale,
    restore_case,
)
from ..workspace.store import CaseWorkspace, ImportOutcome
from .case_tree import CaseTree
from .dialogs import ExportDialog, RuleDialog, SettingsDialog
from .formatting import (
    case_status_label,
    clip_highlights,
    format_paths,
    format_summary,
    page_label,
)
from .jobs import JobRunner
from .preview import PreviewPane
from .rules_panel import RulesPanel
from .theme import FONT_UI_SMALL, PALETTE, apply_theme

SUPPORTED_FILE_TYPES = (
    ("案卷文件", "*.docx *.pdf *.txt *.md *.markdown"),
    ("Word 文档", "*.docx"),
    ("PDF 文件", "*.pdf"),
    ("文本与 Markdown", "*.txt *.md *.markdown"),
)
_PAGE_LABEL_RE = re.compile(r"^第 (\d+) 页$")
_ACCENT_WHITE = "#FFF9ED"


class JianYinApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("笺隐 · 本地文档脱敏工作台")
        self.root.geometry("1480x900")
        self.root.minsize(1160, 720)
        self.palette = apply_theme(root)
        self._initializing = True
        self._startup_warnings: list[str] = []
        self.workspace = CaseWorkspace(default_workspace_directory())
        try:
            self.settings = self.workspace.settings
            self.settings.model_config().validate()
        except ConfigurationError:
            self.settings = WorkspaceSettings()
            self._startup_warnings.append("工作区设置无效，已使用默认设置。")
        self.ruleset = self._load_policy(initial=True)
        self._configure_logging()
        self._icon_photo: tk.PhotoImage | None = None
        self._install_window_icon()

        self.current_case_id: str | None = None
        self.current_document_id: str | None = None
        self.current_case: dict[str, Any] | None = None
        self.current_document: dict[str, Any] | None = None
        self.current_draft: Draft | None = None
        self.current_mapping: dict[str, Any] | None = None
        self.current_original_text = ""
        self.current_redacted_text = ""
        self.current_restored_text = ""
        self.current_page_ranges = []
        self.running = False

        self.workspace_var = tk.StringVar(value=str(self.workspace.root))
        self.case_title_var = tk.StringVar(value="请选择或创建一个案件")
        self.document_title_var = tk.StringVar(value="未选择文件")
        self.case_count_var = tk.StringVar(value="0 个案件")
        self.engine_var = tk.StringVar(value="Q4 ONNX · CPU")
        self.banner_var = tk.StringVar(value="本地处理，不上传案卷。导出前请人工复核。")
        self.status_var = tk.StringVar(value="选择或创建案件后导入文件。")
        self.page_var = tk.StringVar(value="全部页面")
        self.show_restored_var = tk.BooleanVar(value=False)
        self.progress_value = tk.DoubleVar(value=0.0)

        self._action_buttons: list[ttk.Button] = []
        self.job = JobRunner(root, self._on_job_event)
        self._build()
        self._refresh_tree()
        self._update_engine_status()
        self._set_status("笺隐已就绪。所有材料只保存在本地工作区。")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._initializing = False
        if self._startup_warnings:
            self._set_status(self._startup_warnings[0])

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        header = ttk.Frame(self.root, style="Chrome.TFrame")
        header.grid(row=0, column=0, sticky="new")
        header.columnconfigure(1, weight=1)

        brand = ttk.Frame(header, style="Chrome.TFrame", width=290, padding=(21, 13))
        brand.grid(row=0, column=0, sticky="nsw")
        brand.grid_propagate(False)
        ttk.Label(brand, text="笺隐", style="Brand.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(brand, text="JIANYIN · LOCAL DOCUMENT REDACTION", style="BrandSub.TLabel").grid(
            row=1, column=0, sticky="w", pady=(1, 0)
        )

        context = ttk.Frame(header, style="Chrome.TFrame", padding=(24, 11))
        context.grid(row=0, column=1, sticky="nsew")
        context.columnconfigure(0, weight=1)
        ttk.Label(context, textvariable=self.workspace_var, style="ChromePath.TLabel", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(context, textvariable=self.case_title_var, style="ChromeCase.TLabel", anchor="w").grid(
            row=1, column=0, sticky="ew", pady=(4, 0)
        )

        actions = ttk.Frame(header, style="Chrome.TFrame", padding=(0, 13, 18, 13))
        actions.grid(row=0, column=2, sticky="e")
        self._header_button(actions, "选择工作区", self._choose_workspace).grid(row=0, column=0)
        self._header_button(actions, "新建案件", self._create_case).grid(row=0, column=1, padx=(7, 0))
        self._header_button(actions, "导入文件", self._choose_import_files, primary=True).grid(
            row=0, column=2, padx=(7, 0)
        )

        body = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL, style="Main.TPanedwindow")
        body.grid(row=1, column=0, sticky="nsew")

        sidebar = ttk.Frame(body, style="Sidebar.TFrame", width=285, padding=(15, 15, 14, 14))
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(2, weight=1)
        side_heading = ttk.Frame(sidebar, style="Sidebar.TFrame")
        side_heading.grid(row=0, column=0, sticky="ew")
        side_heading.columnconfigure(0, weight=1)
        ttk.Label(side_heading, text="案件目录", style="SidebarTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(side_heading, textvariable=self.case_count_var, style="SidebarSub.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(
            sidebar,
            text="按案件浏览材料；导入、分析、脱敏和还原都只在本机完成。",
            style="SidebarSub.TLabel",
            wraplength=250,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 11))
        self.case_tree = CaseTree(sidebar, on_select=self._on_tree_select)
        self.case_tree.grid(row=2, column=0, sticky="nsew")
        sidebar_bottom = ttk.Frame(sidebar, style="Sidebar.TFrame", padding=(0, 14, 0, 0))
        sidebar_bottom.grid(row=3, column=0, sticky="ew")
        tk.Frame(sidebar_bottom, height=1, background="#40515E").grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(sidebar_bottom, text="处理引擎", style="Section.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(
            sidebar_bottom,
            textvariable=self.engine_var,
            style="SidebarSub.TLabel",
            wraplength=245,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(5, 10))
        self._sidebar_button(sidebar_bottom, "批量解锁 PDF", self._choose_locked_pdfs).grid(
            row=3, column=0, sticky="ew"
        )
        body.add(sidebar, weight=1)

        content = ttk.Frame(body, style="Main.TFrame", padding=(22, 17, 22, 14))
        content.grid_propagate(False)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)
        title_line = ttk.Frame(content, style="Main.TFrame")
        title_line.grid(row=0, column=0, sticky="ew")
        title_line.columnconfigure(0, weight=1)
        ttk.Label(title_line, text="当前案件", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(title_line, text="本地处理 · 不上传案卷", style="Status.TLabel").grid(row=0, column=1, sticky="e")
        ttk.Label(title_line, textvariable=self.case_title_var, style="CaseTitle.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(3, 0)
        )

        controls = ttk.Frame(content, style="Toolbar.TFrame", padding=(0, 11, 0, 8))
        controls.grid(row=1, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        ttk.Label(controls, textvariable=self.document_title_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(controls, text="查看：", style="Status.TLabel").grid(row=0, column=1, sticky="e", padx=(18, 4))
        self.page_box = ttk.Combobox(
            controls,
            textvariable=self.page_var,
            values=("全部页面",),
            state="readonly",
            width=12,
            style="Page.TCombobox",
        )
        self.page_box.grid(row=0, column=2, sticky="e")
        self.page_box.bind("<<ComboboxSelected>>", lambda _event: self._render_preview())
        ttk.Checkbutton(
            controls,
            text="查看还原结果",
            variable=self.show_restored_var,
            command=self._render_preview,
        ).grid(row=0, column=3, sticky="e", padx=(10, 0))
        actions_bar = ttk.Frame(content, style="Toolbar.TFrame")
        actions_bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        actions_bar.columnconfigure(0, weight=1)
        ttk.Label(actions_bar, textvariable=self.banner_var, style="Warning.TLabel", wraplength=760).grid(
            row=0, column=0, sticky="w"
        )
        action_row = ttk.Frame(actions_bar, style="Toolbar.TFrame")
        action_row.grid(row=0, column=1, sticky="e")
        self._action(action_row, "分析敏感信息", self._analyze, "Accent.TButton").grid(row=0, column=0)
        self._action(action_row, "应用脱敏", self._apply, "Quiet.TButton").grid(row=0, column=1, padx=(7, 0))
        self._action(action_row, "还原", self._restore, "Quiet.TButton").grid(row=0, column=2, padx=(7, 0))
        self._action(action_row, "导出", self._export, "Quiet.TButton").grid(row=0, column=3, padx=(7, 0))
        self._action(action_row, "设置", self._open_settings, "Quiet.TButton").grid(row=0, column=4, padx=(7, 0))

        review = ttk.PanedWindow(content, orient=tk.VERTICAL, style="Review.TPanedwindow")
        review.grid(row=3, column=0, sticky="nsew")
        previews = ttk.PanedWindow(review, orient=tk.HORIZONTAL, style="Review.TPanedwindow")
        self.original_preview = PreviewPane(
            previews,
            kicker="ORIGINAL DOCUMENT",
            title="原文页",
            subtitle="模型与中文规则识别到的内容会以高亮标出。",
            badge="隐私标记",
            badge_style="amber",
            on_tag_click=self._on_original_tag,
        )
        self.redacted_preview = PreviewPane(
            previews,
            kicker="REDACTED DOCUMENT",
            title="脱敏页",
            subtitle="应用脱敏后，在这里核对占位符与上下文。",
            badge="脱敏预览",
            badge_style="blue",
        )
        previews.add(self.original_preview.frame, weight=1)
        previews.add(self.redacted_preview.frame, weight=1)
        review.add(previews, weight=5)

        notebook = ttk.Notebook(review)
        rules_tab = ttk.Frame(notebook, style="Paper.TFrame")
        self.rules_panel = RulesPanel(
            rules_tab,
            on_select=self._on_rule_selected,
            on_add=self._add_rule,
            on_edit=self._edit_rule,
            on_delete=self._delete_rule,
            on_toggle=self._toggle_rule,
            on_reset=self._reset_rule,
        )
        self.rules_panel.pack(fill="both", expand=True)
        notebook.add(rules_tab, text="规则清单")
        summary_tab = ttk.Frame(notebook, style="Paper.TFrame")
        summary_tab.columnconfigure(0, weight=1)
        summary_tab.rowconfigure(0, weight=1)
        self.summary_text = tk.Text(
            summary_tab,
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=12,
            font=FONT_UI_SMALL,
            background=PALETTE["paper"],
            foreground=PALETTE["text"],
            state="disabled",
        )
        summary_scroll = ttk.Scrollbar(
            summary_tab,
            orient="vertical",
            command=self.summary_text.yview,
            style="Paper.Vertical.TScrollbar",
        )
        self.summary_text.configure(yscrollcommand=summary_scroll.set)
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        summary_scroll.grid(row=0, column=1, sticky="ns")
        notebook.add(summary_tab, text="分析摘要")
        review.add(notebook, weight=2)
        body.add(content, weight=6)

        footer = ttk.Frame(self.root, style="Footer.TFrame", padding=(20, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Footer.TLabel", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Label(footer, text="导入 / OCR / 分析", style="FooterMeta.TLabel").grid(row=0, column=1, padx=(14, 7))
        self.progress_bar = ttk.Progressbar(
            footer,
            variable=self.progress_value,
            maximum=100,
            length=230,
            mode="determinate",
            style="Case.Horizontal.TProgressbar",
        )
        self.progress_bar.grid(row=0, column=2, sticky="e", padx=(0, 10))
        self.cancel_button = ttk.Button(
            footer,
            text="取消任务",
            command=self.job.cancel,
            style="Chrome.TButton",
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=3, sticky="e")

    def _header_button(self, parent: ttk.Frame, text: str, command: Any, *, primary: bool = False) -> ttk.Button:
        button = ttk.Button(
            parent,
            text=text,
            command=command,
            style="ChromePrimary.TButton" if primary else "Chrome.TButton",
        )
        self._action_buttons.append(button)
        return button

    def _sidebar_button(self, parent: ttk.Frame, text: str, command: Any) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style="Sidebar.TButton")
        self._action_buttons.append(button)
        return button

    def _action(self, parent: ttk.Frame, text: str, command: Any, style: str) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command, style=style)
        self._action_buttons.append(button)
        return button

    # ------------------------------------------------------------- workspace
    def _install_window_icon(self) -> None:
        """Set a real window/taskbar icon instead of Tk's default feather."""
        try:
            png_resource = files("jianyin_app").joinpath("assets").joinpath("jianyin.png")
            with as_file(png_resource) as png_path:
                image = tk.PhotoImage(file=str(png_path))
            self.root.iconphoto(True, image)
            self._icon_photo = image
        except Exception:
            self._icon_photo = None
        try:
            ico_resource = files("jianyin_app").joinpath("assets").joinpath("jianyin.ico")
            with as_file(ico_resource) as ico_path:
                self.root.iconbitmap(default=str(ico_path))
                self.root.iconbitmap(str(ico_path))
        except Exception:
            try:
                self.logger.warning("window_icon_failed")
            except Exception:
                pass
        try:
            self.root.iconname("笺隐")
        except tk.TclError:
            pass

    def _configure_logging(self) -> None:
        self.logger = logging.getLogger("jianyin.gui")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if self.logger.handlers:
            return
        try:
            log_dir = self.workspace.root / "logs"
            ensure_dir(log_dir)
            handler = RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self.logger.addHandler(handler)
        except Exception:
            pass

    def _load_policy(self, *, initial: bool = False) -> RuleSet:
        path = self.settings.policy_path
        if path:
            try:
                return RuleSet.from_path(path)
            except JianYinError as error:
                if initial:
                    self._startup_warnings.append(f"策略规则无法读取，已使用内置规则：{error}")
                else:
                    messagebox.showwarning("规则文件无效", str(error), parent=self.root)
        return default_ruleset()

    def _update_engine_status(self) -> None:
        model_value = self.settings.model_dir or "项目 models/ 或本机缓存"
        chinese_enabled = len(self.settings.chinese.enabled_rule_ids())
        self.engine_var.set(
            f"Q4 ONNX · CPU\n模型：{model_value}\n中文补强：{chinese_enabled} 项\n策略：{self.ruleset.name}"
        )

    def _refresh_tree(self, *, select_case: str | None = None, select_document: str | None = None) -> None:
        try:
            cases = self.workspace.list_cases()
        except Exception as error:
            self._show_error(error)
            return
        self.case_count_var.set(f"{len(cases)} 个案件")
        self.case_tree.refresh(cases, select_case=select_case, select_document=select_document)
        if select_case:
            self._on_tree_select(select_case, select_document)
        elif self.current_case_id is None:
            self._clear_all()
        self._update_case_title()

    def _on_tree_select(self, case_id: str | None, document_id: str | None) -> None:
        if not case_id:
            self._clear_all()
            return
        try:
            case = self.workspace.get_case(case_id)
        except Exception as error:
            self._show_error(error)
            return
        self.current_case_id = case_id
        self.current_case = case
        self.current_document_id = document_id
        self._load_draft_and_mapping(case_id)
        if document_id:
            self._load_document(case_id, document_id)
            self.logger.info("document_selected case=%s document=%s", case_id, document_id)
        else:
            self._clear_document("请选择该案件下的文件，以查看原文与脱敏结果。")
        self._update_case_title()
        self._update_summary()

    def _load_draft_and_mapping(self, case_id: str) -> None:
        self.current_draft = None
        self.current_mapping = None
        if self.workspace.draft_path(case_id).is_file():
            try:
                self.current_draft = self.workspace.read_draft(case_id)
            except Exception as error:
                self._set_status(f"规则草稿无法读取：{error}")
        if self.workspace.mapping_path(case_id).is_file():
            try:
                self.current_mapping = self.workspace.read_mapping(case_id)
            except Exception as error:
                self._set_status(f"映射文件无法读取：{error}")
        candidates = self.current_draft.candidates if self.current_draft else []
        self.rules_panel.set_candidates(candidates)
        self._update_summary()

    def _load_document(self, case_id: str, document_id: str) -> None:
        try:
            document = self.workspace.get_document(case_id, document_id)
            original = self.workspace.read_document_text(case_id, document_id)
        except Exception as error:
            self._show_error(error)
            return
        self.current_document = document
        self.current_original_text = original
        self.current_redacted_text = self._read_optional(case_id, document.get("redacted_path"))
        self.current_restored_text = self._read_optional(case_id, document.get("restored_path"))
        self.current_page_ranges = self._page_ranges(original)
        values = ["全部页面"] + [page_label(item.number) for item in self.current_page_ranges]
        self.page_box.configure(values=values)
        self.page_var.set("全部页面")
        self.document_title_var.set(
            f"{document.get('display_name', '未命名文件')} · {document.get('extraction_method', 'text')} · "
            f"{document.get('page_count', 1)} 页"
        )
        self._render_preview()

    def _read_optional(self, case_id: str, relative_path: Any) -> str:
        if not isinstance(relative_path, str):
            return ""
        path = self.workspace.resolve_case_path(case_id, relative_path)
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ""

    def _clear_document(self, message: str = "未选择文件") -> None:
        self.current_document_id = None
        self.current_document = None
        self.current_original_text = ""
        self.current_redacted_text = ""
        self.current_restored_text = ""
        self.current_page_ranges = []
        self.document_title_var.set(message)
        self.page_box.configure(values=("全部页面",))
        self.page_var.set("全部页面")
        self.original_preview.clear(message)
        self.redacted_preview.clear("尚未生成本案的脱敏结果。")

    def _clear_all(self) -> None:
        self.current_case_id = None
        self.current_case = None
        self.current_draft = None
        self.current_mapping = None
        self.case_title_var.set("请选择或创建一个案件")
        self.rules_panel.set_candidates([])
        self._set_summary("尚未选择案件。")
        self._clear_document("未选择文件")
        self._update_banner()

    # --------------------------------------------------------------- preview
    @staticmethod
    def _page_ranges(text: str) -> list[Any]:
        from ..documents.markdown import page_ranges

        return page_ranges(text)

    def _selected_page_number(self) -> int | None:
        value = self.page_var.get()
        if value == "全部页面":
            return None
        match = _PAGE_LABEL_RE.match(value)
        return int(match.group(1)) if match else None

    def _page_slice(self, text: str, page_number: int | None) -> tuple[int, int]:
        if page_number is None or not text:
            return 0, len(text)
        for item in self._page_ranges(text):
            if item.number == page_number:
                return item.start, item.end
        return 0, len(text)

    def _render_preview(self) -> None:
        if not self.current_document or not self.current_original_text:
            return
        page_number = self._selected_page_number()
        start, end = self._page_slice(self.current_original_text, page_number)
        original = self.current_original_text[start:end]
        highlights: list[tuple[int, int, str]] = []
        if self.current_draft is not None:
            for candidate in self.current_draft.candidates:
                if not candidate.enabled:
                    continue
                tag = f"rule_{candidate.id}"
                color = self._category_color(candidate.category)
                self.original_preview.ensure_tag(tag, background=color, foreground=_ACCENT_WHITE, underline=True)
                for occurrence in candidate.occurrences:
                    if occurrence.document_id == self.current_document_id:
                        highlights.append((occurrence.start, occurrence.end, tag))
        elif self.current_mapping is not None:
            for record in self.current_mapping.get("mappings", []):
                if not isinstance(record, Mapping):
                    continue
                tag = f"map_{record.get('id', 0)}"
                self.original_preview.ensure_tag(tag, background=PALETTE["accent_soft"], underline=True)
                for occurrence in record.get("occurrences", []):
                    if isinstance(occurrence, Mapping) and occurrence.get("document_id") == self.current_document_id:
                        if isinstance(occurrence.get("source_start"), int) and isinstance(occurrence.get("source_end"), int):
                            highlights.append(
                                (int(occurrence["source_start"]), int(occurrence["source_end"]), tag)
                            )
        clipped = clip_highlights(highlights, base_offset=start, length=len(original))
        self.original_preview.set_content(original, clipped, base_offset=start)

        if self.show_restored_var.get() and self.current_restored_text:
            redacted_start, redacted_end = self._page_slice(self.current_restored_text, page_number)
            self.redacted_preview.set_content(
                self.current_restored_text[redacted_start:redacted_end],
                [],
                base_offset=redacted_start,
            )
            self.redacted_preview.set_subtitle("按本案映射还原的审阅文本；原始文件未被修改。")
            self.redacted_preview.set_badge("还原预览")
            return
        if not self.current_redacted_text:
            self.redacted_preview.clear("尚未生成本案的脱敏结果。")
            self.redacted_preview.set_subtitle("应用脱敏后，在这里核对占位符与上下文。")
            self.redacted_preview.set_badge("脱敏预览")
            return
        redacted_start, redacted_end = self._page_slice(self.current_redacted_text, page_number)
        redacted_slice = self.current_redacted_text[redacted_start:redacted_end]
        redacted_highlights: list[tuple[int, int, str]] = []
        if self.current_mapping is not None:
            self.redacted_preview.ensure_tag(
                "redacted_hit",
                background=PALETTE["redact_soft"],
                foreground=PALETTE["redact"],
                underline=True,
            )
            for record in self.current_mapping.get("mappings", []):
                if not isinstance(record, Mapping):
                    continue
                for occurrence in record.get("occurrences", []):
                    if isinstance(occurrence, Mapping) and occurrence.get("document_id") == self.current_document_id:
                        if isinstance(occurrence.get("redacted_start"), int) and isinstance(occurrence.get("redacted_end"), int):
                            redacted_highlights.append(
                                (
                                    int(occurrence["redacted_start"]),
                                    int(occurrence["redacted_end"]),
                                    "redacted_hit",
                                )
                            )
        clipped_redacted = clip_highlights(
            redacted_highlights,
            base_offset=redacted_start,
            length=len(redacted_slice),
        )
        self.redacted_preview.set_content(redacted_slice, clipped_redacted, base_offset=redacted_start)
        self.redacted_preview.set_subtitle("占位符来自本案唯一映射；请逐条核对上下文。")
        self.redacted_preview.set_badge("脱敏预览")

    @staticmethod
    def _category_color(category: str) -> str:
        from ..model.labels import load_category_labels

        return load_category_labels().get(category, {}).get("color", PALETTE["accent"])

    def _on_original_tag(self, tag: str) -> None:
        if not tag.startswith("rule_"):
            return
        try:
            candidate_id = int(tag.split("_", 1)[1])
        except ValueError:
            return
        self.rules_panel.select_candidate(candidate_id)

    def _on_rule_selected(self, candidate: CandidateRule | None) -> None:
        if candidate is None or not self.current_document_id:
            return
        for occurrence in candidate.occurrences:
            if occurrence.document_id == self.current_document_id:
                self.original_preview.scroll_to(occurrence.start)
                break

    # ---------------------------------------------------------------- summary
    def _update_summary(self) -> None:
        lines: list[str] = []
        if self.current_case is None:
            self._set_summary("尚未选择案件。")
            return
        stale = is_mapping_stale(self.current_case, self.current_draft)
        lines.append(f"案件：{self.current_case.get('name', '')}")
        lines.append(f"状态：{case_status_label(self.current_case.get('status'), stale=stale)}")
        lines.append("")
        if self.current_draft is None:
            lines.append("尚未生成规则草稿。请点击“分析敏感信息”。")
        else:
            lines.append("规则草稿：")
            lines.append(format_summary(self.current_draft.summary))
            lines.append("")
            lines.append(f"规则条数：{len(self.current_draft.candidates)}")
        if self.current_mapping is not None:
            lines.append("")
            lines.append("最终映射：")
            lines.append(format_summary(self.current_mapping.get("summary", {})))
        self._set_summary("\n".join(lines))

    def _set_summary(self, text: str) -> None:
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", text)
        self.summary_text.configure(state="disabled")

    def _update_case_title(self) -> None:
        if self.current_case is None:
            self.case_title_var.set("请选择或创建一个案件")
            self._update_banner()
            return
        documents = self.current_case.get("documents") or []
        stale = is_mapping_stale(self.current_case, self.current_draft)
        self.case_title_var.set(
            f"{self.current_case.get('name', '未命名案件')}  ·  {len(documents)} 份材料  ·  "
            f"{case_status_label(self.current_case.get('status'), stale=stale)}"
        )
        self._update_banner()

    def _update_banner(self) -> None:
        stale = is_mapping_stale(self.current_case, self.current_draft) if self.current_case else False
        if self.current_case is None:
            self.banner_var.set("本地处理，不上传案卷。导出前请人工复核。")
        elif stale and self.current_draft is not None:
            self.banner_var.set("规则草稿已修改或尚未应用；当前映射可能过期。请重新应用脱敏。")
        elif self.current_mapping is None:
            self.banner_var.set("模型主要基于英文训练；中文规则为补强。导出前请逐条复核姓名、地址和日期。")
        else:
            self.banner_var.set("映射已生成。模型与中文规则都可能误报或漏报，导出前必须人工复核。")

    # --------------------------------------------------------------- actions
    def _require_case(self) -> str | None:
        if self.current_case_id:
            return self.current_case_id
        messagebox.showinfo("请选择案件", "请先在左侧选择案件，或新建一个案件。", parent=self.root)
        return None

    def _choose_workspace(self) -> None:
        chosen = filedialog.askdirectory(title="选择案件工作区", initialdir=str(self.workspace.root))
        if not chosen:
            return
        try:
            workspace = CaseWorkspace(chosen)
        except Exception as error:
            self._show_error(error)
            return
        self.workspace = workspace
        try:
            self.settings = workspace.settings
            self.settings.model_config().validate()
        except ConfigurationError:
            self.settings = WorkspaceSettings()
        self.workspace_var.set(str(self.workspace.root))
        self.current_case_id = None
        self.current_document_id = None
        self.current_case = None
        self.current_document = None
        self.current_draft = None
        self.current_mapping = None
        self.ruleset = self._load_policy()
        self._refresh_tree()
        self._update_engine_status()
        self._set_status("已切换案件工作区。")

    def _create_case(self) -> None:
        name = simpledialog.askstring("新建案件", "案件名称：", parent=self.root)
        if name is None:
            return
        try:
            case = self.workspace.create_case(name)
        except Exception as error:
            self._show_error(error)
            return
        self._refresh_tree(select_case=str(case["id"]))
        self._set_status("案件已创建，可导入案卷文件。")

    def _choose_import_files(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        selected = filedialog.askopenfilenames(title="导入案卷文件", filetypes=SUPPORTED_FILE_TYPES)
        if selected:
            self._start_import(case_id, selected, password=None)

    def _choose_locked_pdfs(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        selected = filedialog.askopenfilenames(title="选择同一密码的 PDF", filetypes=(("PDF 文件", "*.pdf"),))
        if not selected:
            return
        password = simpledialog.askstring(
            "批量解锁 PDF",
            "请输入这些 PDF 共用的密码：",
            show="*",
            parent=self.root,
        )
        if password is None:
            return
        self._start_import(case_id, selected, password=password)

    def _start_import(self, case_id: str, selected: Sequence[str], password: str | None) -> None:
        self._reset_progress()
        self._set_running(True, f"正在本地导入 {len(selected)} 个文件；扫描 PDF 会自动 OCR。")
        workspace = self.workspace

        def job() -> ImportOutcome:
            return workspace.import_documents(
                case_id,
                list(selected),
                password=password,
                progress=self.job.progress,
                cancel=self.job.is_cancelled,
            )

        if not self.job.start("import", job):
            self._set_running(False)

    def _build_detector(self) -> CompositeDetector:
        model = OnnxPrivacyFilter(self.settings.model_config())
        chinese = ChineseRuleDetector(self.settings.chinese)
        return CompositeDetector(model, chinese, options=self.settings.detection_options())

    def _analyze(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        try:
            case = self.workspace.get_case(case_id)
        except Exception as error:
            self._show_error(error)
            return
        if not case.get("documents"):
            messagebox.showinfo("暂无材料", "请先导入至少一个文件。", parent=self.root)
            return
        preserve = True
        if self.current_draft is not None:
            answer = messagebox.askyesnocancel(
                "重新分析",
                "当前案件已有规则草稿。\n\n"
                "是：保留手工规则和已编辑替换值\n"
                "否：重新生成全部规则\n"
                "取消：不分析",
                parent=self.root,
            )
            if answer is None:
                return
            preserve = bool(answer)
        try:
            detector = self._build_detector()
        except Exception as error:
            self._show_error(error)
            return
        self._reset_progress()
        self._set_running(True, "正在加载本地模型并分析案件。")
        workspace = self.workspace
        rules = self.ruleset
        options = self.settings.detection_options()

        def job() -> Draft:
            return analyze_case(
                workspace,
                case_id,
                detector,
                rules,
                detection_options=options,
                preserve_existing=preserve,
                progress=self.job.progress,
                cancel=self.job.is_cancelled,
            )

        if not self.job.start("analyze", job):
            self._set_running(False)

    def _apply(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        if self.current_draft is None:
            messagebox.showinfo("尚无规则", "请先点击“分析敏感信息”生成规则草稿。", parent=self.root)
            return
        if self.workspace.mapping_path(case_id).is_file():
            if not messagebox.askyesno(
                "覆盖脱敏结果",
                "当前案件已有映射和脱敏文本。重新应用将归档旧映射并覆盖脱敏输出，是否继续？",
                parent=self.root,
            ):
                return
        self._reset_progress()
        self._set_running(True, "正在应用规则并生成案件级映射。")
        workspace = self.workspace
        draft = self.current_draft
        export_docx_enabled = self.settings.export_docx

        def job() -> Any:
            return apply_case(
                workspace,
                case_id,
                draft,
                export_docx_enabled=export_docx_enabled,
                progress=self.job.progress,
                cancel=self.job.is_cancelled,
            )

        if not self.job.start("apply", job):
            self._set_running(False)

    def _restore(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        if not self.workspace.mapping_path(case_id).is_file():
            messagebox.showinfo("尚无映射", "请先应用脱敏，生成案件映射。", parent=self.root)
            return
        if not messagebox.askyesno(
            "还原当前案件",
            "将按本案映射还原脱敏文本；若脱敏文本被手工修改，操作会安全拒绝。是否继续？",
            parent=self.root,
        ):
            return
        self._reset_progress()
        self._set_running(True, "正在校验映射并还原案件文本。")
        workspace = self.workspace

        def job() -> dict[str, str]:
            return restore_case(
                workspace,
                case_id,
                export_docx_enabled=self.settings.export_docx,
                progress=self.job.progress,
                cancel=self.job.is_cancelled,
            )

        if not self.job.start("restore", job):
            self._set_running(False)

    def _export(self) -> None:
        case_id = self._require_case()
        if not case_id:
            return
        if self.current_document_id is None:
            messagebox.showinfo("请选择文件", "请先选择一个已脱敏文件。", parent=self.root)
            return
        if not self.workspace.redacted_text_path(case_id, self.current_document_id).is_file():
            messagebox.showinfo("尚无脱敏结果", "请先应用脱敏。", parent=self.root)
            return
        try:
            case = self.workspace.get_case(case_id)
        except Exception as error:
            self._show_error(error)
            return
        dialog = ExportDialog(
            self.root,
            default_dir=default_workspace_directory().parent / "JianYin Exports",
            current_name=str(self.current_document.get("display_name", "当前文档")) if self.current_document else "当前文档",
        )
        result = dialog.show()
        if result is None:
            return
        document_ids = (
            [str(self.current_document_id)]
            if result["scope"] == "current"
            else [str(document["id"]) for document in case.get("documents", [])]
        )
        try:
            exported = export_documents(
                self.workspace,
                case_id,
                document_ids,
                result["target_dir"],
                include_md=result["include_md"],
                include_docx=result["include_docx"],
                include_mapping=result["include_mapping"],
            )
        except Exception as error:
            self._show_error(error)
            return
        self._set_status(f"已导出 {len(exported)} 个文件。")
        messagebox.showinfo("导出完成", format_paths(exported, limit=6), parent=self.root)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.root, self.settings)
        result = dialog.show()
        if result is None:
            return
        try:
            self.workspace.save_settings(result)
        except Exception as error:
            self._show_error(error)
            return
        self.settings = result
        self.ruleset = self._load_policy()
        self._update_engine_status()
        if self.current_draft is not None and self.current_case_id:
            self.workspace.update_case(self.current_case_id, status="analyzed", draft_sha256=self.current_draft.digest)
            self.current_case = self.workspace.get_case(self.current_case_id)
        self._update_case_title()
        self._update_summary()
        self._set_status("设置已保存。模型、规则或中文开关变化后请重新分析。")

    # ------------------------------------------------------------- rule edits
    def _factory(self, *, exclude_id: int | None = None) -> TargetFactory:
        existing = []
        if self.current_draft is not None:
            existing = [
                (candidate.category, candidate.source, candidate.target)
                for candidate in self.current_draft.candidates
                if candidate.target and candidate.id != exclude_id
            ]
        return TargetFactory(self.ruleset, existing=existing)

    def _ensure_draft(self) -> Draft | None:
        if self.current_draft is None:
            messagebox.showinfo("尚无规则", "请先分析案件，生成规则草稿。", parent=self.root)
            return None
        return self.current_draft

    def _add_rule(self) -> None:
        draft = self._ensure_draft()
        if draft is None or not self.current_case_id:
            return
        selection = self.original_preview.selection_range()
        source = ""
        if selection is not None:
            source = self.current_original_text[selection[0] : selection[1]]
            if "\n" in source or "\r" in source:
                messagebox.showinfo("选择范围", "请选择单行文本作为规则原文。", parent=self.root)
                return
        category = "private_person"
        if source:
            existing = next(
                (candidate for candidate in draft.candidates if candidate.source == source),
                None,
            )
            if existing is not None:
                self._edit_rule(existing)
                return
        try:
            target = self._factory().target_for(category, source) if source else ""
        except Exception:
            target = ""
        dialog = RuleDialog(
            self.root,
            source=source,
            category=category,
            target=target,
            editing=False,
        )
        result = dialog.show()
        if result is None:
            return
        source_value = result["source"]
        if not source_value:
            return
        try:
            documents = self.workspace.document_texts(self.current_case_id)
        except Exception as error:
            self._show_error(error)
            return
        literal_count = count_literal_occurrences(documents, source_value, result["match_mode"])
        if literal_count == 0:
            if not messagebox.askyesno(
                "未找到原文",
                "当前案件的全部文档中没有找到这段文本。仍要添加为规则吗？",
                parent=self.root,
            ):
                return
        candidate = CandidateRule(
            id=max((item.id for item in draft.candidates), default=0) + 1,
            category=result["category"],
            subtype=result.get("subtype"),
            source=source_value,
            target=result["target"],
            enabled=result["enabled"],
            target_edited=bool(result["target"]),
            apply_all=result["apply_all"],
            match_mode=result["match_mode"],
            detection_sources=["manual"],
            detected_count=0,
            literal_count=literal_count,
            note=result["note"],
            occurrences=[],
        )
        if not candidate.target:
            try:
                candidate.target = self._factory().target_for(candidate.category, candidate.source)
            except Exception as error:
                self._show_error(error)
                return
        draft.candidates.append(candidate)
        self._save_draft()
        self.rules_panel.select_candidate(candidate.id)
        self._set_status(f"已添加手工规则：{candidate.source[:20]}")

    def _edit_rule(self, candidate: CandidateRule | None) -> None:
        draft = self._ensure_draft()
        if draft is None or candidate is None:
            return
        dialog = RuleDialog(
            self.root,
            candidate=candidate,
            source=candidate.source,
            category=candidate.category,
            subtype=candidate.subtype,
            target=candidate.target,
            editing=True,
        )
        result = dialog.show()
        if result is None:
            return
        category = result["category"]
        if category != candidate.category:
            duplicate = next(
                (
                    item
                    for item in draft.candidates
                    if item.id != candidate.id and item.category == category and item.source == candidate.source
                ),
                None,
            )
            if duplicate is not None:
                messagebox.showwarning("规则重复", "该类别下已存在相同原文的规则。", parent=self.root)
                return
        target = result["target"]
        if target != candidate.target:
            candidate.target_edited = True
        if not target:
            try:
                target = self._factory().target_for(category, candidate.source)
            except Exception as error:
                self._show_error(error)
                return
        candidate.category = category
        candidate.target = target
        candidate.enabled = result["enabled"]
        candidate.apply_all = result["apply_all"]
        candidate.match_mode = result["match_mode"]
        candidate.note = result["note"]
        candidate.subtype = result.get("subtype") if result.get("subtype") else candidate.subtype
        self._save_draft()
        self._set_status("规则已更新；请重新应用脱敏以生成新映射。")

    def _delete_rule(self, candidate: CandidateRule | None) -> None:
        draft = self._ensure_draft()
        if draft is None or candidate is None:
            return
        if not messagebox.askyesno("删除规则", "确定删除这条规则吗？", parent=self.root):
            return
        draft.candidates = [item for item in draft.candidates if item.id != candidate.id]
        self._save_draft()
        self._set_status("规则已删除。")

    def _toggle_rule(self, candidate: CandidateRule | None) -> None:
        draft = self._ensure_draft()
        if draft is None or candidate is None:
            return
        candidate.enabled = not candidate.enabled
        self._save_draft()

    def _reset_rule(self, candidate: CandidateRule | None) -> None:
        draft = self._ensure_draft()
        if draft is None or candidate is None:
            return
        try:
            candidate.target = self._factory(exclude_id=candidate.id).target_for(candidate.category, candidate.source)
        except Exception as error:
            self._show_error(error)
            return
        candidate.target_edited = False
        self._save_draft()
        self._set_status("已按当前策略重新生成替换值。")

    def _save_draft(self) -> None:
        draft = self.current_draft
        case_id = self.current_case_id
        if draft is None or not case_id:
            return
        try:
            documents = self.workspace.document_texts(case_id)
        except Exception as error:
            self._show_error(error)
            return
        for candidate in draft.candidates:
            candidate.literal_count = count_literal_occurrences(documents, candidate.source, candidate.match_mode)
        by_category: dict[str, int] = {}
        for candidate in draft.candidates:
            by_category[candidate.category] = by_category.get(candidate.category, 0) + candidate.detected_count
        draft.summary.update(
            {
                "document_count": len(documents),
                "candidate_rule_count": len(draft.candidates),
                "literal_occurrence_count": sum(candidate.literal_count for candidate in draft.candidates),
                "by_category": dict(sorted(by_category.items())),
            }
        )
        try:
            self.workspace.write_draft(case_id, draft)
            self.workspace.update_case(case_id, status="analyzed", draft_sha256=draft.digest)
            self.current_case = self.workspace.get_case(case_id)
        except Exception as error:
            self._show_error(error)
            return
        self.rules_panel.set_candidates(draft.candidates)
        self._update_case_title()
        self._update_summary()
        self._render_preview()

    # ------------------------------------------------------------------ jobs
    def _on_job_event(self, status: str, kind: str, payload: Any) -> None:
        if status == "progress":
            self._handle_progress(kind, payload)
            return
        self._set_running(False)
        if status == "error":
            if isinstance(payload, OperationCancelled):
                self._set_status("操作已取消；未写入新的结果。")
                return
            self._show_error(payload)
            return
        self._handle_success(kind, payload)

    def _ensure_document_selected(self) -> None:
        if self.current_document_id or not self.current_case_id:
            return
        try:
            case = self.workspace.get_case(self.current_case_id)
        except Exception:
            return
        documents = case.get("documents") or []
        if documents:
            self.current_document_id = str(documents[0]["id"])

    def _handle_success(self, kind: str, payload: Any) -> None:
        if kind == "import":
            outcome: ImportOutcome = payload
            first = outcome.imported[0]["id"] if outcome.imported else None
            self._refresh_tree(select_case=self.current_case_id, select_document=first)
            self._set_status(f"导入完成：成功 {len(outcome.imported)} 个，未导入 {len(outcome.failures)} 个。")
            if outcome.failures:
                codes = "、".join(sorted({failure.code for failure in outcome.failures}))
                messagebox.showwarning(
                    "部分文件未导入",
                    f"成功 {len(outcome.imported)} 个；{len(outcome.failures)} 个未导入。\n错误类型：{codes}",
                    parent=self.root,
                )
            return
        if kind == "analyze":
            draft: Draft = payload
            self.current_draft = draft
            self._ensure_document_selected()
            self._refresh_tree(select_case=self.current_case_id, select_document=self.current_document_id)
            self.rules_panel.set_candidates(draft.candidates)
            self._update_summary()
            self._update_case_title()
            self._render_preview()
            summary = draft.summary
            self._set_status(
                f"分析完成：{summary.get('candidate_rule_count', 0)} 条候选规则，"
                f"识别 {summary.get('detected_span_count', 0)} 处。"
            )
            messagebox.showinfo(
                "分析完成",
                "已生成规则草稿。请在“规则清单”中审阅、修改或添加规则，再应用脱敏。\n\n"
                "模型主要基于英文训练，中文姓名和地址请重点复核。",
                parent=self.root,
            )
            return
        if kind == "apply":
            application = payload
            self._ensure_document_selected()
            self._refresh_tree(select_case=self.current_case_id, select_document=self.current_document_id)
            self.current_draft = self.workspace.read_draft(self.current_case_id) if self.current_case_id else None
            self.current_mapping = self.workspace.read_mapping(self.current_case_id) if self.current_case_id else None
            self._update_case_title()
            self._update_summary()
            self._render_preview()
            summary = application.summary
            self._set_status(
                f"脱敏完成：{summary.get('applied_rule_count', 0)} 条规则，"
                f"{summary.get('applied_occurrence_count', 0)} 处命中；映射已保存。"
            )
            messagebox.showinfo(
                "脱敏完成",
                "已生成脱敏 Markdown、可选 DOCX 和案件级映射 JSON。\n"
                "映射包含原始敏感值，请仅保存在受控位置；导出前请人工复核。",
                parent=self.root,
            )
            return
        if kind == "restore":
            restored = payload
            self._ensure_document_selected()
            self._refresh_tree(select_case=self.current_case_id, select_document=self.current_document_id)
            self._update_case_title()
            self._update_summary()
            self.current_document = (
                self.workspace.get_document(self.current_case_id, self.current_document_id)
                if self.current_case_id and self.current_document_id
                else None
            )
            if self.current_case_id and self.current_document_id:
                self._load_document(self.current_case_id, self.current_document_id)
            self._set_status(f"还原完成：{len(restored)} 个文档；原始文件未被修改。")
            messagebox.showinfo("还原完成", "已按映射生成还原后的审阅文本。", parent=self.root)

    def _handle_progress(self, kind: str, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        event = dict(payload)
        stage = event.get("stage")
        if stage == "model_download":
            self._set_status("正在准备本地 Q4 ONNX 模型。")
            return
        if kind == "import":
            total_files = event.get("total_files")
            file_index = event.get("file_index")
            if isinstance(total_files, int) and total_files > 0 and isinstance(file_index, int):
                base = (file_index - 1) / total_files * 100
                if stage in {"file_started", "file_finished", "file_failed"}:
                    fraction = 0 if stage == "file_started" else 1
                else:
                    total_pages = event.get("total_pages")
                    completed = event.get("completed_pages")
                    fraction = (
                        min(max(completed, 0), total_pages) / total_pages
                        if isinstance(total_pages, int) and total_pages > 0 and isinstance(completed, int)
                        else 0
                    )
                self.progress_value.set(base + fraction * 100 / total_files)
                if stage == "file_started":
                    self._set_status(f"正在导入第 {file_index}/{total_files} 个文件。")
                elif stage in {"ocr_progress", "ocr_started", "ocr_finished"}:
                    total_pages = event.get("total_pages")
                    completed = event.get("completed_pages")
                    if isinstance(total_pages, int) and isinstance(completed, int):
                        self._set_status(
                            f"OCR 第 {file_index}/{total_files} 个文件：{completed}/{total_pages} 页。"
                        )
            return
        document_count = event.get("document_count")
        document_index = event.get("document_index")
        if isinstance(document_count, int) and document_count > 0 and isinstance(document_index, int):
            base = (document_index - 1) / document_count * 100
            if stage == "model_window":
                window_count = event.get("window_count")
                window_index = event.get("window_index")
                fraction = (
                    min(max(window_index, 0), window_count) / window_count
                    if isinstance(window_count, int) and window_count > 0 and isinstance(window_index, int)
                    else 0
                )
                self.progress_value.set(base + fraction * 100 / document_count)
                self._set_status(f"正在分析第 {document_index}/{document_count} 份；模型窗口 {window_index}/{window_count}。")
            elif stage == "document_start":
                self.progress_value.set(base)
                self._set_status(f"正在分析第 {document_index}/{document_count} 份文档。")
            elif stage == "document_finished":
                self.progress_value.set(base + 100 / document_count)
            elif stage == "apply_document":
                self.progress_value.set(base + 50 / document_count)
                self._set_status(f"正在写入第 {document_index}/{document_count} 份脱敏结果。")
            elif stage == "restore_document":
                self.progress_value.set(base + 50 / document_count)
                self._set_status(f"正在校验并还原第 {document_index}/{document_count} 份文档。")
        if stage in {"apply_finished", "restore_finished", "analysis_finished"}:
            self.progress_value.set(100)

    def _set_running(self, running: bool, status: str | None = None) -> None:
        self.running = running
        for button in self._action_buttons:
            try:
                button.configure(state="disabled" if running else "normal")
            except tk.TclError:
                pass
        try:
            self.cancel_button.configure(state="normal" if running else "disabled")
        except tk.TclError:
            pass
        if not running:
            self.progress_bar.stop()
        if status:
            self._set_status(status)

    def _reset_progress(self) -> None:
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_value.set(0.0)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _show_error(self, error: BaseException) -> None:
        code = getattr(error, "code", type(error).__name__)
        message = str(error) if isinstance(error, JianYinError) else "操作未完成；未写入额外的敏感内容。"
        try:
            self.logger.error("job_error code=%s type=%s", code, type(error).__name__)
        except Exception:
            pass
        self._set_status("任务未完成。请检查模型、文件和工作区设置。")
        messagebox.showerror("操作未完成", f"{message}\n\n错误类型：{code}", parent=self.root)

    def _on_close(self) -> None:
        if self.job.running:
            if not messagebox.askyesno("任务正在运行", "当前任务尚未完成，确定退出吗？", parent=self.root):
                return
            self.job.cancel()
        self.job.shutdown()
        self.root.destroy()


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _startup_log_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "JianYin" / "logs" / "startup.log"


def _set_app_user_model_id() -> None:
    """Give the Python process its own Windows taskbar identity."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JianYin.Desktop.0.1")
    except Exception:
        pass


def main() -> None:
    _enable_dpi_awareness()
    _set_app_user_model_id()
    try:
        root = tk.Tk()
        JianYinApp(root)
        root.mainloop()
    except Exception as error:
        try:
            path = _startup_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        except Exception:
            pass
        try:
            messagebox.showerror(
                "笺隐启动失败",
                "图形界面无法启动。\n\n"
                f"错误类型：{type(error).__name__}\n"
                "请检查 .venv 与模型目录，或查看 %LOCALAPPDATA%\\JianYin\\logs\\startup.log。",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
