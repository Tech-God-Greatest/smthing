import time
from PyQt6.QtCore import QThread, pyqtSignal
from audio.stt import listen
from audio.tts import stop as tts_stop
from utils.logger import log_info, log_error


class VoiceWorker(QThread):
    """Background thread that continuously listens for speech.
    Whenever speech is detected, it stops TTS and emits the transcribed text."""
    voice_detected_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = True

    def run(self):
        while self.running:
            try:
                user_text = listen(speech_start_timeout=None)
                if user_text:
                    tts_stop()
                    log_info("Voice", f"Speech detected: '{user_text}' -> Stopped TTS")
                    self.voice_detected_signal.emit(user_text)
            except Exception as e:
                log_error("Voice", f"{e}")
                time.sleep(0.5)

