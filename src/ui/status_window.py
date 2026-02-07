import os
import sys
import math
from collections import deque

from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QRectF
from PyQt5.QtGui import (
    QFont, QPainter, QBrush, QColor, QPainterPath, QPen, QCursor,
)
from PyQt5.QtWidgets import (
    QApplication, QLabel, QHBoxLayout, QVBoxLayout, QWidget, QPushButton,
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.theme import (
    BG, BG_SECONDARY, BORDER, TEXT_DIM,
    RED, ORANGE,
    BAR_LOW, BAR_MID, BAR_HIGH,
    font, FONT_FAMILY,
)


# ---------------------------------------------------------------------------
#  Pulsing dot indicator
# ---------------------------------------------------------------------------
class _PulsingDot(QWidget):

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = QColor(color)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_color(self, color: QColor):
        self._color = QColor(color)

    def _tick(self):
        self._phase += 0.12
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        alpha = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(self._phase))
        c = QColor(self._color)
        c.setAlphaF(alpha)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 8, 8)


# ---------------------------------------------------------------------------
#  Scrolling peak-level histogram
# ---------------------------------------------------------------------------
class _AudioLevelWidget(QWidget):

    _BAR_W = 3
    _GAP = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._levels: deque = deque(maxlen=64)
        self.setFixedHeight(36)
        self.setMinimumWidth(100)

    def add_level(self, raw: float):
        compressed = min(1.0, raw ** 0.4) if raw > 0 else 0.0
        self._levels.append(compressed)
        self.update()

    def reset(self):
        self._levels.clear()
        self.update()

    @staticmethod
    def _lerp(c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(c1.red()   + t * (c2.red()   - c1.red())),
            int(c1.green() + t * (c2.green() - c1.green())),
            int(c1.blue()  + t * (c2.blue()  - c1.blue())),
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setBrush(QBrush(BG_SECONDARY))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, w, h, 8, 8)

        if not self._levels:
            p.setPen(TEXT_DIM)
            p.setFont(QFont(FONT_FAMILY, 8))
            p.drawText(self.rect(), Qt.AlignCenter, 'Waiting for audio\u2026')
            return

        step = self._BAR_W + self._GAP
        pad = 6
        max_bars = (w - 2 * pad) // step
        levels = list(self._levels)[-max_bars:]
        x0 = w - pad - len(levels) * step

        lo, mid, hi = BAR_LOW, BAR_MID, BAR_HIGH

        for i, lv in enumerate(levels):
            bh = max(2, int(lv * (h - 2 * pad)))
            bx = x0 + i * step
            by = (h - bh) // 2

            if lv < 0.35:
                color = lo
            elif lv < 0.7:
                color = self._lerp(lo, mid, (lv - 0.35) / 0.35)
            else:
                color = self._lerp(mid, hi, min(1.0, (lv - 0.7) / 0.3))

            p.setBrush(QBrush(color))
            p.drawRoundedRect(bx, by, self._BAR_W, bh, 1, 1)


