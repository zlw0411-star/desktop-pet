from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QFileDialog

from . import autostart, cutout
from .ai.client import AIClient
from .assets import import_image
from .input_bubble import InputBubble
from .cutout import CutoutWorker
from .speech_bubble import SpeechBubble
from .config import Config
from .pet_window import PetWindow
from .settings_dialog import SettingsDialog
from .tray import TrayManager
from .voice.speech import SpeechEngine


class DesktopPetApp(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.config = Config()

        self._cut_worker = None
        self._pending_image = None
        self._speech_active = False

        self.pet = PetWindow(self.config)
        self.tray = TrayManager(self.config)
        self.input_bubble = InputBubble()
        self.speech = SpeechBubble()
        self.tts = SpeechEngine(self.config)
        self.ai = AIClient(self.config)
        self._greeted = False
        self.speech.set_anchor_getter(lambda: self.pet)

        self.pet.chat_requested.connect(self.open_chat)
        self.pet.context_menu_requested.connect(self.show_menu)
        self.pet.image_dropped.connect(self.set_custom_image)
        self.tray.action_triggered.connect(self.on_tray_action)
        self.input_bubble.submitted.connect(self.on_user_message)
        self.ai.reply_ready.connect(self.on_reply)
        self.ai.failed.connect(self.on_reply)
        self.ai.chunk.connect(self.on_chunk)
        self.tts.speaking_changed.connect(self.on_speaking_changed)

        self.pet.set_always_on_top(bool(self.config.get("always_on_top", True)))

    def start(self):
        self.tray.set_pet_visible(True)
        self.tray.set_autostart(autostart.is_enabled())
        self.tray.show()
        self.pet.start()

    def open_chat(self):
        self.pet.enter_talk()
        self.input_bubble.popup_above(self.pet)
        if not self._greeted:
            self._greeted = True
            self.speech.finalize("你好呀，和我说说话吧～")

    def on_user_message(self, text):
        self.pet.enter_talk()
        self.input_bubble.hide()
        self._speech_active = False
        self.speech.show_stream()
        self.speech.append("…")
        self.ai.send(text)

    def on_chunk(self, delta):
        if not self._speech_active:
            self._speech_active = True
            self.speech.show_stream()
        self.speech.append(delta)

    def on_reply(self, text):
        if not self._speech_active:
            self._speech_active = True
            self.speech.show_stream()
        self.speech.finalize(text)
        self.pet.enter_talk()
        voice_on = bool((self.config.get("voice") or {}).get("enabled", True))
        if voice_on:
            self.tts.speak(text)
            QTimer.singleShot(6000, self.pet.finish_talk)
        else:
            QTimer.singleShot(4000, self.pet.finish_talk)

    def on_speaking_changed(self, speaking):
        if speaking:
            self.pet.enter_talk()
        else:
            self.pet.finish_talk()

    def show_menu(self, global_pos):
        self.tray.menu.popup(global_pos)

    def on_tray_action(self, action):
        if action == "toggle":
            visible = self.pet.isVisible()
            self.pet.setVisible(not visible)
            if visible:
                self.input_bubble.hide()
                self.speech.hide()
            self.tray.set_pet_visible(not visible)
        elif action == "chat":
            self.pet.setVisible(True)
            self.tray.set_pet_visible(True)
            self.open_chat()
        elif action == "settings":
            self.open_settings()
        elif action == "change_image":
            self.choose_image()
        elif action.startswith("autostart:"):
            enabled = action.split(":", 1)[1] == "1"
            autostart.set_enabled(enabled)
            self.config["autostart"] = enabled
            self.config.save()
        elif action == "quit":
            self.quit()

    def open_settings(self):
        dialog = SettingsDialog(self.config, self.pet)
        dialog.settings_saved.connect(self.apply_settings)
        dialog.voice_test_requested.connect(self.test_voice)
        dialog.exec()

    def test_voice(self):
        self.tts.speak("你好呀，我是你的桌面宠物，这是我的声音。")

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self.pet, "选择宠物形象图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if path:
            self.set_custom_image(path)

    def set_custom_image(self, path):
        stored = import_image(path)
        if not stored:
            self.tray.show_message("更换形象", "无法读取这张图片，请换个格式试试。")
            return
        self._pending_image = stored
        if self.config.get("auto_cutout", True) and cutout.available():
            self.tray.show_message("更换形象", "正在抠图，请稍等…")
            self._cut_worker = CutoutWorker(stored)
            self._cut_worker.done.connect(self._on_cutout_done)
            self._cut_worker.failed.connect(self._on_cutout_failed)
            self._cut_worker.start()
        else:
            self._apply_image(stored)
            self.tray.show_message("更换形象", "已换成你的图片啦～")

    def _on_cutout_done(self, cut_path):
        self._apply_image(cut_path)
        self.tray.show_message("更换形象", "抠图完成，漂亮！")

    def _on_cutout_failed(self, message):
        if getattr(self, "_pending_image", None):
            self._apply_image(self._pending_image)
        self.tray.show_message("更换形象", "抠图失败，已使用原图：%s" % message[:40])

    def _apply_image(self, path):
        self.config["style"] = "image"
        self.config["image_path"] = path
        self.config.save()
        self.pet.apply_config()
        self.tray.refresh_icon()

    def apply_settings(self):
        self.pet.apply_config()
        self.pet.set_always_on_top(bool(self.config.get("always_on_top", True)))
        self.tray.set_autostart(autostart.is_enabled())
        self.tray.refresh_icon()
        self.tts.reload()

    def quit(self):
        self.pet.stop()
        self.pet.save_position()
        self.tts.shutdown()
        self.ai.cancel()
        self.config.save()
        self.app.quit()
