import sys
import os
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QSize
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QHBoxLayout, QToolButton, QStyle

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow

class StatusWindow(BaseWindow):
    statusSignal = pyqtSignal(str)
    closeSignal = pyqtSignal()
    stopSignal = pyqtSignal()

    def __init__(self, show_stop_button=False):
        """
        Initialize the status window.
        """
        self.show_stop_button = show_stop_button
        self.stop_button = None
        width = 240 if show_stop_button else 200
        super().__init__('WhisperWriter Status', width, 70)
        self.initStatusUI()
        self.statusSignal.connect(self.updateStatus)

    def initStatusUI(self):
        """
        Initialize the status user interface.
        """
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowOpacity(0.7)
        
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(32, 32)
        microphone_path = os.path.join('assets', 'microphone.png')
        pencil_path = os.path.join('assets', 'pencil.png')
        self.microphone_pixmap = QPixmap(microphone_path).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pencil_pixmap = QPixmap(pencil_path).scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(self.microphone_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)

        self.status_label = QLabel('Recording...')
        self.status_label.setFont(QFont('Segoe UI', 12))

        if self.show_stop_button:
            self.stop_button = QToolButton()
            self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
            self.stop_button.setIconSize(QSize(16, 16))
            self.stop_button.setToolTip('Stop')
            self.stop_button.setAutoRaise(True)
            self.stop_button.setCursor(Qt.PointingHandCursor)
            self.stop_button.clicked.connect(self.stopSignal.emit)
            self.stop_button.hide()

        status_layout.addStretch(1)
        status_layout.addWidget(self.icon_label)
        status_layout.addWidget(self.status_label)
        if self.stop_button:
            status_layout.addWidget(self.stop_button)
        status_layout.addStretch(1)

        self.main_layout.addLayout(status_layout)
        
    def show(self):
        """
        Position the window in the bottom center of the screen and show it.
        """
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        window_width = self.width()
        window_height = self.height()

        x = (screen_width - window_width) // 2
        y = screen_height - window_height - 120

        self.move(x, y)
        super().show()
        
    def closeEvent(self, event):
        """
        Emit the close signal when the window is closed.
        """
        self.closeSignal.emit()
        super().closeEvent(event)

    @pyqtSlot(str)
    def updateStatus(self, status):
        """
        Update the status window based on the given status.
        """
        if status == 'recording':
            self.icon_label.setPixmap(self.microphone_pixmap)
            self.status_label.setText('Recording...')
            self._set_stop_button_visible(True)
            self.show()
        elif status == 'transcribing':
            self.icon_label.setPixmap(self.pencil_pixmap)
            self.status_label.setText('Transcribing...')
            self._set_stop_button_visible(False)

        if status in ('idle', 'error', 'cancel'):
            self._set_stop_button_visible(False)
            self.close()

    def _set_stop_button_visible(self, visible):
        if self.stop_button:
            self.stop_button.setVisible(visible)
            self.stop_button.setEnabled(visible)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    status_window = StatusWindow()
    status_window.show()

    # Simulate status updates
    QTimer.singleShot(3000, lambda: status_window.statusSignal.emit('transcribing'))
    QTimer.singleShot(6000, lambda: status_window.statusSignal.emit('idle'))
    
    sys.exit(app.exec_())
