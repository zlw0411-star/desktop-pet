from PySide6.QtCore import QObject, QTimer, QEvent
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QFileDialog

from . import autostart, cutout
from .ai.client import AIClient
from .assets import import_image
from .input_bubble import InputBubble
from .cutout import CutoutWorker
from .speech_bubble import SpeechBubble
from .config import Config
from .personality import Personality
from .pet_window import PetWindow
from .settings_dialog import SettingsDialog
from .tray import TrayManager
from .chat_panel import ChatPanel
from .state_machine import PetState


class DesktopPetApp(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.config = Config()

        self._cut_worker = None
        self._pending_image = None
        self._speech_active = False
        self._ai_busy = False
        self._quitting = False

        self.pet = PetWindow(self.config)
        self._talk_timer = QTimer(self)
        self._talk_timer.setSingleShot(True)
        self._talk_timer.timeout.connect(self._on_talk_timeout)
        self.tray = TrayManager(self.config)
        self.input_bubble = InputBubble()
        self.speech = SpeechBubble()
        self.chat_panel = ChatPanel(self.pet)
        self.ai = AIClient(self.config)
        self.persona = Personality(self.config)
        self._greeted = False
        self.speech.set_anchor_getter(lambda: self.pet)

        self.pet.chat_requested.connect(self.open_chat)
        self.pet.context_menu_requested.connect(self.show_menu)
        self.pet.image_dropped.connect(self.set_custom_image)
        self.pet.file_dropped.connect(self.on_file_dropped)
        self.pet.petted.connect(self.on_petted)
        self.pet.thrown.connect(self.on_thrown)
        self.tray.action_triggered.connect(self.on_tray_action)
        self.input_bubble.submitted.connect(self.on_user_message)
        self.input_bubble.stop_requested.connect(self.stop_reply)
        self.input_bubble.retry_requested.connect(self.retry_reply)
        self.ai.reply_ready.connect(self.on_reply)
        self.ai.failed.connect(self.on_failure)
        self.ai.chunk.connect(self.on_chunk)
        self.ai.busy_changed.connect(self._on_ai_busy)
        self.ai.status_changed.connect(self._on_ai_status)
        self.input_bubble.closed.connect(self._on_input_closed)
        self.persona.say.connect(self.on_persona_say)
        self.persona.act.connect(self.on_persona_act)
        self.speech.full_reply_requested.connect(self.show_chat_panel)
        self.chat_panel.clear_requested.connect(self._clear_chat)
        self.pet.state_changed.connect(self._on_pet_state_changed)
        self.pet.installEventFilter(self)
        self.chat_panel.installEventFilter(self)

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(15000)
        self._idle_timer.timeout.connect(self._on_idle_tick)

        self.pet.set_always_on_top(bool(self.config.get("always_on_top", True)))

    def start(self):
        self.tray.set_pet_visible(True)
        self.tray.set_autostart(autostart.is_enabled())
        self.tray.show()
        self.pet.start()
        self.persona.remember_skip(int(self.pet.winId()))
        self.persona.remember_skip(int(self.input_bubble.winId()))
        self.persona.remember_skip(int(self.speech.winId()))
        self.persona.remember_skip(int(self.chat_panel.winId()))
        self._sync_persona_pause()
        self._idle_timer.start()
        if not self.config.get("shown_hint", False):
            QTimer.singleShot(1800, self._show_hint)

    def _show_hint(self):
        if (self._quitting or self._greeted or not self.pet.isVisible()
                or self.input_bubble.isVisible() or self.config.get("focus_mode", False)):
            return
        self.speech.finalize("双击我就能聊天哦～")
        self.config["shown_hint"] = True
        self.config.save()

    def open_chat(self):
        if self._quitting:
            return
        self._talk_timer.stop()
        self.pet.enter_talk()
        self.input_bubble.set_mode("ai" if self.ai.is_configured() else "offline")
        self.input_bubble.popup_beside(self.pet)
        self._sync_persona_pause()
        if not self._greeted:
            self._greeted = True
            self.speech.finalize("你好呀，和我说说话吧～")
            if not self.config.get("shown_hint", False):
                self.config["shown_hint"] = True
                self.config.save()

    def on_user_message(self, text):
        if self._quitting or not text.strip():
            return
        self.persona.on_chat()
        if self._ai_busy:
            # A new user action supersedes the current request. Keep any partial
            # answer in the transcript, and never let its late signal replace the action response.
            partial = self.ai.partial_text
            self.ai.cancel()
            if self.chat_panel.turns:
                self.chat_panel.set_reply(partial or "已中断。", "stopped")
            self._speech_active = False
            self.speech.hide()
            self._talk_timer.stop()
        self.chat_panel.begin_turn(text)
        self._current_user_text = ""
        self._handling_command = True
        self._command_output = ""
        self._last_command_feedback = ""
        if self.persona.try_command(text):
            self._handling_command = False
            result = self._last_command_feedback or self._command_output
            if result:
                self.chat_panel.set_reply(result)
            self.input_bubble.set_mode("ai" if self.ai.is_configured() else "offline")
            self.input_bubble.set_status("complete")
            return
        self._handling_command = False
        self._enter_talk_if_available()
        self._talk_timer.stop()
        self._speech_active = False
        self._current_user_text = text
        self.input_bubble.set_status("waiting")
        self.speech.show_stream()
        if not self.ai.is_configured():
            self.input_bubble.set_mode("offline")
            self._present_local_reply(self.persona.offline_reply(text))
            return
        self.input_bubble.set_mode("ai")
        self.speech.append("…")
        self.ai.send(text, mood_line=self.persona.mood_line())

    def _present_local_reply(self, text):
        if self._quitting or not self.pet.isVisible():
            return
        self.input_bubble.set_status("complete")
        self.chat_panel.set_reply(text)
        self.speech.finalize(text)
        self._speech_active = False
        self._enter_talk_if_available()

    def stop_reply(self):
        if not self._ai_busy:
            return
        partial = self.ai.stop()
        self.input_bubble.set_status("stopped")
        if self.chat_panel.turns:
            self.chat_panel.set_reply(partial or "已停止。", "stopped")
        if not self._quitting and self.pet.isVisible():
            self.speech.finalize((partial + "（已停止）") if partial else "已停止。")
        self._speech_active = False
        self._talk_timer.stop()
        if self.input_bubble.isVisible():
            self._enter_talk_if_available()
        else:
            self._finish_talk_if_available()

    def retry_reply(self):
        text = getattr(self, "_current_user_text", "")
        if self._quitting or self._ai_busy or not text:
            return
        if not self.ai.is_configured():
            self.input_bubble.set_mode("offline")
            self._current_user_text = ""
            self._present_local_reply(self.persona.offline_reply(text))
            return
        self._enter_talk_if_available()
        self._talk_timer.stop()
        self._speech_active = False
        self.speech.show_stream()
        self.speech.append("…")
        self.chat_panel.set_reply("", "waiting")
        self.input_bubble.set_status("waiting")
        self.input_bubble.set_mode("ai")
        self.ai.send(text, mood_line=self.persona.mood_line())

    def on_petted(self, head):
        if head:
            self.persona.on_pet_head()
        else:
            self.persona.on_pet_body()

    def on_thrown(self):
        self.persona.on_thrown()

    def on_file_dropped(self, path):
        self.persona.on_file(path)

    def on_persona_say(self, text):
        if getattr(self, "_handling_command", False):
            self._command_output = text
        if self._quitting or not self.pet.isVisible() or self._ai_busy:
            return
        self.speech.finalize(text)

    def on_persona_act(self, action):
        self._last_command_feedback = ""
        if action == "dance":
            ok = self.pet.dance()
            self._last_command_feedback = "好呀，跳一支给你看！" if ok else "现在没法跳舞，等我一下吧。"
        elif action == "come":
            ok = self.pet.walk_to_cursor()
            self._last_command_feedback = "我这就过来！" if ok else "我现在过不去，等一下再试吧。"
        elif action == "perch":
            hwnd = self.persona.last_hwnd
            ok = self.pet.perch(hwnd)
            self._last_command_feedback = "找到地方坐好啦。" if ok else "附近没有合适的位置坐下。"
        elif action == "unperch":
            ok = self.pet.unperch()
            self._last_command_feedback = "好，我下来啦。" if ok else "我现在没有坐在高处。"
        if self._last_command_feedback:
            self._speech_active = False
            self._talk_timer.stop()
            self.speech.finalize(self._last_command_feedback)

    def _on_pet_state_changed(self, _state):
        if _state != PetState.TALK:
            self._talk_timer.stop()
        self._sync_persona_pause()

    def _user_motion_active(self):
        pet = self.pet
        state = getattr(getattr(pet, "sm", None), "state", None)
        return bool(getattr(pet, "_dragging", False)
                    or state in (PetState.DRAG, PetState.FALL, PetState.THROWN, PetState.HOP)
                    or getattr(pet, "_dance_left", 0)
                    or getattr(pet, "_walk_target", None) is not None
                    or getattr(pet, "_perch_hwnd", 0))

    def _enter_talk_if_available(self):
        if self.pet.isVisible() and not self._user_motion_active():
            self.pet.enter_talk()

    def _finish_talk_if_available(self):
        if (self.pet.isVisible() and not self.input_bubble.isVisible()
                and not self._user_motion_active()
                and self.pet.sm.state == PetState.TALK):
            self.pet.finish_talk()

    def _on_talk_timeout(self):
        self._finish_talk_if_available()

    def _sync_persona_pause(self, *_):
        sleeping = getattr(getattr(self.pet, "sm", None), "state", None) == PetState.SLEEP
        paused = (self._quitting or not self.pet.isVisible() or self.input_bubble.isVisible()
                  or self.chat_panel.isVisible() or sleeping
                  or bool(self.config.get("focus_mode", False)) or self._ai_busy
                  or not self.config.get("proactive_chat_enabled", True))
        self.persona.set_paused(paused)

    def _on_ai_status(self, status):
        if not self._quitting:
            self.input_bubble.set_status(status, can_retry=(status == "failed"))

    def _on_idle_tick(self):
        self._sync_persona_pause()
        if not self.pet.isVisible() or self._quitting:
            return
        busy = self.input_bubble.isVisible() or self._ai_busy or self.speech.isVisible()
        self.persona.tick(busy)

    def _on_ai_busy(self, busy):
        self._ai_busy = busy
        if not self._quitting:
            self.input_bubble.set_busy(busy)
            self._sync_persona_pause()

    def _on_input_closed(self):
        if not self._ai_busy:
            self._finish_talk_if_available()
        self._sync_persona_pause()

    def eventFilter(self, watched, event):
        if watched in (self.chat_panel, self.pet) and event.type() in (QEvent.Show, QEvent.Hide):
            QTimer.singleShot(0, self._sync_persona_pause)
        return super().eventFilter(watched, event)

    def on_chunk(self, delta):
        if self._quitting or not self.pet.isVisible():
            return
        if not self._speech_active:
            self._speech_active = True
            self.speech.show_stream()
        self.speech.append(delta)
        self.chat_panel.append_reply(delta)

    def on_reply(self, text):
        if self._quitting or not self.pet.isVisible():
            return
        if not self._speech_active:
            self._speech_active = True
            self.speech.show_stream()
        self.speech.finalize(text)
        self.chat_panel.set_reply(text)
        self._speech_active = False
        self._enter_talk_if_available()
        self._schedule_talk_return()

    def on_failure(self, message):
        if self._quitting or not self.pet.isVisible():
            return
        partial = self.ai.partial_text
        shown = partial or message
        self.chat_panel.set_reply(partial or message, "interrupted" if partial else "failed")
        self.input_bubble.set_status("failed", can_retry=True)
        self.speech.finalize((partial + "（回复中断，可重试）") if partial else message)
        self._speech_active = False
        if not self.input_bubble.isVisible():
            self._finish_talk_if_available()

    def _schedule_talk_return(self):
        self._talk_timer.stop()
        if (not self.input_bubble.isVisible() and self.pet.isVisible()
                and self.pet.sm.state == PetState.TALK and not self._user_motion_active()):
            self._talk_timer.start(4000)

    def _clear_chat(self):
        self.ai.cancel()
        self.ai.reset_history()
        self._current_user_text = ""
        self._speech_active = False
        self._talk_timer.stop()
        self.input_bubble.set_status("stopped")
        self.speech.hide()
        if self.pet.isVisible() and not self.input_bubble.isVisible():
            self._finish_talk_if_available()

    def show_menu(self, global_pos):
        self.tray.menu.popup(global_pos)

    def show_chat_panel(self):
        if self._quitting:
            return
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.chat_panel.activateWindow()
        self._sync_persona_pause()

    def on_tray_action(self, action):
        if action == "toggle":
            visible = self.pet.isVisible()
            self.pet.setVisible(not visible)
            if visible:
                if self._ai_busy:
                    partial = self.ai.partial_text
                    if self.chat_panel.turns:
                        self.chat_panel.set_reply(partial or "已中断。", "stopped")
                    self.input_bubble.set_status("stopped")
                self.ai.cancel()
                self._talk_timer.stop()
                self.pet.finish_talk()
                self.input_bubble.hide()
                self.speech.hide()
                self.chat_panel.hide()
            self.tray.set_pet_visible(not visible)
            self._sync_persona_pause()
        elif action == "chat":
            self.pet.setVisible(True)
            self.tray.set_pet_visible(True)
            self.open_chat()
        elif action == "settings":
            self.open_settings()
        elif action.startswith("focus_mode:"):
            enabled = action.split(":", 1)[1] == "1"
            self.config["focus_mode"] = enabled
            self.config.save()
            self.pet.apply_config()
            self.tray.set_focus_mode(enabled)
            self._sync_persona_pause()
        elif action == "change_image":
            self.choose_image()
        elif action.startswith("autostart:"):
            enabled = action.split(":", 1)[1] == "1"
            autostart.set_enabled(enabled)
            actual = autostart.is_enabled()
            self.config["autostart"] = actual
            self.config.save()
            self.tray.set_autostart(actual)
            if actual != enabled:
                self.tray.show_message("开机启动", "系统未能应用开机启动设置。")
        elif action == "quit":
            self.quit()

    def open_settings(self):
        dialog = SettingsDialog(self.config, self.pet)
        dialog.settings_saved.connect(self.apply_settings)
        dialog.image_requested.connect(self.set_custom_image)
        dialog.exec()

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self.pet, "选择宠物形象图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if path:
            self.set_custom_image(path)

    def set_custom_image(self, path):
        if self._quitting:
            return
        if self._cut_worker is not None:
            self.tray.show_message("更换形象", "正在处理上一张图片，请稍等再换。")
            return
        reader = QImageReader(path)
        if not reader.canRead() or reader.read().isNull():
            self.tray.show_message("更换形象", "无法读取这张图片，请换个格式试试。")
            return
        stored = import_image(path)
        if not stored:
            self.tray.show_message("更换形象", "无法读取这张图片，请换个格式试试。")
            return
        self._pending_image = stored
        if (self.config.get("auto_cutout", True)
                and not stored.lower().endswith(".gif") and cutout.available()):
            self.tray.show_message("更换形象", "正在抠图，请稍等…")
            self._cut_worker = CutoutWorker(stored)
            self._cut_worker.done.connect(self._on_cutout_done)
            self._cut_worker.failed.connect(self._on_cutout_failed)
            self._cut_worker.finished.connect(self._on_cutout_finished)
            self._cut_worker.start()
        else:
            self._apply_image(stored)
            self.tray.show_message("更换形象", "已换成你的图片啦～")

    def _on_cutout_done(self, cut_path):
        if self._quitting:
            return
        self._apply_image(cut_path)
        self.tray.show_message("更换形象", "抠图完成，漂亮！")

    def _on_cutout_failed(self, message):
        if self._quitting:
            return
        if getattr(self, "_pending_image", None):
            self._apply_image(self._pending_image)
        self.tray.show_message("更换形象", "抠图失败，已使用原图：%s" % message[:40])

    def _on_cutout_finished(self):
        worker = self.sender()
        if self._cut_worker is worker:
            self._cut_worker = None
        if worker is not None:
            worker.deleteLater()
        if self._quitting:
            self.app.quit()

    def _apply_image(self, path):
        self.config["style"] = "image"
        self.config["image_path"] = path
        self.config.save()
        self.pet.apply_config()
        self.tray.refresh_icon()

    def apply_settings(self):
        cancelled_reply = self._ai_busy
        if self._ai_busy:
            partial = self.ai.partial_text
            self.ai.cancel()
            if self.chat_panel.turns:
                self.chat_panel.set_reply(partial or "设置已更新，当前回复已停止。", "stopped")
            if self.pet.isVisible():
                self.speech.finalize((partial + "（已停止）") if partial
                                     else "设置已更新，当前回复已停止。")
            self._speech_active = False
            self._talk_timer.stop()
            if self.pet.isVisible() and not self.input_bubble.isVisible():
                self._finish_talk_if_available()
        self.pet.apply_config()
        self.pet.set_always_on_top(bool(self.config.get("always_on_top", True)))
        self.tray.set_autostart(autostart.is_enabled())
        self.tray.refresh_icon()
        self.tray.set_focus_mode(bool(self.config.get("focus_mode", False)))
        self.input_bubble.set_mode("ai" if self.ai.is_configured() else "offline")
        if cancelled_reply:
            self.input_bubble.set_status("stopped")
        self._sync_persona_pause()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._idle_timer.stop()
        self._talk_timer.stop()
        self.pet.stop()
        self.pet.save_position()
        self.config["mood"] = self.persona.mood
        self.ai.cancel()
        self.persona.set_paused(True)
        self.config.save()
        self.pet.hide()
        self.input_bubble.hide()
        self.speech.hide()
        self.chat_panel.hide()
        self.tray.icon.hide()
        if self._cut_worker is None or not self._cut_worker.isRunning():
            self.app.quit()
