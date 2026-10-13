import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QDialog

from pet.config import Config
from pet import assets
from pet.settings_dialog import SettingsDialog
from pet.state_machine import PetState

APP = QApplication.instance() or QApplication([])


class ConfigCompatibilityTests(unittest.TestCase):
    def test_bad_types_and_out_of_range_values_fall_back_without_losing_valid_ai(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({
                "scale": "giant", "fps": 500, "focus_mode": "yes",
                "proactive_chat_enabled": False, "ai": {
                    "enabled": True, "base_url": "https://example.test/v1",
                    "model": "model-a", "fallback_models": "model-b, model-c",
                    "system_prompt": "keep this persona", "timeout": 0,
                },
            }), encoding="utf-8")
            config = Config(path)
            self.assertEqual(config["scale"], 1.5)
            self.assertEqual(config["fps"], 30)
            self.assertFalse(config["focus_mode"])
            self.assertFalse(config["proactive_chat_enabled"])
            self.assertTrue(config["ai"]["enabled"])
            self.assertEqual(config["ai"]["base_url"], "https://example.test/v1")
            self.assertEqual(config["ai"]["fallback_models"], ["model-b", "model-c"])
            self.assertEqual(config["ai"]["system_prompt"], "keep this persona")
            self.assertEqual(config["ai"]["timeout"], 30)

    def test_huge_json_numbers_and_invalid_utf8_recover_to_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({
                "scale": 10 ** 400,
                "start_position": [10 ** 400, -(10 ** 400)],
            }), encoding="utf-8")
            config = Config(path)
            self.assertEqual(config["scale"], 1.5)
            self.assertIsNone(config["start_position"])
            path.write_bytes(b"{\xff invalid utf8")
            config = Config(path)
            self.assertEqual(config["scale"], 1.5)
            self.assertIsNone(config["start_position"])


class SettingsTransactionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.cfg = Config(self.root / "config.json")
        self.source = self.root / "candidate.png"
        pixmap = QPixmap(24, 24)
        pixmap.fill(QColor("royalblue"))
        pixmap.save(str(self.source))

    def tearDown(self):
        self.folder.cleanup()

    def test_cancelled_candidate_does_not_copy_or_change_active_image(self):
        active = self.root / "active.png"
        active.write_bytes(self.source.read_bytes())
        self.cfg["style"] = "image"
        self.cfg["image_path"] = str(active)
        asset_dir = self.root / "assets"
        with patch.object(assets, "ASSET_DIR", asset_dir):
            dialog = SettingsDialog(self.cfg)
            dialog._candidate_image = str(self.source)
            dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("image"))
            dialog.reject()
            self.assertEqual(self.cfg["image_path"], str(active))
            self.assertEqual(self.cfg["style"], "image")
            self.assertFalse(asset_dir.exists())
            dialog.close()

    def test_accept_defers_new_image_commit_to_shared_app_pipeline(self):
        self.cfg["style"] = "ghost"
        self.cfg["image_path"] = "previous.png"
        dialog = SettingsDialog(self.cfg)
        dialog._candidate_image = str(self.source)
        dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("image"))
        imported = []
        dialog.image_requested.connect(imported.append)
        with patch("pet.settings_dialog.autostart.is_enabled", return_value=False), \
             patch("pet.settings_dialog.autostart.set_enabled", return_value=True):
            dialog.accept()
        self.assertEqual(imported, [str(self.source)])
        self.assertEqual(self.cfg["style"], "ghost")
        self.assertEqual(self.cfg["image_path"], "previous.png")
        dialog.close()

    def test_image_preview_loads_without_touching_active_pet(self):
        self.cfg["style"] = "ghost"
        self.cfg["image_path"] = "previous.png"
        dialog = SettingsDialog(self.cfg)
        dialog._candidate_image = str(self.source)
        dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("image"))
        dialog._refresh_preview()
        self.assertFalse(dialog.preview.pixmap().isNull())
        self.assertEqual(self.cfg["style"], "ghost")
        dialog.close()

    def test_invalid_candidate_is_reported_without_changing_active_style(self):
        broken = self.root / "broken.png"
        broken.write_bytes(b"not an image")
        self.cfg["style"] = "doro"
        self.cfg["image_path"] = "old.png"
        dialog = SettingsDialog(self.cfg)
        dialog._candidate_image = str(broken)
        dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("image"))
        with patch("pet.settings_dialog.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_called_once()
        self.assertEqual(self.cfg["style"], "doro")
        self.assertEqual(self.cfg["image_path"], "old.png")
        self.assertEqual(dialog.result(), QDialog.Rejected)
        dialog.close()

    def test_abandoned_invalid_image_does_not_block_builtin_style_save(self):
        broken = self.root / "broken.png"
        broken.write_bytes(b"not an image")
        self.cfg["style"] = "girl"
        self.cfg["image_path"] = "old.png"
        dialog = SettingsDialog(self.cfg)
        dialog._candidate_image = str(broken)
        dialog.style_combo.setCurrentIndex(dialog.style_combo.findData("ghost"))
        imported = []
        dialog.image_requested.connect(imported.append)
        with patch("pet.settings_dialog.autostart.is_enabled", return_value=False), \
             patch("pet.settings_dialog.autostart.set_enabled", return_value=True), \
             patch("pet.settings_dialog.QMessageBox.warning") as warning:
            dialog.accept()
        warning.assert_not_called()
        self.assertEqual(self.cfg["style"], "ghost")
        self.assertEqual(self.cfg["image_path"], "old.png")
        self.assertEqual(imported, [])
        self.assertEqual(dialog.result(), QDialog.Accepted)
        dialog.close()


class AppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.config = Config(Path(self.folder.name) / "config.json")
        self.runtime = Mock()
        from pet.app import DesktopPetApp
        with patch("pet.app.Config", return_value=self.config):
            self.controller = DesktopPetApp(self.runtime)

    def tearDown(self):
        self.controller.quit()
        for widget in (self.controller.chat_panel, self.controller.input_bubble,
                       self.controller.speech, self.controller.pet,
                       self.controller.tray.menu):
            widget.close()
            widget.deleteLater()
        APP.processEvents()
        self.folder.cleanup()

    def test_focus_tray_toggle_applies_and_persists_without_restart(self):
        with patch.object(self.config, "save") as save:
            self.controller.on_tray_action("focus_mode:1")
            self.assertTrue(self.controller.pet.sm.focus_mode)
            self.assertTrue(self.config["focus_mode"])
            self.assertTrue(self.controller.tray.focus_action.isChecked())
            save.assert_called_once()

    def test_unconfigured_chat_uses_local_persona_reply(self):
        self.controller.pet.show()
        with patch.object(self.controller.persona, "offline_reply", return_value="我在这里。"):
            self.controller.on_user_message("你好")
        self.assertEqual(self.controller.chat_panel.turns[-1]["user"], "你好")
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "我在这里。")
        self.assertEqual(self.controller.chat_panel.turns[-1]["status"], "complete")
        self.assertFalse(self.controller.ai._placeholder_timer.isActive())

    def test_failed_retry_reuses_existing_transcript_turn(self):
        self.controller.pet.show()
        with patch.object(self.controller.ai, "is_configured", return_value=True), \
             patch.object(self.controller.ai, "send") as send:
            self.controller.on_user_message("hello")
            self.controller.chat_panel.set_reply("temporary error", "failed")
            self.controller.retry_reply()
        self.assertEqual(len(self.controller.chat_panel.turns), 1)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args.args[0], "hello")
        self.assertEqual(self.controller.chat_panel.turns[0]["reply"], "")
        self.assertEqual(self.controller.chat_panel.turns[0]["status"], "waiting")

    def test_local_action_feedback_is_scoped_to_its_command_turn(self):
        self.controller.pet.show()
        self.controller.on_user_message("跳舞")
        dance = self.controller.chat_panel.turns[-1]
        self.controller.on_user_message("心情")
        mood = self.controller.chat_panel.turns[-1]
        self.assertIn("跳", dance["reply"])
        self.assertTrue(mood["reply"])
        self.assertNotEqual(dance["reply"], mood["reply"])
        self.assertEqual(len(self.controller.chat_panel.turns), 2)
        self.assertTrue(self.controller.input_bubble.retry_btn.isHidden())

    def test_clear_chat_cancels_request_and_retry_target(self):
        self.controller.pet.show()
        with patch.object(self.controller.ai, "is_configured", return_value=True), \
             patch.object(self.controller.ai, "send"):
            self.controller.on_user_message("hello")
        self.controller.ai._history.append({"role": "user", "content": "hello"})
        self.controller._talk_timer.start(60000)
        self.controller.chat_panel.clear_button.click()
        self.assertEqual(self.controller.chat_panel.turns, [])
        self.assertEqual(self.controller._current_user_text, "")
        self.assertEqual(self.controller.ai._history, [])
        self.assertFalse(self.controller._talk_timer.isActive())

    def test_stop_during_waiting_replaces_placeholder_and_preserves_turn(self):
        self.controller.pet.show()
        with patch.object(self.controller.ai, "is_configured", return_value=True), \
             patch.object(self.controller.ai, "send"), \
             patch.object(self.controller.ai, "stop", return_value=""):
            self.controller.on_user_message("hello")
            self.controller._ai_busy = True
            self.controller.stop_reply()
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "已停止。")
        self.assertEqual(self.controller.chat_panel.turns[-1]["status"], "stopped")
        self.assertEqual(self.controller.speech._text, "已停止。")

    def test_failed_partial_stays_visible_and_retryable(self):
        self.controller.pet.show()
        self.controller.chat_panel.begin_turn("hello")
        self.controller._current_user_text = "hello"
        self.controller.ai.partial_text = "partial answer"
        self.controller.on_failure("request failed")
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "partial answer")
        self.assertEqual(self.controller.chat_panel.turns[-1]["status"], "interrupted")
        self.assertFalse(self.controller.input_bubble.retry_btn.isHidden())

    def test_late_ai_callbacks_do_not_pop_up_after_hide(self):
        self.controller.pet.show()
        self.controller.pet.hide()
        self.controller.chat_panel.begin_turn("hello")
        self.controller.on_chunk("late")
        self.controller.on_reply("late complete")
        self.controller.on_failure("late failure")
        self.controller.on_persona_say("late chatter")
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "")
        self.assertFalse(self.controller.speech.isVisible())

    def test_esc_during_ai_wait_finishes_talk_after_late_success(self):
        self.controller.pet.show()
        self.controller.pet.enter_talk()
        self.controller.input_bubble.show()
        self.controller._ai_busy = True
        self.controller.input_bubble.hide()
        self.controller._on_input_closed()
        self.assertEqual(self.controller.pet.sm.state, PetState.TALK)
        self.controller.on_reply("done")
        self.assertTrue(self.controller._talk_timer.isActive())
        self.assertEqual(self.controller.pet.sm.state, PetState.TALK)

    def test_failure_after_esc_returns_pet_to_idle(self):
        self.controller.pet.show()
        self.controller.pet.enter_talk()
        self.controller.chat_panel.begin_turn("hello")
        self.controller.ai.partial_text = "partial"
        self.controller.input_bubble.show()
        self.controller._ai_busy = True
        self.controller.input_bubble.hide()
        self.controller._on_input_closed()
        self.controller.on_failure("network failed")
        self.assertNotEqual(self.controller.pet.sm.state, PetState.TALK)
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "partial")
        self.assertEqual(self.controller.chat_panel.turns[-1]["status"], "interrupted")
        self.assertIn("中断", self.controller.speech._text)

    def test_settings_save_cancels_and_finishes_pending_reply(self):
        self.controller.pet.show()
        self.controller.pet.enter_talk()
        self.controller.chat_panel.begin_turn("hello")
        self.controller.ai.partial_text = "some words"
        self.controller._ai_busy = True
        self.controller.apply_settings()
        self.assertFalse(self.controller._ai_busy)
        self.assertEqual(self.controller.chat_panel.turns[-1]["reply"], "some words")
        self.assertEqual(self.controller.chat_panel.turns[-1]["status"], "stopped")

    def test_reply_does_not_interrupt_physical_drag_or_release(self):
        pet = self.controller.pet
        pet.show()
        local = QPointF(35, 35)
        global_pos = QPointF(pet.x() + 35, pet.y() + 35)
        APP.sendEvent(pet, QMouseEvent(QEvent.MouseButtonPress, local, global_pos,
                                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        moved_local = QPointF(55, 35)
        moved_global = global_pos + QPointF(30, 0)
        APP.sendEvent(pet, QMouseEvent(QEvent.MouseMove, moved_local, moved_global,
                                       Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
        self.assertEqual(pet.sm.state, PetState.DRAG)
        self.controller.chat_panel.begin_turn("hello")
        self.controller.on_reply("done")
        self.assertEqual(pet.sm.state, PetState.DRAG)
        self.assertTrue(pet._dragging)
        release = QMouseEvent(QEvent.MouseButtonRelease, moved_local, moved_global,
                              Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        with patch.object(pet, "_release_velocity", return_value=QPointF(0, 0)):
            APP.sendEvent(pet, release)
        self.assertEqual(pet.sm.state, PetState.FALL)

    def test_reopening_chat_cancels_pending_talk_return(self):
        self.controller.pet.show()
        self.controller.pet.enter_talk()
        self.controller.chat_panel.begin_turn("hello")
        self.controller.input_bubble.hide()
        self.controller.on_reply("done")
        self.assertTrue(self.controller._talk_timer.isActive())
        self.controller.open_chat()
        self.assertFalse(self.controller._talk_timer.isActive())
        self.controller._on_talk_timeout()
        self.assertEqual(self.controller.pet.sm.state, PetState.TALK)

    def test_delayed_hint_is_suppressed_when_hidden_or_focused(self):
        self.controller.pet.show()
        self.config["focus_mode"] = True
        self.controller._show_hint()
        self.assertFalse(self.controller.speech.isVisible())
        self.config["focus_mode"] = False
        self.controller.pet.hide()
        self.controller._show_hint()
        self.assertFalse(self.controller.speech.isVisible())


if __name__ == "__main__":
    unittest.main()
