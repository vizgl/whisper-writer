import os
import sys
import math
import ctypes
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
    RED, ORANGE, GREEN,
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
    retrySignal  = pyqtSignal()

    # Size presets
    REC_W,   REC_H   = 240, 110
    TRANS_W, TRANS_H  = 200, 48
    DONE_W,  DONE_H  = 200, 48

    def __init__(self, show_stop_button=False):
        super().__init__()
        self._show_stop   = show_stop_button
        self._is_recording = False
        self._is_done     = False
        self._is_error    = False
        self._dismiss_armed = False
        self._dragging    = False
        self._drag_origin = None
        self._anchor = None  # (x, y) screen coords below input field
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
        self._root.setContentsMargins(14, 10, 14, 4)
        self._root.setSpacing(6)

        # --- top row: dot + label + close ---
        top = QHBoxLayout()
        top.setSpacing(8)

        self._dot = _PulsingDot(RED)

        self._label = QLabel('Recording\u2026')
        self._label.setFont(font(11, bold=True))
        self._label.setStyleSheet('color: #e0e0e0;')

        self._close_btn = QPushButton('\u2715')
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(
            'QPushButton { background:transparent; border:none;'
            '              color:#8888a0; font-size:13px; border-radius:12px; }'
            'QPushButton:hover { background:#ff5f57; color:white; }'
        )
        self._close_btn.clicked.connect(self.close)

        self._retry_btn = QPushButton('\u21bb')
        self._retry_btn.setFixedSize(24, 24)
        self._retry_btn.setCursor(Qt.PointingHandCursor)
        self._retry_btn.setToolTip('Retry transcription')
        self._retry_btn.setStyleSheet(
            'QPushButton { background:transparent; border:none;'
            '              color:#8888a0; font-size:15px; border-radius:12px; }'
            'QPushButton:hover { background:#4a9eff; color:white; }'
        )
        self._retry_btn.clicked.connect(self.retrySignal.emit)
        self._retry_btn.hide()

        top.addWidget(self._dot, 0, Qt.AlignVCenter)
        top.addWidget(self._label, 1)
        top.addWidget(self._retry_btn, 0, Qt.AlignVCenter)
        top.addWidget(self._close_btn, 0, Qt.AlignVCenter)
        self._root.addLayout(top)

        # --- middle row: histogram + stop button ---
        mid = QHBoxLayout()
        mid.setSpacing(6)

        self._histogram = _AudioLevelWidget()

        self._stop_btn = QPushButton('\u25A0  Stop')
        self._stop_btn.setFixedSize(64, 36)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFont(font(9))
        self._stop_btn.setStyleSheet(
            'QPushButton { background:#2a2b3d; border:1px solid #3a3b4d;'
            '              border-radius:6px; color:#e0e0e0; padding:0 8px; }'
            'QPushButton:hover { background:#3a3b4d; border-color:#4a9eff; }'
        )
        self._stop_btn.clicked.connect(self.stopSignal.emit)
        self._stop_btn.hide()

        mid.addWidget(self._histogram, 1)
        mid.addWidget(self._stop_btn, 0, Qt.AlignVCenter)
        self._mid_layout = mid
        self._root.addLayout(mid)

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

    # ---- positioning ---------------------------------------------------

    def set_anchor(self, x, y):
        """Set the screen position (below the input field) to anchor the window to."""
        self._anchor = (x, y) if x is not None else None

    def _reposition(self):
        from PyQt5.QtCore import QPoint

        # Determine which screen to use
        ref = QPoint(*self._anchor) if self._anchor else QCursor.pos()
        target = QApplication.primaryScreen()
        for scr in QApplication.screens():
            if scr.geometry().contains(ref):
                target = scr
                break
        geo = target.availableGeometry()

        if self._anchor:
            ax, ay = self._anchor
            gap = 8
            x = ax - self.width() // 2
            y = ay + gap
            # Clamp to screen bounds
            x = max(geo.x(), min(x, geo.x() + geo.width() - self.width()))
            y = max(geo.y(), min(y, geo.y() + geo.height() - self.height()))
        else:
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
        self._dismiss_armed = False
        self._stop_dismiss_timer()
        self._root.setContentsMargins(14, 10, 14, 4)
        self._root.setSpacing(6)
        self._histogram.reset()
        self._histogram.show()
        self._hint.setText('Esc \u2014 transcribe')
        self._hint.show()
        self._retry_btn.hide()
        self._stop_btn.setVisible(self._show_stop)
        self.setFixedSize(self.REC_W, self.REC_H)

    def _enter_transcribing_mode(self):
        self._dismiss_armed = False
        self._stop_dismiss_timer()
        self._histogram.hide()
        self._hint.hide()
        self._stop_btn.hide()
        self._retry_btn.hide()
        self._root.setContentsMargins(12, 0, 12, 0)
        self._root.setSpacing(0)
        self.setFixedSize(self.TRANS_W, self.TRANS_H)
        self._reposition()
        # Show retry button after a delay so user can restart a hung transcription
        QTimer.singleShot(5000, self._show_transcribing_retry)

    def _enter_done_mode(self):
        self._histogram.hide()
        self._hint.hide()
        self._stop_btn.hide()
        self._retry_btn.show()
        self._dismiss_armed = False
        self._root.setContentsMargins(12, 0, 12, 0)
        self._root.setSpacing(0)
        self.setFixedSize(self.DONE_W, self.DONE_H)
        self._reposition()
        QTimer.singleShot(800, self._arm_dismiss)

    def _show_transcribing_retry(self):
        """Show the retry button if still stuck in transcribing mode."""
        if not self._is_recording and not self._is_done and self.isVisible():
            self._retry_btn.show()

    def _arm_dismiss(self):
        if self._is_done:
            self._dismiss_armed = True
            if sys.platform == 'win32':
                self._fg_at_arm = ctypes.windll.user32.GetForegroundWindow()
                self._dismiss_timer = QTimer(self)
                self._dismiss_timer.timeout.connect(self._poll_dismiss)
                self._dismiss_timer.start(200)

    def _stop_dismiss_timer(self):
        if hasattr(self, '_dismiss_timer') and self._dismiss_timer is not None:
            self._dismiss_timer.stop()
            self._dismiss_timer = None

    def _poll_dismiss(self):
        if not self._is_done or not self._dismiss_armed:
            self._stop_dismiss_timer()
            return
        fg = ctypes.windll.user32.GetForegroundWindow()
        my_hwnd = int(self.winId())
        if fg != self._fg_at_arm and fg != my_hwnd:
            self._stop_dismiss_timer()
            self.close()

    # ---- public slots --------------------------------------------------

    @pyqtSlot(float)
    def updateAudioLevel(self, level: float):
        if self._is_recording:
            self._histogram.add_level(level)

    @pyqtSlot(str)
    def updateStatus(self, status):
        if status == 'recording':
            self._is_recording = True
            self._is_done = False
            self._dot.set_color(RED)
            self._label.setText('Recording\u2026')
            self._enter_recording_mode()
            self.show()

        elif status == 'transcribing':
            self._is_recording = False
            self._is_done = False
            self._dot.set_color(ORANGE)
            self._label.setText('Transcribing\u2026')
            self._enter_transcribing_mode()

        elif status == 'done':
            self._is_recording = False
            self._is_done = True
            self._dot.set_color(GREEN)
            self._label.setText('Done')
            self._enter_done_mode()

        elif status == 'error':
            # Keep the window up briefly so the failure is visible instead of
            # flashing open/closed; details go to the tray notification.
            self._is_recording = False
            self._is_done = False
            self._is_error = True
            self._dot.set_color(RED)
            self._label.setText('Error')
            self._histogram.hide()
            self._hint.hide()
            self._stop_btn.hide()
            self._retry_btn.hide()
            self._root.setContentsMargins(12, 0, 12, 0)
            self._root.setSpacing(0)
            self.setFixedSize(self.TRANS_W, self.TRANS_H)
            self._reposition()
            QTimer.singleShot(2500, self._close_if_error)

        if status != 'error':
            self._is_error = False

        if status in ('idle', 'cancel'):
            self._is_recording = False
            self._is_done = False
            self._histogram.reset()
            self.close()

    def _close_if_error(self):
        """Close the window after the error display delay, unless a new
        recording/transcription has started in the meantime."""
        if self._is_error:
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