# ---------------------------------------------------------------------------
#  StatusWindow
# ---------------------------------------------------------------------------
class StatusWindow(QWidget):
    """
    Dark-themed status overlay for recording / transcription.

    * Esc during recording  -> emits ``stopSignal`` (start transcription)
    * Close (X)             -> emits ``closeSignal`` (cancel everything)
    * Transcription mode    -> window shrinks to a compact pill indicator
    """

    statusSignal = pyqtSignal(str)
    closeSignal  = pyqtSignal()
    stopSignal   = pyqtSignal()

    # Two size presets
    REC_W,   REC_H   = 280, 128
    TRANS_W, TRANS_H  = 200, 48

    def __init__(self, show_stop_button=False):
        super().__init__()
        self._show_stop   = show_stop_button
        self._is_recording = False
        self._dragging    = False
        self._drag_origin = None
        self._build_ui()
        self.statusSignal.connect(self.updateStatus)

    # ---- construction --------------------------------------------------

    def _build_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.REC_W, self.REC_H)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(14, 10, 14, 10)
        self._root.setSpacing(6)

        # --- top row: dot + label + [stop] + close ---
        top = QHBoxLayout()
        top.setSpacing(8)

        self._dot = _PulsingDot(RED)

        self._label = QLabel('Recording\u2026')
        self._label.setFont(font(11, bold=True))
        self._label.setStyleSheet('color: #e0e0e0;')

        self._stop_btn = QPushButton('\u25A0  Stop')
        self._stop_btn.setFixedHeight(26)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFont(font(9))
        self._stop_btn.setStyleSheet(
            'QPushButton { background:#2a2b3d; border:1px solid #3a3b4d;'
            '              border-radius:6px; color:#e0e0e0; padding:0 12px; }'
            'QPushButton:hover { background:#3a3b4d; border-color:#4a9eff; }'
        )
        self._stop_btn.clicked.connect(self.stopSignal.emit)
        self._stop_btn.hide()

        self._close_btn = QPushButton('\u2715')
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            'QPushButton { background:transparent; border:none;'
            '              color:#8888a0; font-size:13px; border-radius:12px; }'
            'QPushButton:hover { background:#ff5f57; color:white; }'
        )
        self._close_btn.clicked.connect(self.close)

        top.addWidget(self._dot, 0, Qt.AlignVCenter)
        top.addWidget(self._label, 1)
        top.addWidget(self._stop_btn, 0, Qt.AlignVCenter)
        top.addWidget(self._close_btn, 0, Qt.AlignVCenter)
        self._root.addLayout(top)

        # --- histogram ---
        self._histogram = _AudioLevelWidget()
        self._root.addWidget(self._histogram)

        # --- hint ---
        self._hint = QLabel('Esc \u2014 transcribe')
        self._hint.setFont(font(8))
        self._hint.setStyleSheet('color: #8888a0;')
        self._hint.setAlignment(Qt.AlignRight)
        self._root.addWidget(self._hint)

    # ---- painting ------------------------------------------------------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        radius = min(16, self.height() / 2)
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        p.setBrush(QBrush(BG))
        p.setPen(QPen(BORDER, 1))
        p.drawPath(path)

    # ---- drag support --------------------------------------------------

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_origin = ev.globalPos() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._dragging and self._drag_origin is not None:
            self.move(ev.globalPos() - self._drag_origin)
            ev.accept()

    def mouseReleaseEvent(self, _ev):
        self._dragging = False

    # ---- keyboard ------------------------------------------------------

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            if self._is_recording:
                self.stopSignal.emit()
        else:
            super().keyPressEvent(ev)

    # ---- positioning ---------------------------------------------------

    def _reposition(self):
        cursor_pos = QCursor.pos()
        target = QApplication.primaryScreen()
        for scr in QApplication.screens():
            if scr.geometry().contains(cursor_pos):
                target = scr
                break
        geo = target.availableGeometry()
        x = geo.x() + (geo.width()  - self.width())  // 2
        y = geo.y() + geo.height() - self.height() - 60
        self.move(x, y)

    def show(self):
        self._reposition()
        super().show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def closeEvent(self, event):
        self.closeSignal.emit()
        self._histogram.reset()
        super().closeEvent(event)

    # ---- mode transitions ----------------------------------------------

    def _enter_recording_mode(self):
        self._root.setContentsMargins(14, 10, 14, 10)
        self._root.setSpacing(6)
        self._histogram.reset()
        self._histogram.show()
        self._hint.setText('Esc \u2014 transcribe')
        self._hint.show()
        self._stop_btn.setVisible(self._show_stop)
        self.setFixedSize(self.REC_W, self.REC_H)

    def _enter_transcribing_mode(self):
        self._histogram.hide()
        self._hint.hide()
        self._stop_btn.hide()
        self._root.setContentsMargins(12, 0, 12, 0)
        self._root.setSpacing(0)
        self.setFixedSize(self.TRANS_W, self.TRANS_H)
        self._reposition()

    # ---- public slots --------------------------------------------------

    @pyqtSlot(float)
    def updateAudioLevel(self, level: float):
        if self._is_recording:
            self._histogram.add_level(level)

    @pyqtSlot(str)
    def updateStatus(self, status):
        if status == 'recording':
            self._is_recording = True
            self._dot.set_color(RED)
            self._label.setText('Recording\u2026')
            self._enter_recording_mode()
            self.show()

        elif status == 'transcribing':
            self._is_recording = False
            self._dot.set_color(ORANGE)
            self._label.setText('Transcribing\u2026')
            self._enter_transcribing_mode()

        if status in ('idle', 'error', 'cancel'):
            self._is_recording = False
            self._histogram.reset()
            self.close()


# ---------------------------------------------------------------------------
#  Standalone demo
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import random

    app = QApplication(sys.argv)

    win = StatusWindow(show_stop_button=True)
    win.updateStatus('recording')

    _demo_timer = QTimer()
    _demo_timer.timeout.connect(
        lambda: win.updateAudioLevel(random.uniform(0.01, 0.6))
    )
    _demo_timer.start(60)

    QTimer.singleShot(5000, lambda: win.updateStatus('transcribing'))
    QTimer.singleShot(8000, lambda: win.updateStatus('idle'))

    sys.exit(app.exec_())
