"""Colour palettes and the application stylesheet (light and dark) - a "glass" look.

Qt style sheets cannot blur what is behind a widget, so the glass effect is built from what they CAN do: a soft
gradient behind everything, frosted semi-transparent panels (rgba fills) with a bright 1 px edge, rounded corners,
gradient buttons and a glassy sidebar. The original solid colours (``surface``, ``border`` ...) are kept because
the charts and a few widgets read them directly; the ``glass_*`` entries are only used by the style sheet.
"""
from __future__ import annotations

import re

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#f4f6fb", "surface": "#ffffff", "border": "#e1e6ef", "text": "#17212f", "muted": "#667085",
        "primary": "#3350d9", "primary_hover": "#2a43b8", "primary_text": "#ffffff",
        "sidebar": "#0f1a36", "sidebar_text": "#d6def2", "sidebar_active": "#1f3068", "sidebar_muted": "#8f9cc0",
        "danger": "#c62828", "success": "#1b7f4b", "warning": "#b26a00",
        "row_alt": "#f8f9fd", "selection": "#dfe6ff", "input_bg": "#ffffff", "hover": "#eef1f9",
        "bar_udhaar": "#e0575b", "bar_jama": "#2fa36b",
        # ---- glass (style sheet only)
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #dbe6ff, stop:0.5 #eee4ff, stop:1 #d5f0ee)",
        "glass": "rgba(255, 255, 255, 140)", "glass_strong": "rgba(255, 255, 255, 205)",
        "glass_hover": "rgba(255, 255, 255, 215)", "glass_input": "rgba(255, 255, 255, 185)",
        "glass_alt": "rgba(255, 255, 255, 70)", "glass_header": "rgba(255, 255, 255, 110)",
        "glass_edge": "rgba(255, 255, 255, 235)", "glass_line": "rgba(70, 90, 150, 45)",
        "glass_selection": "rgba(51, 80, 217, 55)", "popup": "#ffffff",
        "sidebar_gradient": "qlineargradient(x1:0, y1:0, x2:0.4, y2:1, stop:0 #22336e, stop:1 #0b1432)",
        "nav_hover": "rgba(255, 255, 255, 34)",
        "nav_active": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,70), stop:1 rgba(255,255,255,26))",
        "side_edge": "rgba(255, 255, 255, 45)",
        "primary_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6a83f3, stop:1 #3350d9)",
        "primary_gradient_hover": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #7b92f7, stop:1 #4160e6)",
    },
    "dark": {
        "bg": "#0d1220", "surface": "#151c2e", "border": "#26304a", "text": "#e8ecf6", "muted": "#9aa7c4",
        "primary": "#6b86ff", "primary_hover": "#869cff", "primary_text": "#0b1020",
        "sidebar": "#0a0f1d", "sidebar_text": "#b7c2dd", "sidebar_active": "#18223d", "sidebar_muted": "#7886a8",
        "danger": "#ff7b7b", "success": "#4cd694", "warning": "#f0b44c",
        "row_alt": "#121a2b", "selection": "#25335f", "input_bg": "#101728", "hover": "#1b2440",
        "bar_udhaar": "#ff7b7b", "bar_jama": "#4cd694",
        # ---- glass (style sheet only)
        "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0b1020, stop:0.5 #1b1346, stop:1 #08283a)",
        "glass": "rgba(255, 255, 255, 18)", "glass_strong": "rgba(255, 255, 255, 34)",
        "glass_hover": "rgba(255, 255, 255, 40)", "glass_input": "rgba(255, 255, 255, 16)",
        "glass_alt": "rgba(255, 255, 255, 9)", "glass_header": "rgba(255, 255, 255, 14)",
        "glass_edge": "rgba(255, 255, 255, 52)", "glass_line": "rgba(255, 255, 255, 30)",
        "glass_selection": "rgba(107, 134, 255, 85)", "popup": "#1a2238",
        "sidebar_gradient": "qlineargradient(x1:0, y1:0, x2:0.4, y2:1, stop:0 #131c3a, stop:1 #070b17)",
        "nav_hover": "rgba(255, 255, 255, 22)",
        "nav_active": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,48), stop:1 rgba(255,255,255,14))",
        "side_edge": "rgba(255, 255, 255, 30)",
        "primary_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8aa0ff, stop:1 #5b77f5)",
        "primary_gradient_hover": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9bb0ff, stop:1 #6b86ff)",
    },
}

_current = "light"


def current_name() -> str:
    return _current


def current() -> dict[str, str]:
    return PALETTES[_current]


def set_current(name: str) -> None:
    global _current
    _current = name if name in PALETTES else "light"


