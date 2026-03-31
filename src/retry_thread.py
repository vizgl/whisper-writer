import time
import traceback
from PyQt5.QtCore import QThread, pyqtSignal

from transcription import transcribe
from utils import ConfigManager


class RetryThread(QThread):
    """Lightweight thread that re-transcribes already-recorded audio."""

    statusSignal = pyqtSignal(str)
    resultSignal = pyqtSignal(str)

    def __init__(self, audio_data, local_model=None):
        super().__init__()
        self.audio_data = audio_data
        self.local_model = local_model

    def run(self):
        try:
            self.statusSignal.emit('transcribing')
            ConfigManager.console_print('Retrying transcription...')

            start = time.time()
            result = transcribe(self.audio_data, self.local_model)
            elapsed = time.time() - start

            ConfigManager.console_print(
                f'Retry transcription completed in {elapsed:.2f}s. Result: {result}'
            )

            self.statusSignal.emit('done')
            self.resultSignal.emit(result)
        except Exception:
            traceback.print_exc()
            self.statusSignal.emit('error')
            self.resultSignal.emit('')
