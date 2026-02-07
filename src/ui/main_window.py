import os
import sys
from PyQt5.QtWidgets import QApplication, QPushButton, QHBoxLayout
from PyQt5.QtCore import pyqtSignal

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui.base_window import BaseWindow
from ui.theme import font


class MainWindow(BaseWindow):
    openSettings = pyqtSignal()
    startListening = pyqtSignal()
    closeApp = pyqtSignal()

    def __init__(self):
        super().__init__('WhisperWriter', 320, 170)
        self.initMainUI()

    def initMainUI(self):
        start_btn = QPushButton('Start')
        start_btn.setFont(font(10))
        start_btn.setFixedSize(120, 50)
        start_btn.clicked.connect(self.startPressed)

        settings_btn = QPushButton('Settings')
        settings_btn.setFont(font(10))
        settings_btn.setFixedSize(120, 50)
        settings_btn.clicked.connect(self.openSettings.emit)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        button_layout.addWidget(start_btn)
        button_layout.addWidget(settings_btn)
        button_layout.addStretch(1)

        self.main_layout.addStretch(1)
        self.main_layout.addLayout(button_layout)
        self.main_layout.addStretch(1)

    def closeEvent(self, event):
        self.closeApp.emit()

    def startPressed(self):
        self.startListening.emit()
        self.hide()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
