"""Visual language for the 笺隐 desktop workspace."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTE = {
    "ink": "#17202A",
    "ink_alt": "#1D2935",
    "ink_light": "#2B3D4B",
    "paper": "#FBF8F2",
    "paper_deep": "#F3EEE4",
    "canvas": "#E8E3D9",
    "line": "#D6CEC1",
    "text": "#1B252E",
    "muted": "#68727A",
    "muted_light": "#AEB9BF",
    "accent": "#A8443A",
    "accent_deep": "#7E2F27",
    "accent_soft": "#F3DCD4",
    "redact": "#244A60",
    "redact_soft": "#DCEAF0",
    "success": "#2C745F",
    "danger": "#A94A3C",
}

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_UI_SMALL = ("Microsoft YaHei UI", 9)
FONT_UI_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 18, "bold")
FONT_BRAND = ("Microsoft YaHei UI", 16, "bold")


def apply_theme(root: tk.Tk) -> dict[str, str]:
    color = PALETTE
    root.configure(background=color["canvas"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("App.TFrame", background=color["canvas"])
    style.configure("Chrome.TFrame", background=color["ink"])
    style.configure("Sidebar.TFrame", background=color["ink_alt"])
    style.configure("Main.TFrame", background=color["paper_deep"])
    style.configure("Paper.TFrame", background=color["paper"])
    style.configure("Toolbar.TFrame", background=color["paper_deep"])
    style.configure("Footer.TFrame", background=color["ink"])
    style.configure("Main.TPanedwindow", background=color["canvas"])
    style.configure("Review.TPanedwindow", background=color["paper_deep"])

    style.configure(
        "Brand.TLabel",
        background=color["ink"],
        foreground="#FFFDF8",
        font=FONT_BRAND,
    )
    style.configure(
        "BrandSub.TLabel",
        background=color["ink"],
        foreground="#B9C3C6",
        font=("Microsoft YaHei UI", 8),
    )
    style.configure(
        "ChromePath.TLabel",
        background=color["ink"],
        foreground="#B8C2C6",
        font=FONT_UI_SMALL,
    )
    style.configure(
        "ChromeCase.TLabel",
        background=color["ink"],
        foreground="#FAF7F0",
        font=FONT_UI_BOLD,
    )
    style.configure(
        "SidebarTitle.TLabel",
        background=color["ink_alt"],
        foreground="#F1F3F2",
        font=("Microsoft YaHei UI", 11, "bold"),
    )
    style.configure(
        "SidebarSub.TLabel",
        background=color["ink_alt"],
        foreground="#AEB9BF",
        font=FONT_UI_SMALL,
    )
    style.configure(
        "Section.TLabel",
        background=color["ink_alt"],
        foreground="#9EB0BA",
        font=("Microsoft YaHei UI", 8, "bold"),
    )
    style.configure(
        "CaseTitle.TLabel",
        background=color["paper_deep"],
        foreground=color["ink"],
        font=FONT_TITLE,
    )
    style.configure(
        "Eyebrow.TLabel",
        background=color["paper_deep"],
        foreground=color["accent_deep"],
        font=("Microsoft YaHei UI", 8, "bold"),
    )
    style.configure(
        "Status.TLabel",
        background=color["paper_deep"],
        foreground=color["muted"],
        font=FONT_UI_SMALL,
    )
    style.configure(
        "Footer.TLabel",
        background=color["ink"],
        foreground="#D7E0E2",
        font=FONT_UI_SMALL,
    )
    style.configure(
        "FooterMeta.TLabel",
        background=color["ink"],
        foreground="#AEB9BF",
        font=("Microsoft YaHei UI", 8),
    )
    style.configure(
        "Badge.TLabel",
        background=color["accent_soft"],
        foreground=color["accent_deep"],
        font=("Microsoft YaHei UI", 8, "bold"),
        padding=(7, 3),
    )
    style.configure(
        "BlueBadge.TLabel",
        background=color["redact_soft"],
        foreground=color["redact"],
        font=("Microsoft YaHei UI", 8, "bold"),
        padding=(7, 3),
    )
    style.configure(
        "Warning.TLabel",
        background=color["paper_deep"],
        foreground=color["accent_deep"],
        font=FONT_UI_SMALL,
    )

    style.configure(
        "Chrome.TButton",
        background=color["ink"],
        foreground="#E8EFF0",
        borderwidth=1,
        relief="flat",
        padding=(11, 7),
        font=FONT_UI_SMALL,
    )
    style.map(
        "Chrome.TButton",
        background=[("active", color["ink_light"]), ("disabled", color["ink_alt"])],
        foreground=[("disabled", "#7B8990")],
    )
    style.configure(
        "ChromePrimary.TButton",
        background=color["accent_deep"],
        foreground="#FFF9ED",
        borderwidth=1,
        relief="flat",
        padding=(11, 7),
        font=FONT_UI_BOLD,
    )
    style.map(
        "ChromePrimary.TButton",
        background=[("active", "#66241E"), ("disabled", "#685936")],
        foreground=[("disabled", "#D9CDAE")],
    )
    style.configure(
        "Quiet.TButton",
        background=color["paper"],
        foreground=color["ink_alt"],
        borderwidth=1,
        relief="flat",
        padding=(10, 6),
        font=FONT_UI_SMALL,
    )
    style.map(
        "Quiet.TButton",
        background=[("active", "#F0E9DD"), ("disabled", "#EEE9DF")],
        foreground=[("active", color["accent_deep"]), ("disabled", "#A49E93")],
    )
    style.configure(
        "Accent.TButton",
        background=color["accent_deep"],
        foreground="#FFF9ED",
        borderwidth=1,
        relief="flat",
        padding=(12, 7),
        font=FONT_UI_BOLD,
    )
    style.map(
        "Accent.TButton",
        background=[("active", "#66241E"), ("disabled", "#685936")],
        foreground=[("disabled", "#D9CDAE")],
    )
    style.configure(
        "Sidebar.TButton",
        background=color["ink_light"],
        foreground="#E5ECEE",
        borderwidth=1,
        relief="flat",
        padding=(10, 7),
        font=FONT_UI_SMALL,
    )
    style.map("Sidebar.TButton", background=[("active", "#354B5B")])

    style.configure(
        "Case.Treeview",
        rowheight=30,
        font=FONT_UI,
        background=color["ink_alt"],
        fieldbackground=color["ink_alt"],
        foreground="#D6E0E4",
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Case.Treeview",
        background=[("selected", "#334754")],
        foreground=[("selected", "#FFFDF7")],
    )
    style.configure(
        "Rules.Treeview",
        rowheight=26,
        font=("Microsoft YaHei UI", 9),
        background=color["paper"],
        fieldbackground=color["paper"],
        foreground=color["text"],
        borderwidth=0,
    )
    style.map(
        "Rules.Treeview",
        background=[("selected", color["redact_soft"])],
        foreground=[("selected", color["ink"])],
    )
    style.configure(
        "Case.Horizontal.TProgressbar",
        background=color["accent"],
        troughcolor="#40515E",
        bordercolor="#40515E",
        lightcolor=color["accent"],
        darkcolor=color["accent"],
    )
    style.configure(
        "Page.TCombobox",
        foreground=color["ink_alt"],
        fieldbackground=color["paper"],
        background=color["paper"],
        arrowcolor=color["ink_alt"],
        bordercolor="#B8B0A2",
        padding=4,
        font=FONT_UI_SMALL,
    )
    style.map(
        "Page.TCombobox",
        fieldbackground=[("readonly", color["paper"])],
        foreground=[("readonly", color["ink_alt"])],
    )
    style.configure("TNotebook", background=color["paper_deep"], borderwidth=0)
    style.configure("TNotebook.Tab", font=FONT_UI_SMALL, padding=(12, 6))
    style.configure(
        "Paper.Vertical.TScrollbar",
        background="#DED6C9",
        troughcolor=color["paper"],
        bordercolor=color["paper"],
        arrowcolor=color["muted"],
    )
    style.configure(
        "Sidebar.Vertical.TScrollbar",
        background=color["ink_light"],
        troughcolor=color["ink_alt"],
        bordercolor=color["ink_alt"],
        arrowcolor=color["muted_light"],
    )
    style.configure("TPanedwindow", background=color["canvas"])
    return color
