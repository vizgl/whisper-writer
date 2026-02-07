"""
Shared dark-theme palette and stylesheet for all WhisperWriter windows.
"""

from PyQt5.QtGui import QColor, QFont

# ---------------------------------------------------------------------------
#  Colour palette
# ---------------------------------------------------------------------------
BG           = QColor(30, 31, 46, 240)
BG_SOLID     = QColor(30, 31, 46)
BG_SECONDARY = QColor(22, 23, 34)
SURFACE      = QColor(42, 43, 61)
OVERLAY      = QColor(58, 59, 77)
BORDER       = QColor(60, 62, 87)

TEXT         = QColor(224, 224, 224)
TEXT_DIM     = QColor(136, 136, 160)

ACCENT       = QColor(74, 158, 255)
RED          = QColor(255, 95, 87)
ORANGE       = QColor(255, 179, 71)
GREEN        = QColor(166, 227, 161)

BAR_LOW      = QColor(74, 158, 255)
BAR_MID      = QColor(124, 92, 252)
BAR_HIGH     = QColor(255, 107, 107)

# ---------------------------------------------------------------------------
#  Font helper
# ---------------------------------------------------------------------------
FONT_FAMILY = 'Segoe UI'


def font(size: int = 10, bold: bool = False) -> QFont:
    f = QFont(FONT_FAMILY, size)
    if bold:
        f.setWeight(QFont.DemiBold)
    return f


# ---------------------------------------------------------------------------
#  QSS applied to every top-level window
# ---------------------------------------------------------------------------
WINDOW_QSS = """
/* ---- base ---- */
QWidget {
    background: transparent;
    color: #e0e0e0;
    font-family: 'Segoe UI';
}
QLabel {
    background: transparent;
    color: #e0e0e0;
}

/* ---- buttons ---- */
QPushButton {
    background: #2a2b3d;
    border: 1px solid #3a3b4d;
    border-radius: 6px;
    color: #e0e0e0;
    padding: 6px 16px;
}
QPushButton:hover {
    background: #3a3b4d;
    border-color: #4a9eff;
}
QPushButton:pressed {
    background: #1a1b2d;
}

/* ---- inputs ---- */
QLineEdit {
    background: #16172a;
    border: 1px solid #3a3b4d;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 4px 8px;
    selection-background-color: #4a9eff;
}
QLineEdit:focus {
    border-color: #4a9eff;
}

/* ---- combo boxes ---- */
QComboBox {
    background: #16172a;
    border: 1px solid #3a3b4d;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 4px 8px;
}
QComboBox:hover { border-color: #4a9eff; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8888a0;
}
QComboBox QAbstractItemView {
    background: #1e1f2e;
    border: 1px solid #3a3b4d;
    color: #e0e0e0;
    selection-background-color: #3a3b4d;
    outline: none;
}

/* ---- check boxes ---- */
QCheckBox { color: #e0e0e0; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #3a3b4d;
    border-radius: 3px;
    background: #16172a;
}
QCheckBox::indicator:checked {
    background: #4a9eff;
    border-color: #4a9eff;
}
QCheckBox::indicator:hover { border-color: #4a9eff; }

/* ---- tab widget ---- */
QTabWidget::pane {
    border: 1px solid #3a3b4d;
    border-radius: 0 0 6px 6px;
    background: rgba(30, 31, 46, 200);
    top: -1px;
}
QTabBar::tab {
    background: #16172a;
    border: 1px solid #3a3b4d;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #8888a0;
    padding: 6px 14px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: rgba(30, 31, 46, 200);
    color: #e0e0e0;
}
QTabBar::tab:hover:!selected { color: #c0c0d0; }

/* ---- tool buttons ---- */
QToolButton {
    background: transparent;
    border: none;
    color: #8888a0;
    border-radius: 4px;
    padding: 2px;
}
QToolButton:hover {
    background: #3a3b4d;
    color: #e0e0e0;
}

/* ---- scrollbars ---- */
QScrollBar:vertical {
    background: #16172a; width: 8px; border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3a3b4d; border-radius: 4px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #4a5570; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

/* ---- tooltips ---- */
QToolTip {
    background: #1e1f2e;
    border: 1px solid #3a3b4d;
    color: #e0e0e0;
    padding: 4px 8px;
    border-radius: 4px;
}
"""
