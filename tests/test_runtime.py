import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.pet_window import PetWindow
from pet.sprite import ImageSprite
from pet.state_machine import Context, PetState, StateMachine
from pet.ai.client import AIClient
from pet import assets, cutout

APP = QApplication.instance() or QApplication([])


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.sm = StateMachine(rng=random.Random(1))
        self.ctx = Context(QRect(0, 0, 800, 600), QPoint(200, 460),
                           QSize(140, 140), QPoint(700, 300))

    def test_click_after_press_leaves_drag(self):
        self.sm.on_press()
        self.sm.on_click(pet=True)
        self.assertEqual(self.sm.state, PetState.PET)

    def test_fall_returns_to_idle_after_landing(self):
        self.sm.on_press()
        self.sm.on_release()
        self.sm.tick(0.04, self.ctx)
        self.assertEqual(self.sm.state, PetState.IDLE)
        self.assertTrue(self.sm.just_landed)

    def test_follow_cursor_walks_towards_cursor(self):
        self.sm.follow_cursor = True
        self.sm.force(PetState.WALK)
        self.sm.facing = -1
        self.assertGreater(self.sm.tick(0.04, self.ctx).x(), 0)

    def test_throw_preserves_release_velocity(self):
        self.sm.on_press()
        self.sm.on_release(QPointF(700, -400))
        self.assertEqual(self.sm.state, PetState.THROWN)
        self.assertEqual(self.sm.vx, 700)
        self.assertEqual(self.sm.vy, -400)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.cfg = Config(Path(self.folder.name) / "config.json")
        self.pet = PetWindow(self.cfg)

    def tearDown(self):
        self.pet.stop()
        self.pet.close()
        APP.processEvents()
        self.folder.cleanup()

    def test_hide_pauses_rendering_and_show_resumes(self):
        self.pet.start()
        self.pet.hide()
        clock = self.pet._clock
        QTest.qWait(160)
        self.assertEqual(self.pet._clock, clock)
        self.assertFalse(self.pet._keep_top_timer.isActive())
        self.pet.show()
        QTest.qWait(100)
        self.assertGreater(self.pet._clock, clock)

    def test_disable_topmost_keeps_visible_window(self):
        self.pet.start()
        self.pet.set_always_on_top(False)
        self.assertTrue(self.pet.isVisible())

    def test_press_release_reacts_and_drag_still_falls(self):
        for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
            event = QMouseEvent(kind, QPointF(100, 20), QPointF(300, 300),
                                Qt.LeftButton, Qt.LeftButton if kind == QEvent.MouseButtonPress
                                else Qt.NoButton, Qt.NoModifier)
            APP.sendEvent(self.pet, event)
        self.assertEqual(self.pet.sm.state, PetState.PET)
        self.pet.sm.on_press()
        self.pet.sm.on_release()
        self.assertEqual(self.pet.sm.state, PetState.FALL)

    def test_sleep_clock_uses_full_low_fps_interval(self):
        class Clock:
            def restart(self):
                return 125
        self.pet._elapsed = Clock()
        self.pet.sm.force(PetState.SLEEP)
        self.pet._tick()
        self.assertAlmostEqual(self.pet.sm.t, 0.125)

    def test_target_walk_uses_correct_facing_and_stops_at_edge(self):
        ctx = self.pet._context()
        self.pet.move(ctx.screen.right() - self.pet.width() + 1, self.pet.y())
        self.pet._walk_target = ctx.screen.right() + 1000
        self.pet._walk_step(0.04, self.pet._context())
        self.assertIsNone(self.pet._walk_target)
        self.pet.move(ctx.screen.left() + 200, self.pet.y())
        self.pet._walk_target = self.pet.x() - 100
        self.pet.sm.force(PetState.IDLE)
        self.pet._walk_step(0.04, self.pet._context())
        self.assertEqual(self.pet.sm.facing, -1)

    def test_gif_prepare_detects_different_pixmap_content(self):
        sprite = ImageSprite("")
        image = QPixmap(60, 60)
        image.fill(QColor("red"))
        sprite._prepare(image, 100)
        before = sprite._scaled.toImage().pixelColor(20, 20)
        image.fill(QColor("blue"))
        sprite._prepare(image, 100)
        after = sprite._scaled.toImage().pixelColor(20, 20)
        self.assertNotEqual(before, after)

    def test_frame_limit_changes_without_restarting(self):
        self.pet.start()
        self.pet.sm.force(PetState.WALK)
        self.cfg["fps"] = 15
        self.pet.apply_config()
        self.assertEqual(self.pet._timer.interval(), 66)

    def test_slow_motion_accumulates_subpixel_steps(self):
        class Clock:
            def restart(self):
                return 16
        self.pet._elapsed = Clock()
        self.pet.move(200, 200)
        self.pet.sm.walk_speed = 10
        self.pet.sm.scale = 0.5
        self.pet.sm.force(PetState.WALK)
        self.pet.sm.facing = 1
        before = self.pet.x()
        for _ in range(25):
            self.pet._tick()
        self.assertGreater(self.pet.x(), before)

    def test_actual_gif_pauses_when_hidden_and_resumes(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional")
        path = str(Path(self.folder.name) / "animated.gif")
        first, second = Image.new("RGB", (30, 30), "red"), Image.new("RGB", (30, 30), "blue")
        first.save(path, save_all=True, append_images=[second], duration=80, loop=0)
        self.cfg["style"] = "image"
        self.cfg["image_path"] = path
        self.pet.apply_config()
        self.pet.start()
        self.pet.hide()
        from PySide6.QtGui import QMovie
        self.assertEqual(self.pet._sprite._movie.state(), QMovie.Paused)
        frame = self.pet._sprite._movie.currentFrameNumber()
        QTest.qWait(200)
        self.assertEqual(self.pet._sprite._movie.currentFrameNumber(), frame)
        self.pet.show()
        self.assertEqual(self.pet._sprite._movie.state(), QMovie.Running)

    def test_cancelled_settings_keep_active_image(self):
        folder = Path(self.folder.name)
        source_a, source_b = folder / "a.png", folder / "b.png"
        image = QPixmap(30, 30)
        image.fill(QColor("red"))
        image.save(str(source_a))
        image.fill(QColor("blue"))
        image.save(str(source_b))
        with patch.object(assets, "ASSET_DIR", folder / "assets"):
            active = assets.import_image(source_a)
            candidate = assets.import_image(source_b)
            self.assertTrue(Path(active).is_file())
            self.assertTrue(Path(candidate).is_file())


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.cfg = Config(Path(self.folder.name) / "config.json")

    def tearDown(self):
        self.folder.cleanup()

    def test_cancel_stops_delayed_ai_placeholder(self):
        client = AIClient(self.cfg)
        replies = []
        client.reply_ready.connect(replies.append)
        client.send("hello")
        client.cancel()
        QTest.qWait(300)
        self.assertEqual(replies, [])

    def test_ai_history_is_bounded_after_success(self):
        from PySide6.QtCore import QByteArray
        from PySide6.QtNetwork import QNetworkReply
        client = AIClient(self.cfg)
        self.cfg["ai"]["max_history"] = 4
        for i in range(12):
            client._history.append({"role": "user", "content": str(i)})
            client._pending_text = str(i)
            client._stream_text = "reply"
            client._reply = Mock()
            client._reply.readAll.return_value = QByteArray()
            client._reply.error.return_value = QNetworkReply.NoError
            client._on_finished()
        self.assertEqual(len(client._history), 4)
        self.assertEqual(client._history[-1]["role"], "assistant")

    def test_cutout_releases_session_after_success_and_failure(self):
        for error in (None, RuntimeError("decode failed")):
            cutout._session = object()
            worker = cutout.CutoutWorker("unused.png")
            result, errors = [], []
            worker.done.connect(result.append)
            worker.failed.connect(errors.append)
            with patch.object(cutout, "cutout", return_value="out.png", side_effect=error):
                worker.run()
            self.assertIsNone(cutout._session)
            self.assertEqual(errors, [] if error is None else ["decode failed"])

    def test_cutout_availability_does_not_import_inference(self):
        with patch.object(cutout, "find_spec", return_value=object()) as find:
            self.assertTrue(cutout.rembg_available())
            self.assertEqual(find.call_count, 3)

    def test_quit_waits_for_cutout_without_blocking_ui(self):
        from pet.app import DesktopPetApp
        runtime = Mock()
        with patch("pet.app.Config", return_value=self.cfg):
            controller = DesktopPetApp(runtime)
        worker = Mock()
        worker.isRunning.return_value = True
        controller._cut_worker = worker
        controller.quit()
        runtime.quit.assert_not_called()
        with patch.object(controller, "sender", return_value=worker):
            controller._on_cutout_finished()
        runtime.quit.assert_called_once()
        worker.deleteLater.assert_called_once()
        for widget in (controller.pet, controller.input_bubble, controller.speech,
                       controller.tray.menu):
            widget.close()
            widget.deleteLater()

    def test_hidden_pet_does_not_run_personality_or_popup(self):
        from pet.app import DesktopPetApp
        with patch("pet.app.Config", return_value=self.cfg):
            controller = DesktopPetApp(Mock())
        with patch.object(controller.persona, "tick") as tick:
            controller._on_idle_tick()
            tick.assert_not_called()
        controller.on_persona_say("hello")
        self.assertFalse(controller.speech.isVisible())
        for widget in (controller.pet, controller.input_bubble, controller.speech,
                       controller.tray.menu):
            widget.close()
            widget.deleteLater()


if __name__ == "__main__":
    unittest.main()
