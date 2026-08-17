import time
import traceback
import numpy as np
import sounddevice as sd
import tempfile
import wave
import webrtcvad
from PyQt5.QtCore import QThread, QMutex, pyqtSignal
from collections import deque
from threading import Event

from transcription import transcribe
from utils import ConfigManager


class ResultThread(QThread):
    """
    A thread class for handling audio recording, transcription, and result processing.

    This class manages the entire process of:
    1. Recording audio from the microphone
    2. Detecting speech and silence
    3. Saving the recorded audio as numpy array
    4. Transcribing the audio
    5. Emitting the transcription result

    Signals:
        statusSignal: Emits the current status of the thread (e.g., 'recording', 'transcribing', 'idle')
        resultSignal: Emits the transcription result
    """

    statusSignal = pyqtSignal(str)
    resultSignal = pyqtSignal(str)
    audioLevelSignal = pyqtSignal(float)
    audioDataReady = pyqtSignal(object)
    errorSignal = pyqtSignal(str)

    def __init__(self, local_model=None):
        """
        Initialize the ResultThread.

        :param local_model: Local transcription model (if applicable)
        """
        super().__init__()
        self.local_model = local_model
        self.is_recording = False
        self.is_running = True
        self.sample_rate = None
        self.mutex = QMutex()

    def stop_recording(self):
        """Stop the current recording session."""
        self.mutex.lock()
        self.is_recording = False
        self.mutex.unlock()

    def stop(self):
        """Stop the entire thread execution."""
        self.mutex.lock()
        self.is_running = False
        self.mutex.unlock()
        self.statusSignal.emit('idle')
        self.wait()

    def run(self):
        """Main execution method for the thread."""
        try:
            if not self.is_running:
                return

            self.mutex.lock()
            self.is_recording = True
            self.mutex.unlock()

            self.statusSignal.emit('recording')
            ConfigManager.console_print('Recording...')
            audio_data = self._record_audio()

            if not self.is_running:
                return

            if audio_data is None:
                self.statusSignal.emit('idle')
                return

            self.audioDataReady.emit(audio_data)

            self.statusSignal.emit('transcribing')
            ConfigManager.console_print('Transcribing...')

            # Time the transcription process
            start_time = time.time()
            result = transcribe(audio_data, self.local_model)
            end_time = time.time()

            transcription_time = end_time - start_time
            ConfigManager.console_print(f'Transcription completed in {transcription_time:.2f} seconds. Post-processed line: {result}')

            if not self.is_running:
                return

            self.resultSignal.emit(result)

        except Exception as e:
            traceback.print_exc()
            self.errorSignal.emit(str(e))
            self.statusSignal.emit('error')
            self.resultSignal.emit('')
        finally:
            self.stop_recording()

    @staticmethod
    def _parse_requested_device(requested_device):
        """Normalize the configured device value (index, name, or empty)."""
        device = requested_device
        if isinstance(device, str):
            device = device.strip()
            if device == '':
                device = None
            else:
                try:
                    device = int(device)
                except ValueError:
                    pass
        if device == -1:
            device = None
        return device

    def _iter_input_candidates(self, requested_device, target_rate):
        """Yield (device, samplerate) pairs to try, most preferred first.

        Simply taking the first device with input channels is not enough:
        the enumeration can start with a broken ASIO driver, and WDM-KS
        devices reject non-native sample rates. So every candidate device is
        tried at the target rate, then at its own default rate.
        """
        if requested_device is not None:
            device_indices = [requested_device]
        else:
            try:
                devices = sd.query_devices()
                hostapis = sd.query_hostapis()
            except Exception as exc:
                ConfigManager.console_print(f"Failed to query audio devices: {exc}")
                return
            non_asio, asio = [], []
            for idx, info in enumerate(devices):
                if info.get('max_input_channels', 0) < 1:
                    continue
                api_name = hostapis[info['hostapi']]['name'] if 'hostapi' in info else ''
                (asio if 'ASIO' in api_name else non_asio).append(idx)
            # ASIO last: broken ASIO drivers are a common cause of instant failure
            device_indices = non_asio + asio

        for idx in device_indices:
            rates = [target_rate]
            try:
                default_rate = int(round(sd.query_devices(idx)['default_samplerate']))
                if default_rate not in rates:
                    rates.append(default_rate)
            except Exception:
                pass
            for rate in (48000, 44100):
                if rate not in rates:
                    rates.append(rate)
            for rate in rates:
                yield idx, rate

    def _record_audio(self):
        """
        Record audio from the microphone and save it to a temporary file.

        :return: numpy array of audio data, or None if the recording is too short
        """
        recording_options = ConfigManager.get_config_section('recording_options')
        target_rate = recording_options.get('sample_rate') or 16000
        frame_duration_ms = 30  # 30ms frame duration for WebRTC VAD
        silence_duration_ms = recording_options.get('silence_duration') or 900
        silence_frames = int(silence_duration_ms / frame_duration_ms)
        recording_mode = recording_options.get('recording_mode') or 'continuous'

        audio_buffer = deque()
        recording = []
        data_ready = Event()

        def audio_callback(indata, frames, time, status):
            if status:
                ConfigManager.console_print(f"Audio callback status: {status}")
            audio_buffer.extend(indata[:, 0])
            data_ready.set()

        # Open the first (device, samplerate) combination that actually works.
        requested = self._parse_requested_device(recording_options.get('sound_device'))
        stream = None
        capture_rate = None
        frame_size = None
        last_error = None
        for device, rate in self._iter_input_candidates(requested, target_rate):
            candidate_frame = int(rate * (frame_duration_ms / 1000.0))
            try:
                candidate = sd.InputStream(samplerate=rate, channels=1, dtype='int16',
                                           blocksize=candidate_frame, device=device,
                                           callback=audio_callback)
                candidate.start()
                stream = candidate
                capture_rate = rate
                frame_size = candidate_frame
                device_name = sd.query_devices(device)['name']
                ConfigManager.console_print(f'Recording from device {device} ({device_name}) at {rate} Hz')
                break
            except Exception as exc:
                last_error = exc
                ConfigManager.console_print(f'Input device {device} @ {rate} Hz failed: {exc}')

        if stream is None:
            raise RuntimeError(
                f'No working microphone found. Check that a microphone is '
                f'connected and enabled. Last error: {last_error}'
            )

        self.sample_rate = capture_rate

        # 150ms delay before starting VAD to avoid mistaking the sound of key pressing for voice
        initial_frames_to_skip = int(0.15 * capture_rate / frame_size)

        # Create VAD only for recording modes that use it (and rates it supports)
        vad = None
        if recording_mode in ('voice_activity_detection', 'continuous'):
            if capture_rate in (8000, 16000, 32000, 48000):
                vad = webrtcvad.Vad(2)  # VAD aggressiveness: 0 to 3, 3 being the most aggressive
                speech_detected = False
                silent_frame_count = 0
            else:
                ConfigManager.console_print(f'VAD unsupported at {capture_rate} Hz — disabled.')

        try:
            while self.is_running and self.is_recording:
                data_ready.wait()
                data_ready.clear()

                if len(audio_buffer) < frame_size:
                    continue

                # Save frame
                frame = np.array(list(audio_buffer), dtype=np.int16)
                audio_buffer.clear()
                recording.extend(frame)

                # Emit peak level for UI histogram
                peak = float(np.abs(frame.astype(np.float32)).max()) / 32768.0
                self.audioLevelSignal.emit(peak)

                # Avoid trying to detect voice in initial frames
                if initial_frames_to_skip > 0:
                    initial_frames_to_skip -= 1
                    continue

                if vad:
                    if vad.is_speech(frame.tobytes(), capture_rate):
                        silent_frame_count = 0
                        if not speech_detected:
                            ConfigManager.console_print("Speech detected.")
                            speech_detected = True
                    else:
                        silent_frame_count += 1

                    if speech_detected and silent_frame_count > silence_frames:
                        break
        finally:
            stream.stop()
            stream.close()

        audio_data = np.array(recording, dtype=np.int16)
        duration = len(audio_data) / capture_rate

        ConfigManager.console_print(f'Recording finished. Size: {audio_data.size} samples, Duration: {duration:.2f} seconds')

        min_duration_ms = recording_options.get('min_duration') or 100

        if (duration * 1000) < min_duration_ms:
            ConfigManager.console_print(f'Discarded due to being too short.')
            return None

        # Whisper expects 16 kHz input; resample if the device recorded at
        # another rate (WDM-KS and ASIO devices only accept native rates).
        if capture_rate != target_rate and len(audio_data) > 0:
            n_out = int(round(len(audio_data) * target_rate / capture_rate))
            positions = np.linspace(0, len(audio_data) - 1, n_out)
            audio_data = np.interp(positions, np.arange(len(audio_data)),
                                   audio_data.astype(np.float32)).astype(np.int16)
            self.sample_rate = target_rate
            ConfigManager.console_print(f'Resampled {capture_rate} Hz -> {target_rate} Hz')

        return audio_data
