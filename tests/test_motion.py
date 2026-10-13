import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.pet_window import PetWindow
from pet.state_machine import Context, PetState, StateMachine

APP = QApplication.instance() or QApplication([])


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.config = Config(Path(self.tmp.name) / "config.json")
        self.pet = PetWindow(self.config)

    def tearDown(self):
        self.pet.stop()
        self.pet.close()
        APP.processEvents()
        self.tmp.cleanup()

    def test_talk_cancels_scripted_dance_and_wins_next_tick(self):
        self.pet.dance()
        self.assertGreater(self.pet._dance_left, 0)
        self.pet.enter_talk()
        self.assertEqual(self.pet.sm.state, PetState.TALK)
        self.assertEqual(self.pet._dance_left, 0)
        with patch.object(self.pet, "_render"):
            self.pet._tick()
        self.assertEqual(self.pet.sm.state, PetState.TALK)

    def test_talk_transition_uses_last_rendered_react_phase(self):
        self.pet.sm.force(PetState.REACT)
        self.pet.sm.t = 0.47
        self.pet._last_state = PetState.REACT
        self.pet._render()
        self.pet.enter_talk()
        with patch.object(self.pet, "_render"):
            self.pet._tick()
        self.assertEqual(self.pet._state_transition[:2], (PetState.REACT, 0.47))

    def test_focus_toggle_stops_autonomous_walk_and_hop(self):
        self.pet.sm.force(PetState.WALK)
        self.pet.config["focus_mode"] = True
        self.pet.apply_config()
        self.assertEqual(self.pet.sm.state, PetState.IDLE)
        self.pet.config["focus_mode"] = False
        self.pet.apply_config()
        self.pet.sm.force(PetState.HOP)
        self.pet.config["focus_mode"] = True
        self.pet.apply_config()
        self.assertEqual(self.pet.sm.state, PetState.FALL)
        self.pet.sm.force(PetState.IDLE)
        self.pet.sm.on_startle(1)
        self.assertEqual(self.pet.sm.state, PetState.IDLE)

    def test_focus_mode_prevents_autonomous_hop_and_cursor_follow(self):
        sm = StateMachine(follow_cursor=True, focus_mode=True, rng=random.Random(4))
        sm.duration = 0
        ctx = Context(QRect(0, 0, 800, 600), QPoint(200, 460), QSize(140, 140),
                      QPoint(700, 300), focus_mode=True)
        sm._choose_next_idle()
        self.assertNotEqual(sm.state, PetState.HOP)
        self.assertNotEqual(sm.state, PetState.WALK)

    def test_eye_look_eases_towards_cursor(self):
        sm = StateMachine(rng=random.Random(8))
        ctx = Context(QRect(0, 0, 800, 600), QPoint(200, 200), QSize(140, 140),
                      QPoint(700, 200))
        sm.tick(1 / 60, ctx)
        self.assertGreater(sm.look.x(), 0.0)
        self.assertLess(sm.look.x(), 1.0)

    def test_blink_phase_is_smooth_and_continuous_across_state_change(self):
        from pet.animation import _pose
        values = [_pose(PetState.IDLE, 0.0, 140, blink_t=t)[-1]
                  for t in (3.0, 3.1, 3.2, 3.26, 3.32)]
        self.assertEqual(values[0], 0.0)
        self.assertAlmostEqual(values[1], 0.5)
        self.assertEqual(values[2], 1.0)
        self.assertAlmostEqual(values[3], 0.5)
        self.assertAlmostEqual(values[4], 0.0)
        talk_blink = _pose(PetState.TALK, 0.0, 140, blink_t=3.1)[-1]
        self.assertAlmostEqual(talk_blink, values[1])

    def test_scripted_walk_keeps_its_facing_with_follow_cursor_enabled(self):
        sm = StateMachine(follow_cursor=True, rng=random.Random(9))
        sm.force(PetState.WALK)
        sm.facing = 1
        ctx = Context(QRect(0, 0, 800, 600), QPoint(200, 200), QSize(140, 140),
                      QPoint(0, 200))
        sm.tick(0.05, ctx, scripted_walk=True)
        self.assertEqual(sm.facing, 1)

    def test_scripted_walk_suppresses_cursor_startle(self):
        self.pet._walk_target = 600
        self.pet._last_cursor = QPoint(0, 0)
        ctx = self.pet._context()
        ctx.cursor = QPoint(4000, 4000)
        with patch.object(self.pet.sm, "on_startle") as startle:
            self.pet._update_cursor_awareness(0.016, ctx)
        startle.assert_not_called()

    def test_focus_setting_does_not_block_explicit_walk_or_dance(self):
        self.pet.config["focus_mode"] = True
        self.pet.apply_config()
        with patch.object(self.pet, "cursor") as cursor:
            cursor.return_value.pos.return_value = QPoint(500, 300)
            self.assertTrue(self.pet.walk_to_cursor())
        self.assertIsNotNone(self.pet._walk_target)
        self.assertTrue(self.pet.dance())
        self.assertEqual(self.pet.sm.state, PetState.HOP)

    def test_saved_position_on_secondary_negative_monitor_is_preserved(self):
        class Screen:
            def __init__(self, rect):
                self.rect = rect

            def availableGeometry(self):
                return self.rect

        screens = [Screen(QRect(0, 0, 1920, 1080)),
                   Screen(QRect(-1600, -100, 1600, 900))]
        self.config["start_position"] = [-1200, 100]
        with patch("pet.pet_window.QApplication.screens", return_value=screens):
            self.pet._place_initial()
        self.assertEqual(self.pet.pos(), QPoint(-1200, 100))

    def test_saved_position_recovers_after_monitor_removal(self):
        class Screen:
            def __init__(self, rect):
                self.rect = rect

            def availableGeometry(self):
                return self.rect

        primary = Screen(QRect(0, 0, 1280, 720))
        secondary = Screen(QRect(-1600, 0, 1600, 900))
        with patch("pet.pet_window.QApplication.screens", return_value=[primary]):
            self.pet.move(-1200, 100)
            self.pet._on_screen_removed(secondary)
        self.assertGreaterEqual(self.pet.x(), 0)
        self.assertLessEqual(self.pet.x() + self.pet.width(), 1280)

    def test_drag_uses_screen_under_global_mouse_position(self):
        class Screen:
            def availableGeometry(self):
                return QRect(800, 0, 800, 600)

        secondary = Screen()
        self.pet._dragging = True
        self.pet._drag_offset = QPoint(10, 10)
        event = QMouseEvent(QEvent.MouseMove, QPointF(100, 100), QPointF(900, 200),
                            Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
        with patch("pet.pet_window.QApplication.screenAt", return_value=secondary):
            self.pet.mouseMoveEvent(event)
        self.assertEqual(self.pet.pos(), QPoint(890, 190))

    def test_minimized_or_closed_perch_falls_free(self):
        class Clock:
            def restart(self):
                return 16

        for visible, minimized, rect in ((True, True, (100, 100, 500, 400)),
                                         (False, False, (100, 100, 500, 400)),
                                         (True, False, None)):
            with self.subTest(visible=visible, minimized=minimized, rect=rect):
                self.pet._perch_hwnd = 123
                self.pet.sm.force(PetState.IDLE)
                self.pet._elapsed = Clock()
                with patch("pet.win32util.is_window_visible", return_value=visible), \
                        patch("pet.win32util.is_window_minimized", return_value=minimized), \
                        patch("pet.win32util.window_rect", return_value=rect), \
                        patch.object(self.pet, "_render"):
                    self.pet._tick()
                self.assertEqual(self.pet.sm.state, PetState.FALL)
                self.assertEqual(self.pet._perch_hwnd, 0)

    def test_explicit_unperch_releases_pet_into_fall(self):
        self.pet._perch_hwnd = 123
        self.pet.sm.force(PetState.IDLE)
        self.assertTrue(self.pet.unperch())
        self.assertEqual(self.pet.sm.state, PetState.FALL)
        self.assertFalse(self.pet.unperch())

    def test_perch_advances_animation_clock(self):
        self.pet._perch_hwnd = 123
        with patch("pet.win32util.is_window_visible", return_value=True), \
                patch("pet.win32util.is_window_minimized", return_value=False), \
                patch("pet.win32util.window_rect", return_value=(100, 100, 500, 400)), \
                patch.object(self.pet, "_render"):
            class Clock:
                def restart(self):
                    return 80
            self.pet._elapsed = Clock()
            before = self.pet.sm.t
            self.pet._tick()
        self.assertGreater(self.pet.sm.t, before)


if __name__ == "__main__":
    unittest.main()
