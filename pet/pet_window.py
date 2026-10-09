import math
import time
from collections import deque

from PySide6.QtCore import (QElapsedTimer, QPoint, QPointF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QWidget

from . import animation
from .effects import ParticleField
from .sprite import ImageSprite
from .state_machine import Context, PetState, StateMachine

BASE_SIZE = 140


class PetWindow(QWidget):
    chat_requested = Signal()
    context_menu_requested = Signal(QPoint)
    state_changed = Signal(object)
    image_dropped = Signal(str)
    file_dropped = Signal(str)
    petted = Signal(bool)
    thrown = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAcceptDrops(True)

        self.config = config
        self._running = False
        self.scale = float(config.get("scale", 1.0))
        self.style = config.get("style", "blob")
        self.size_px = int(BASE_SIZE * self.scale)
        self.setFixedSize(QSize(self.size_px, self.size_px))

        self._sprite = None
        self._load_sprite()

        self.sm = StateMachine(
            walk_speed=float(config.get("walk_speed", 60.0)),
            scale=self.scale,
            wander=bool(config.get("wander", True)),
            follow_cursor=bool(config.get("follow_cursor", False)),
            sleep_enabled=bool(config.get("sleep_enabled", True)),
        )

        self._frame = None
        self._dragging = False
        self._drag_offset = QPoint()
        self._moved = False
        self._last_state = self.sm.state
        self._fps = max(10, min(60, int(config.get("fps", 30))))
        self._mask_state = None
        self._mask_updated_at = float("-inf")

        self.particles = ParticleField()
        self._drag_samples = deque(maxlen=8)
        self._sx = 1.0
        self._sy = 1.0
        self._sx_v = 0.0
        self._sy_v = 0.0
        self._last_cursor = self.cursor().pos()
        self._startle_cooldown = 0.0
        self._sparkle_timer = 0.0
        self._clock = 0.0
        self._walk_target = None
        self._motion_remainder = QPointF()
        self._dance_left = 0
        self._perch_hwnd = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._elapsed = QElapsedTimer()
        self._elapsed.start()

        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.setInterval(4000)
        self._keep_top_timer.timeout.connect(self._keep_on_top)

        self._place_initial()

    def _keep_on_top(self):
        if not self.isVisible():
            return
        if self.windowFlags() & Qt.WindowStaysOnTopHint:
            self.raise_()

    def _place_initial(self):
        screen = self.screen().availableGeometry()
        saved = self.config.get("start_position")
        if isinstance(saved, (list, tuple)) and len(saved) == 2:
            pos = QPoint(int(saved[0]), int(saved[1]))
        else:
            pos = QPoint(screen.right() - self.size_px - 40,
                         screen.bottom() - self.size_px + 1)
        self.move(self._clamp(pos, screen))

    def start(self):
        self._running = True
        if self._sprite is not None and not self._sprite.valid:
            self._load_sprite()
        self.show()
        self._resume_animation()

    def _resume_animation(self):
        if not self._running or not self.isVisible():
            return
        self._elapsed.restart()
        self._last_cursor = self.cursor().pos()
        if self._sprite is not None:
            self._sprite.set_paused(False)
        self._render()
        self._timer.start(max(1, int(1000 / self._fps_for(self.sm.state))))
        self._keep_top_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._resume_animation()

    def hideEvent(self, event):
        self._timer.stop()
        self._keep_top_timer.stop()
        if self._sprite is not None:
            self._sprite.set_paused(True)
        if self._dragging:
            self._dragging = False
            self.sm.on_release()
        super().hideEvent(event)

    def _fps_for(self, state):
        table = {
            PetState.SLEEP: 8,
            PetState.IDLE: 18,
            PetState.REACT: 20,
            PetState.PET: 24,
            PetState.TALK: 24,
        }
        return max(6, min(self._fps, table.get(state, self._fps)))

    def _apply_interval(self):
        self._timer.setInterval(max(1, int(1000 / self._fps_for(self.sm.state))))

    def stop(self):
        self._running = False
        self._timer.stop()
        self._keep_top_timer.stop()
        if self._sprite is not None:
            self._sprite.stop()

    def _load_sprite(self):
        if self._sprite is not None:
            self._sprite.stop()
            self._sprite = None
        if self.style == "image":
            sprite = ImageSprite(self.config.get("image_path", ""))
            self._sprite = sprite if sprite.valid else None
            sprite.set_paused(not (self._running and self.isVisible()))

    def apply_config(self):
        self.scale = float(self.config.get("scale", 1.0))
        self.style = self.config.get("style", "blob")
        self._fps = max(10, min(60, int(self.config.get("fps", 30))))
        self.size_px = int(BASE_SIZE * self.scale)
        self.setFixedSize(QSize(self.size_px, self.size_px))
        self._load_sprite()
        self.sm.update_options(
            wander=bool(self.config.get("wander", True)),
            follow_cursor=bool(self.config.get("follow_cursor", False)),
            sleep_enabled=bool(self.config.get("sleep_enabled", True)),
            walk_speed=float(self.config.get("walk_speed", 60.0)),
            scale=self.scale,
        )
        self._mask_state = None
        self.move(self._clamp(self.pos(), self.screen().availableGeometry()))
        self._apply_interval()
        self._render()

    def _context(self):
        return Context(
            screen=self.screen().availableGeometry(),
            pos=self.pos(),
            size=self.size(),
            cursor=self.cursor().pos(),
            wander=bool(self.config.get("wander", True)),
            follow_cursor=bool(self.config.get("follow_cursor", False)),
            sleep_enabled=bool(self.config.get("sleep_enabled", True)),
            bottom_margin=int(self.config.get("bottom_margin", 6)),
        )

    def _tick(self):
        dt = min(self._elapsed.restart() / 1000.0, 0.25)
        self._clock += dt
        ctx = self._context()
        if self._perch_hwnd and not self._dragging:
            self._follow_perch()
        elif not self._dragging:
            extra = self._walk_step(dt, ctx)
            move = self.sm.tick(dt, ctx)
            if extra is not None:
                move = extra
            if not move.isNull():
                total = move + self._motion_remainder
                step = total.toPoint()
                intended = self.pos() + step
                clamped = self._clamp(intended, ctx.screen)
                self._motion_remainder = total - QPointF(step)
                if clamped.x() != intended.x():
                    self._motion_remainder.setX(0.0)
                if clamped.y() != intended.y():
                    self._motion_remainder.setY(0.0)
                self.move(clamped)
        else:
            self.sm.tick(dt, ctx)

        self._update_cursor_awareness(dt, ctx)
        self._handle_events(dt)
        self._spring(dt)
        self.particles.update(dt)
        self._ambient_sparkles(dt)

        if self.sm.state != self._last_state:
            prev = self._last_state
            self._last_state = self.sm.state
            self._motion_remainder = QPointF()
            self._apply_interval()
            self.state_changed.emit(self.sm.state)
            if self.sm.state == PetState.THROWN and prev != PetState.THROWN:
                self.thrown.emit()
            if self._dance_left and prev in (PetState.HOP, PetState.FALL) and self.sm.state in (
                    PetState.IDLE, PetState.WALK):
                self._dance_left -= 1
                if self._dance_left:
                    self.sm.force(PetState.HOP)
        self._render()

    def _handle_events(self, dt):
        if self.sm.just_landed:
            impact = self.sm.land_impact
            if impact > 0:
                cx = self.size_px * 0.5
                cy = self.size_px * 0.9
                self.particles.stars(cx, cy, count=min(9, 3 + int(impact / 220)))
                impulse = min(0.34, 0.10 + impact / 2400.0)
                self._sy = 1.0 - impulse
                self._sx = 1.0 + impulse
                self._sy_v = 0.0
                self._sx_v = 0.0
        if self.sm.state == PetState.DIZZY and self._last_state != PetState.DIZZY:
            self.particles.sweat(self.size_px * 0.72, self.size_px * 0.28, count=4)

    def _spring(self, dt):
        if (self._sx == 1.0 and self._sy == 1.0
                and abs(self._sx_v) < 0.01 and abs(self._sy_v) < 0.01):
            self._sx_v = self._sy_v = 0.0
            return
        k = 320.0
        c = 24.0
        step = 1.0 / 240.0
        remaining = dt
        while remaining > 1e-6:
            h = min(step, remaining)
            remaining -= h
            for attr, vel in (("_sx", "_sx_v"), ("_sy", "_sy_v")):
                x = getattr(self, attr)
                v = getattr(self, vel)
                v += (-k * (x - 1.0) - c * v) * h
                x += v * h
                setattr(self, attr, x)
                setattr(self, vel, v)
        for attr in ("_sx", "_sy"):
            if abs(getattr(self, attr) - 1.0) < 0.002:
                setattr(self, attr, 1.0)

    def _update_cursor_awareness(self, dt, ctx):
        self._startle_cooldown = max(0.0, self._startle_cooldown - dt)
        cursor = ctx.cursor
        last = self._last_cursor
        self._last_cursor = cursor
        if self._dragging or self._startle_cooldown > 0.0:
            return
        speed = math.hypot(cursor.x() - last.x(), cursor.y() - last.y()) / max(dt, 1e-3)
        center = QPointF(ctx.pos.x() + ctx.size.width() / 2.0,
                         ctx.pos.y() + ctx.size.height() * 0.55)
        dist = math.hypot(cursor.x() - center.x(), cursor.y() - center.y())
        can_react = self.sm.state in (PetState.IDLE, PetState.WALK, PetState.SLEEP,
                                      PetState.PET, PetState.REACT)
        if dist < ctx.size.width() * 0.78 and speed > 1500.0 and can_react:
            direction = 1 if cursor.x() < center.x() else -1
            self.sm.on_startle(direction)
            self.particles.sweat(center.x(), center.y() - ctx.size.height() * 0.3, count=4)
            self._startle_cooldown = 2.5

    def _ambient_sparkles(self, dt):
        if self.sm.state not in (PetState.IDLE, PetState.PET):
            return
        self._sparkle_timer += dt
        if self._sparkle_timer >= 0.6:
            self._sparkle_timer = 0.0
            if self.sm.rng.random() < 0.35:
                self.particles.sparkles(self.size_px * 0.5, self.size_px * 0.2, count=1)

    def _clamp(self, pos, screen):
        margin = int(self.config.get("bottom_margin", 6))
        x = max(screen.left(), min(pos.x(), screen.right() - self.width() + 1))
        y = max(screen.top(), min(pos.y(), screen.bottom() - self.height() + 1 - margin))
        return QPoint(int(x), int(y))

    def save_position(self):
        self.config["start_position"] = [int(self.pos().x()), int(self.pos().y())]

    def _compose(self, target):
        if self.style == "image" and self._sprite is not None:
            base = self._sprite.render(target, self.sm.state, self._clock,
                                       self.sm.facing, self.sm.look)
        else:
            base = animation.render_frame(target, self.sm.state, self.sm.t,
                                          self.sm.facing, self.sm.look, self.style)
        deforming = abs(self._sx - 1.0) > 0.01 or abs(self._sy - 1.0) > 0.01
        if deforming and self.style != "image":
            out = QPixmap(target, target)
            out.fill(Qt.transparent)
            painter = QPainter(out)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.translate(target / 2.0, target * 0.95)
            painter.scale(self._sx, self._sy)
            painter.translate(-target / 2.0, -target * 0.95)
            painter.drawPixmap(0, 0, base)
            painter.end()
            base = out
        return base

    def _render(self):
        dpr = max(1.0, float(self.devicePixelRatioF()))
        render_size = max(1, int(round(self.size_px * dpr)))
        frame = self._compose(render_size)
        frame.setDevicePixelRatio(dpr)
        self._frame = frame
        # Native window masks are much costlier than ordinary repainting.
        # Refresh immediately on state changes; otherwise cap them at 12 Hz.
        now = time.monotonic()
        if self.sm.state != self._mask_state or now - self._mask_updated_at >= 1 / 12:
            self._update_mask()
            self._mask_state = self.sm.state
            self._mask_updated_at = now
        self.update()

    def _update_mask(self):
        image = self._frame.toImage().scaled(
            self.size_px, self.size_px,
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        image.setDevicePixelRatio(1.0)
        mask = QPixmap.fromImage(image).mask()
        if mask.isNull():
            return
        region = QRegion(mask)
        for p in self.particles.items:
            r = max(p.size, 6.0)
            region = region.united(QRegion(
                int(p.x - r), int(p.y - r), int(r * 2), int(r * 2)))
        self.setMask(region)

    def paintEvent(self, event):
        if self._frame is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._frame)
        self.particles.draw(painter)

    def current_pixmap(self, size=None):
        target = size or self.size_px
        dpr = max(1.0, float(self.devicePixelRatioF()))
        pm = self._compose(max(1, int(round(target * dpr))))
        pm.setDevicePixelRatio(dpr)
        return pm

    def set_always_on_top(self, enabled):
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) == bool(enabled):
            return
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, bool(enabled))
        if visible:
            self.show()

    def enter_talk(self):
        self.unperch()
        self._walk_target = None
        self.sm.on_double_click()

    def finish_talk(self):
        self.sm.finish_talk()

    def walk_to_cursor(self):
        self.unperch()
        cursor = self.cursor().pos()
        self._walk_target = cursor.x() - self.size_px // 2

    def dance(self):
        self.unperch()
        self._walk_target = None
        self._dance_left = 3
        self.sm.force(PetState.HOP)

    def perch(self, hwnd):
        if not hwnd:
            return False
        self._walk_target = None
        self._perch_hwnd = int(hwnd)
        return self._follow_perch()

    def unperch(self):
        self._perch_hwnd = 0

    def _walk_step(self, dt, ctx):
        if self._walk_target is None:
            return None
        x = self.pos().x()
        self._walk_target = max(ctx.screen.left(), min(
            self._walk_target, ctx.screen.right() - self.width() + 1))
        dx = self._walk_target - x
        if abs(dx) < 8:
            self._walk_target = None
            self.sm.force(PetState.IDLE)
            return QPointF(0.0, 0.0)
        if self.sm.state != PetState.WALK:
            self.sm.force(PetState.WALK)
        self.sm.facing = 1 if dx > 0 else -1
        speed = self.sm.walk_speed * self.sm.scale
        step = max(-speed * dt, min(speed * dt, dx))
        return QPointF(step, 0.0)

    def _follow_perch(self):
        from . import win32util

        if not win32util.is_window_visible(self._perch_hwnd):
            self._perch_hwnd = 0
            return False
        box = win32util.window_rect(self._perch_hwnd)
        if box is None:
            self._perch_hwnd = 0
            return False
        left, top, right, _bottom = box
        x = int((left + right) / 2 - self.size_px / 2)
        y = int(top - self.size_px + 18)
        self.move(self._clamp(QPoint(x, y), self.screen().availableGeometry()))
        if self.sm.state not in (PetState.IDLE, PetState.SLEEP, PetState.PET, PetState.REACT):
            self.sm.force(PetState.IDLE)
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._motion_remainder = QPointF()
            self._walk_target = None
            self._moved = False
            self._drag_samples.clear()
            self._drag_samples.append((time.monotonic(), event.globalPosition().toPoint()))
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.unperch()
            self.sm.on_press()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            global_pos = event.globalPosition().toPoint()
            new_pos = global_pos - self._drag_offset
            if (new_pos - self.pos()).manhattanLength() > 3:
                self._moved = True
            self._drag_samples.append((time.monotonic(), global_pos))
            self.move(self._clamp(new_pos, self.screen().availableGeometry()))

    def _release_velocity(self):
        if len(self._drag_samples) < 2:
            return QPointF(0.0, 0.0)
        t_now, p_now = self._drag_samples[-1]
        t0, p0 = self._drag_samples[0]
        for t, p in self._drag_samples:
            if t_now - t <= 0.12:
                t0, p0 = t, p
                break
        dt = t_now - t0
        if dt <= 0.001:
            return QPointF(0.0, 0.0)
        return QPointF((p_now.x() - p0.x()) / dt, (p_now.y() - p0.y()) / dt)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            if self._moved:
                self._drag_samples.append((time.monotonic(), event.globalPosition().toPoint()))
                self.sm.on_release(self._release_velocity())
            else:
                local = event.position()
                head = local.y() < self.size_px * 0.42
                self.sm.on_click(pet=head)
                cy = self.size_px * (0.22 if head else 0.32)
                self.particles.hearts(self.size_px * 0.5, cy, count=8 if head else 5)
                self.petted.emit(head)
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.sm.on_double_click()
            self.chat_requested.emit()

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(event.globalPos())

    def enterEvent(self, event):
        self.sm.on_hover(True)
        super().enterEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self._first_file(event) is not None:
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self._first_file(event)
        if path is None:
            return
        event.acceptProposedAction()
        from .assets import is_image
        if is_image(path):
            self.image_dropped.emit(path)
        else:
            self.file_dropped.emit(path)

    @staticmethod
    def _first_file(event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                return path
        return None