_TEMPLATE = """
* { font-size: 13px; }

/* ---- window, pages: soft gradient behind everything --------------------------------------------- */
QMainWindow, QDialog { background: @bg_gradient@; color: @text@; }
QStackedWidget { background: transparent; }
QWidget#page { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QLabel { color: @text@; background: transparent; }
QLabel#h1 { font-size: 23px; font-weight: 700; }
QLabel#h2 { font-size: 15px; font-weight: 600; }
QLabel#muted, QLabel[muted="true"] { color: @muted@; }
QLabel#kpiValue { font-size: 25px; font-weight: 700; }
QLabel#kpiTitle { color: @muted@; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#kpiCaption { color: @muted@; font-size: 11px; }
QLabel[kind="danger"] { color: @danger@; font-weight: 600; }
QLabel[kind="success"] { color: @success@; font-weight: 600; }
QLabel[kind="warning"] { color: @warning@; font-weight: 600; }

/* ---- sidebar: dark glass ------------------------------------------------------------------------- */
QFrame#sidebar { background: @sidebar_gradient@; border-right: 1px solid @side_edge@; }
QLabel#brand { color: #ffffff; font-size: 17px; font-weight: 800; letter-spacing: 1px; background: transparent; }
QLabel#brandSub { color: @sidebar_muted@; font-size: 11px; background: transparent; }
QLabel#sideNote { color: @sidebar_muted@; font-size: 11px; background: transparent; }
QPushButton#nav { background: transparent; color: @sidebar_text@; border: 1px solid transparent; border-radius: 10px;
                  text-align: left; padding: 10px 14px; font-size: 13px; }
QPushButton#nav:hover { background: @nav_hover@; border: 1px solid @side_edge@; }
QPushButton#nav:checked { background: @nav_active@; color: #ffffff; font-weight: 700; border: 1px solid @side_edge@; }
QPushButton#sideTool { background: rgba(255, 255, 255, 14); color: @sidebar_text@; border: 1px solid @side_edge@;
                       border-radius: 10px; padding: 7px 10px; }
QPushButton#sideTool:hover { background: @nav_hover@; }

/* ---- frosted panels ------------------------------------------------------------------------------ */
QFrame#card { background: @glass@; border: 1px solid @glass_edge@; border-radius: 16px; }
QFrame#card QLabel { background: transparent; }
QGroupBox { background: @glass@; border: 1px solid @glass_edge@; border-radius: 16px; margin-top: 14px;
            padding: 14px 12px 10px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: @muted@; }

/* ---- buttons ------------------------------------------------------------------------------------- */
QPushButton { background: @glass_strong@; color: @text@; border: 1px solid @glass_edge@; border-radius: 10px;
              padding: 7px 14px; }
QPushButton:hover { background: @glass_hover@; border: 1px solid @primary@; }
QPushButton:pressed { background: @glass@; }
QPushButton:disabled { color: @muted@; background: @glass@; border: 1px solid @glass_line@; }
QPushButton#primary { background: @primary_gradient@; color: @primary_text@; border: 1px solid @glass_edge@;
                      font-weight: 600; }
QPushButton#primary:hover { background: @primary_gradient_hover@; border: 1px solid @glass_edge@; }
QPushButton#primary:disabled { background: @glass@; color: @muted@; border: 1px solid @glass_line@; }
QPushButton#danger { color: @danger@; }
QToolButton { background: @glass_input@; color: @text@; border: 1px solid @glass_line@; border-radius: 8px;
              padding: 5px 8px; }
QToolButton:hover { background: @glass_hover@; border: 1px solid @primary@; }

/* ---- inputs -------------------------------------------------------------------------------------- */
QLineEdit, QComboBox, QDateEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background: @glass_input@; color: @text@; border: 1px solid @glass_line@; border-radius: 10px; padding: 6px 9px;
    selection-background-color: @glass_selection@; selection-color: @text@; }
QLineEdit:hover, QComboBox:hover, QDateEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border: 1px solid @glass_edge@; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid @primary@; background: @glass_strong@; }
QLineEdit[invalid="true"] { border: 1px solid @danger@; }
QLineEdit:read-only { background: @glass_alt@; }
QComboBox QAbstractItemView, QCompleter QAbstractItemView { background: @popup@; color: @text@; border: 1px solid @glass_line@;
                              selection-background-color: @selection@; selection-color: @text@; outline: 0; }
QMenu { background: @popup@; color: @text@; border: 1px solid @glass_line@; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: @selection@; }
QCalendarWidget QWidget { background: @popup@; color: @text@; }

/* ---- tables -------------------------------------------------------------------------------------- */
QTableWidget { background: @glass@; alternate-background-color: @glass_alt@; color: @text@;
               border: 1px solid @glass_edge@; border-radius: 14px; gridline-color: transparent;
               selection-background-color: @glass_selection@; selection-color: @text@; }
QTableWidget::item { padding: 4px 8px; border: none; }
QHeaderView { background: transparent; }
QHeaderView::section { background: @glass_header@; color: @muted@; border: none; border-bottom: 1px solid @glass_line@;
                       padding: 8px; font-weight: 600; font-size: 12px; }
QTableCornerButton::section { background: @glass_header@; border: none; }

/* ---- tabs ---------------------------------------------------------------------------------------- */
QTabWidget::pane { border: 1px solid @glass_edge@; border-radius: 14px; background: @glass@; top: -1px; }
QTabBar::tab { background: transparent; color: @muted@; padding: 8px 16px; border: none; font-weight: 600; }
QTabBar::tab:hover { color: @text@; }
QTabBar::tab:selected { color: @primary@; border-bottom: 2px solid @primary@; }

/* ---- bars, scrollbars ---------------------------------------------------------------------------- */
QProgressBar { background: @glass_line@; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }
QProgressBar::chunk { background: @primary_gradient@; border-radius: 4px; }
QProgressBar[state="warn"]::chunk { background: @warning@; }
QProgressBar[state="over"]::chunk { background: @danger@; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @glass_line@; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @muted@; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @glass_line@; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: @muted@; }

QStatusBar { background: @glass@; color: @muted@; border-top: 1px solid @glass_edge@; }
QToolTip { background: @popup@; color: @text@; border: 1px solid @glass_line@; border-radius: 6px; padding: 4px; }
QMessageBox { background: @bg_gradient@; }
QCheckBox, QRadioButton { color: @text@; spacing: 6px; background: transparent; }
"""


def build_stylesheet(name: str) -> str:
    palette = PALETTES.get(name, PALETTES["light"])
    return re.sub(r"@(\w+)@", lambda m: palette[m.group(1)], _TEMPLATE)
