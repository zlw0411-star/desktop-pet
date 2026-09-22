import os
import tempfile
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .rvc import RVCWorker
from .tts import TTS


class SpeechEngine(QObject):
    """说话引擎：优先走 RVC 音色转换，否则回退系统 TTS。"""

    speaking_changed = Signal(bool)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._qt = TTS(config)
        self._qt.speaking_changed.connect(self.speaking_changed)
        self._rvc = RVCWorker(config)
        self._rvc.failed.connect(self._on_rvc_failed)
        self._temp_dir = os.path.join(tempfile.gettempdir(), "desktop_pet_voice")
        os.makedirs(self._temp_dir, exist_ok=True)
        self._off_timer = QTimer(self)
        self._off_timer.setSingleShot(True)
        self._off_timer.timeout.connect(lambda: self.speaking_changed.emit(False))
        self._fallback_text = ""

    def rvc_available(self):
        return self._rvc.available()

    def speak(self, text):
        text = (text or "").strip()
        if not text:
            return
        self.stop()
        if self.rvc_available():
            self._speak_rvc(text)
        else:
            self._qt.speak(text)

    def _speak_rvc(self, text):
        self._fallback_text = text
        output = os.path.join(self._temp_dir, "pet_%d.wav" % int(time.time() * 1000))

        def done(path, error):
            if path and os.path.exists(path):
                self._play(path)
            else:
                self._qt.speak(text)

        self._rvc.convert(done, text=text, output_path=output)

    def _on_rvc_failed(self, message):
        if self._fallback_text:
            self._qt.speak(self._fallback_text)
            self._fallback_text = ""

    def _play(self, path):
        try:
            import winsound

            winsound.PlaySound(
                path,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            self._qt.speak(self._fallback_text)
            return
        duration = self._duration(path)
        self.speaking_changed.emit(True)
        self._off_timer.start(int(duration * 1000) + 250)

    @staticmethod
    def _duration(path):
        try:
            import wave

            with wave.open(path, "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate() or 1
            return max(0.6, min(60.0, frames / rate))
        except Exception:
            return 2.5

    def stop(self):
        self._off_timer.stop()
        try:
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self._qt.stop()

    def shutdown(self):
        self.stop()
        self._rvc.stop()

    def reload(self):
        self.stop()
        self._rvc.stop()
