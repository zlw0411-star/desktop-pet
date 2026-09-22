import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter

HEART_COLOR = QColor(255, 107, 138)
STAR_COLOR = QColor(255, 213, 74)
SPARKLE_COLOR = QColor(255, 246, 200)
SWEAT_COLOR = QColor(120, 190, 255)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "kind",
                 "size", "spin", "angle", "gravity")

    def __init__(self, x, y, vx, vy, life, kind, size, gravity):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.kind = kind
        self.size = size
        self.spin = random.uniform(-220.0, 220.0)
        self.angle = random.uniform(0.0, 360.0)
        self.gravity = gravity

    def update(self, dt):
        self.life -= dt
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        return self.life > 0


class ParticleField:
    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()

    @property
    def active(self):
        return bool(self.items)

    def _spawn(self, kind, x, y, vx, vy, life, size, gravity):
        self.items.append(Particle(x, y, vx, vy, life, kind, size, gravity))

    def hearts(self, x, y, count=5, spread=32.0):
        for _ in range(count):
            self._spawn("heart",
                        x + random.uniform(-spread * 0.5, spread * 0.5),
                        y + random.uniform(-6, 6),
                        random.uniform(-24, 24), random.uniform(-95, -55),
                        random.uniform(0.9, 1.4), random.uniform(13, 20), 12.0)

    def stars(self, x, y, count=6):
        for _ in range(count):
            ang = random.uniform(0.0, math.tau)
            speed = random.uniform(70, 160)
            self._spawn("star", x, y,
                        math.cos(ang) * speed, math.sin(ang) * speed - 40,
                        random.uniform(0.5, 0.9), random.uniform(10, 16), 260.0)

    def sparkles(self, x, y, count=2):
        for _ in range(count):
            self._spawn("sparkle",
                        x + random.uniform(-40, 40), y + random.uniform(-50, 10),
                        random.uniform(-12, 12), random.uniform(-40, -18),
                        random.uniform(0.6, 1.1), random.uniform(7, 12), 0.0)

    def sweat(self, x, y, count=3):
        for _ in range(count):
            self._spawn("sweat",
                        x + random.uniform(-6, 6), y,
                        random.uniform(-40, 40) + 40, random.uniform(-120, -70),
                        random.uniform(0.6, 1.0), random.uniform(6, 9), 300.0)

    def update(self, dt):
        self.items = [p for p in self.items if p.update(dt)]

    def draw(self, painter, scale=1.0):
        if not self.items:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        for p in self.items:
            alpha = max(0.0, min(1.0, p.life / p.max_life))
            fade = int(255 * (alpha if alpha < 0.6 else 1.0))
            painter.save()
            painter.translate(p.x * scale, p.y * scale)
            painter.rotate(p.angle)
            size = p.size * scale
            if p.kind == "heart":
                color = QColor(HEART_COLOR)
                color.setAlpha(fade)
                painter.setPen(color)
                painter.setBrush(color)
                painter.setFont(QFont("Segoe UI Symbol", int(size)))
                painter.drawText(int(-size * 0.6), int(size * 0.35), "♥")
            elif p.kind == "star":
                color = QColor(STAR_COLOR)
                color.setAlpha(fade)
                painter.setPen(color)
                painter.setBrush(color)
                painter.setFont(QFont("Segoe UI Symbol", int(size)))
                painter.drawText(int(-size * 0.55), int(size * 0.4), "★")
            elif p.kind == "sparkle":
                color = QColor(SPARKLE_COLOR)
                color.setAlpha(fade)
                painter.setPen(color)
                painter.setBrush(color)
                painter.setFont(QFont("Segoe UI Symbol", int(size)))
                painter.drawText(int(-size * 0.5), int(size * 0.4), "✦")
            else:
                color = QColor(SWEAT_COLOR)
                color.setAlpha(fade)
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(0, 0), size * 0.4, size * 0.55)
            painter.restore()
