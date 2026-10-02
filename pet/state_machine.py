import math
import random
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QPoint, QPointF, QRect, QSize


class PetState(Enum):
    IDLE = auto()
    WALK = auto()
    SLEEP = auto()
    DRAG = auto()
    FALL = auto()
    REACT = auto()
    TALK = auto()
    HOP = auto()
    THROWN = auto()
    PET = auto()
    DIZZY = auto()


@dataclass
class Context:
    screen: QRect
    pos: QPoint
    size: QSize
    cursor: QPoint
    wander: bool = True
    follow_cursor: bool = False
    sleep_enabled: bool = True
    bottom_margin: int = 0


class StateMachine:
    def __init__(self, walk_speed=60.0, scale=1.0, wander=True,
                 follow_cursor=False, sleep_enabled=True, rng=None):
        self.rng = rng or random.Random()
        self.walk_speed = walk_speed
        self.scale = scale
        self.wander = wander
        self.follow_cursor = follow_cursor
        self.sleep_enabled = sleep_enabled

        self.state = PetState.IDLE
        self.t = 0.0
        self.duration = 0.0
        self.facing = 1
        self.look = QPointF(0.0, 0.0)
        self.vy = 0.0
        self.vx = 0.0
        self.idle_streak = 0
        self.just_landed = False
        self.land_impact = 0.0
        self._enter(PetState.IDLE)

    def update_options(self, wander=None, follow_cursor=None, sleep_enabled=None,
                       walk_speed=None, scale=None):
        if wander is not None:
            self.wander = wander
        if follow_cursor is not None:
            self.follow_cursor = follow_cursor
        if sleep_enabled is not None:
            self.sleep_enabled = sleep_enabled
        if walk_speed is not None:
            self.walk_speed = walk_speed
        if scale is not None:
            self.scale = scale

    @property
    def gravity(self):
        return 2100.0 * self.scale

    def _enter(self, state):
        self.state = state
        self.t = 0.0
        rng = self.rng
        if state == PetState.IDLE:
            self.duration = rng.uniform(1.5, 4.0)
        elif state == PetState.WALK:
            self.duration = rng.uniform(3.0, 8.0)
            if rng.random() < 0.5:
                self.facing = -self.facing
        elif state == PetState.SLEEP:
            self.duration = rng.uniform(8.0, 20.0)
        elif state == PetState.REACT:
            self.duration = 0.9
        elif state == PetState.FALL:
            self.vy = 0.0
            self.vx = 0.0
        elif state == PetState.HOP:
            self.vy = -460.0 * self.scale
            self.vx = self.facing * rng.uniform(40.0, 130.0) * self.scale
        elif state == PetState.PET:
            self.duration = rng.uniform(1.0, 1.6)
        elif state == PetState.DIZZY:
            self.duration = 1.6
        else:
            self.duration = float("inf")

    def force(self, state):
        if self.state != state:
            self._enter(state)

    def on_press(self):
        self.idle_streak = 0
        self.vx = 0.0
        self.vy = 0.0
        self._enter(PetState.DRAG)

    def on_release(self, velocity=None):
        if self.state != PetState.DRAG:
            return
        speed = 0.0
        if velocity is not None:
            speed = math.hypot(velocity.x(), velocity.y())
        if speed >= 260.0:
            self.vx = max(-1500.0, min(1500.0, velocity.x()))
            self.vy = max(-1500.0, min(1500.0, velocity.y()))
            self._enter(PetState.THROWN)
        else:
            self._enter(PetState.FALL)

    def on_click(self, pet=False):
        if self.state in (PetState.DRAG, PetState.THROWN):
            return
        self.idle_streak = 0
        self.vx = 0.0
        self.vy = 0.0
        if pet:
            self._enter(PetState.PET)
        elif self.rng.random() < 0.5:
            self._enter(PetState.PET)
        else:
            self._enter(PetState.REACT)

    def on_double_click(self):
        self.idle_streak = 0
        self.vx = 0.0
        self.vy = 0.0
        self._enter(PetState.TALK)

    def on_startle(self, direction):
        if self.state in (PetState.DRAG, PetState.THROWN, PetState.HOP):
            return
        self.idle_streak = 0
        self.facing = 1 if direction >= 0 else -1
        self._enter(PetState.HOP)
        self.vx = (1 if direction >= 0 else -1) * 200.0 * self.scale
        self.vy = -520.0 * self.scale

    def finish_talk(self):
        if self.state == PetState.TALK:
            self._enter(PetState.IDLE)

    def on_hover(self, inside):
        if inside and self.state in (PetState.SLEEP, PetState.IDLE):
            self.idle_streak = 0
            self._enter(PetState.REACT)

    def tick(self, dt, ctx):
        self.t += dt
        self.just_landed = False
        self.land_impact = 0.0
        move = QPointF(0.0, 0.0)
        state = self.state
        self._update_look(ctx)

        if state == PetState.IDLE:
            if self.t >= self.duration:
                self._choose_next_idle()
        elif state == PetState.WALK:
            speed = self.walk_speed * self.scale
            move = QPointF(self.facing * speed * dt, 0.0)
            if self._at_horizontal_edge(ctx, move.x()):
                self.facing = -self.facing
                move = QPointF(self.facing * speed * dt, 0.0)
            if self.t >= self.duration:
                self._enter(PetState.IDLE)
        elif state == PetState.SLEEP:
            if self.t >= self.duration:
                self._enter(PetState.IDLE)
        elif state == PetState.REACT:
            if self.t >= self.duration:
                self._enter(PetState.IDLE)
        elif state == PetState.PET:
            if self.t >= self.duration:
                self._enter(PetState.IDLE)
        elif state == PetState.DIZZY:
            if self.t >= self.duration:
                self._enter(PetState.IDLE)
        elif state == PetState.FALL:
            self.vy += self.gravity * dt
            move = QPointF(0.0, self.vy * dt)
            bottom = self._bottom(ctx)
            if ctx.pos.y() + move.y() >= bottom:
                move.setY(bottom - ctx.pos.y())
                self._land(abs(self.vy))
        elif state in (PetState.HOP, PetState.THROWN):
            move = self._ballistic(dt, ctx)
        elif state in (PetState.DRAG, PetState.TALK):
            move = QPointF(0.0, 0.0)

        return move

    def _ballistic(self, dt, ctx):
        self.vy += self.gravity * dt
        if self.state == PetState.THROWN:
            self.vx *= (1.0 - 0.35 * dt)

        planned_x = ctx.pos.x() + self.vx * dt
        planned_y = ctx.pos.y() + self.vy * dt

        left = ctx.screen.left()
        right = ctx.screen.right() - ctx.size.width() + 1
        top = ctx.screen.top()
        bottom = self._bottom(ctx)

        if planned_x < left:
            planned_x = left
            self.vx = abs(self.vx) * 0.55
        elif planned_x > right:
            planned_x = right
            self.vx = -abs(self.vx) * 0.55

        if planned_y < top:
            planned_y = top
            self.vy = abs(self.vy) * 0.4

        if planned_y >= bottom:
            planned_y = bottom
            impact = abs(self.vy)
            if impact > 950.0:
                self._land(impact)
                self._enter(PetState.DIZZY)
            elif impact > 130.0:
                self.vy = -impact * 0.42
                self.vx *= 0.72
                self.just_landed = True
                self.land_impact = impact
            else:
                self._land(impact)
                self._enter(PetState.IDLE)

        return QPointF(planned_x - ctx.pos.x(), planned_y - ctx.pos.y())

    def _land(self, impact):
        self.vy = 0.0
        self.vx = 0.0
        if impact > 0:
            self.just_landed = True
            self.land_impact = impact

    def _bottom(self, ctx):
        return (ctx.screen.bottom() - ctx.size.height() + 1
                - int(getattr(ctx, "bottom_margin", 0)))

    def _choose_next_idle(self):
        self.idle_streak += 1
        r = self.rng.random()
        if self.sleep_enabled and self.idle_streak >= 3 and r < 0.40:
            self.idle_streak = 0
            self._enter(PetState.SLEEP)
        elif self.follow_cursor:
            self.facing = 1 if self.look.x() >= 0 else -1
            self._enter(PetState.WALK)
        elif r < 0.12:
            self._enter(PetState.HOP)
        elif r < 0.22:
            self._enter(PetState.REACT)
        elif self.wander and r < 0.72:
            self._enter(PetState.WALK)
        else:
            self._enter(PetState.IDLE)

    def _update_look(self, ctx):
        cx = ctx.pos.x() + ctx.size.width() / 2.0
        cy = ctx.pos.y() + ctx.size.height() * 0.45
        dx = ctx.cursor.x() - cx
        dy = ctx.cursor.y() - cy
        length = max((dx * dx + dy * dy) ** 0.5, 1.0)
        self.look = QPointF(dx / length, dy / length)
        if self.state not in (PetState.WALK, PetState.THROWN, PetState.HOP):
            if abs(dx) > ctx.size.width() * 0.7:
                self.facing = 1 if dx > 0 else -1

    def _at_horizontal_edge(self, ctx, dx):
        left = ctx.screen.left()
        right = ctx.screen.right() - ctx.size.width() + 1
        if dx < 0 and ctx.pos.x() <= left:
            return True
        if dx > 0 and ctx.pos.x() >= right:
            return True
        return False
