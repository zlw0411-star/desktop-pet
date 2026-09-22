import os
import subprocess
import sys

from PySide6.QtCore import QObject, QTimer, Signal

try:
    from PySide6.QtTextToSpeech import QTextToSpeech
except ImportError:  # pragma: no cover
    QTextToSpeech = None

_CREATE_NO_WINDOW = 0x08000000


class TTS(QObject):
    speaking_changed = Signal(bool)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._engine = None
        self._proc = None
        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.timeout.connect(lambda: self.speaking_changed.emit(False))
        self._init_engine()

    def _init_engine(self):
        if QTextToSpeech is None:
            return
        cfg = self.config.get("voice", {}) or {}
        engine_name = cfg.get("engine")
        try:
            self._engine = QTextToSpeech(engine_name) if engine_name else QTextToSpeech()
        except Exception:
            self._engine = None
            return
        self._engine.stateChanged.connect(self._on_state_changed)
        self._engine.setVolume(float(cfg.get("volume", 1.0)))
        self._engine.setRate(float(cfg.get("rate", 0.0)))
        self._select_voice(cfg.get("voice_name"))

    def _select_voice(self, preferred):
        if self._engine is None:
            return
        voices = self._engine.availableVoices()
        if not voices:
            return
        for voice in voices:
            if preferred and voice.name() == preferred:
                self._engine.setVoice(voice)
                return
        for voice in voices:
            if "zh" in voice.name().lower() or "chinese" in voice.name().lower():
                self._engine.setVoice(voice)
                return
        self._engine.setVoice(voices[0])

    def _on_state_changed(self, state):
        speaking = state == QTextToSpeech.Speaking
        self.speaking_changed.emit(speaking)

    def _enabled(self):
        return bool((self.config.get("voice", {}) or {}).get("enabled", True))

    def speak(self, text):
        text = (text or "").strip()
        if not text or not self._enabled():
            return
        self.stop()
        if self._engine is not None:
            self._engine.say(text)
        else:
            self._speak_fallback(text)

    def _speak_fallback(self, text):
        if os.name != "nt":
            return
        script = ("Add-Type -AssemblyName System.Speech; "
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  "$s.Speak($env:DESKTOP_PET_TTS)")
        env = os.environ.copy()
        env["DESKTOP_PET_TTS"] = text
        try:
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                env=env, creationflags=_CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.speaking_changed.emit(True)
        seconds = min(30.0, max(1.5, len(text) / 12.0))
        self._fallback_timer.start(int(seconds * 1000))

    def stop(self):
        self._fallback_timer.stop()
        if self._engine is not None:
            self._engine.stop()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
            self._proc = None
