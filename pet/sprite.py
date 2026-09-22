import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QMovie,
                           QPainter, QPixmap, QRadialGradient)

from .state_machine import PetState


class ImageSprite:
    """用用户提供的图片/GIF 作为宠物形象。"""

    def __init__(self, path):
        self.path = path or ""
        self.valid = False
        self._movie = None
        self._pixmap = None
        self._cache_sig = None
        self._scaled = None
        self._glow = None
        if not self.path or not os.path.exists(self.path):
            return
        if self.path.lower().endswith(".gif"):
            movie = QMovie(self.path)
            if movie.isValid():
                self._movie = movie
                movie.start()
                if movie.currentPixmap().isNull():
                    movie.jumpToFrame(0)
                self.valid = True
            return
        pm = QPixmap(self.path)
        if not pm.isNull():
            self._pixmap = pm
            self.valid = True

    def _base(self):
        if self._movie is not None:
            pm = self._movie.currentPixmap()
            return None if pm.isNull() else pm
        return self._pixmap

    def stop(self):
        if self._movie is not None:
            self._movie.stop()

    def _prepare(self, base, size):
        src_w = max(base.width(), 1)
        src_h = max(base.height(), 1)
        factor = min(size / src_w, size / src_h) * 0.94
        draw_w = max(1, int(src_w * factor))
        draw_h = max(1, int(src_h * factor))

        sig = (size, id(base))
        if self._cache_sig == sig and self._scaled is not None:
            return draw_w, draw_h

        scaled = base.scaled(draw_w, draw_h, Qt.IgnoreAspectRatio,
                             Qt.SmoothTransformation)
        glow = QPixmap(scaled.size())
        glow.fill(Qt.transparent)
        gp = QPainter(glow)
        gp.drawPixmap(0, 0, scaled)
        gp.setCompositionMode(QPainter.CompositionMode_SourceIn)
        gp.fillRect(glow.rect(), QColor(255, 255, 255, 165))
        gp.end()

        self._scaled = scaled
        self._glow = glow
        self._cache_sig = sig
        return draw_w, draw_h

    def render(self, size, state, t, facing=1, look=None, glow=True):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        base = self._base()
        if base is None:
            return pm

        if state in (PetState.DRAG, PetState.FALL, PetState.THROWN, PetState.HOP):
            bob = 0.0
        else:
            bob = math.sin(t * 2.0) * size * 0.014
        if state == PetState.SLEEP:
            bob += size * 0.012

        draw_w, draw_h = self._prepare(base, size)
        scaled = self._scaled
        half_w = draw_w / 2.0
        half_h = draw_h / 2.0

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if state not in (PetState.DRAG, PetState.FALL):
            shadow = QRadialGradient(QPointF(size / 2.0, size * 0.965 + bob * 0.4),
                                     max(size * 0.30, 1.0))
            shadow.setColorAt(0.0, QColor(0, 0, 0, 80))
            shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(shadow))
            painter.drawEllipse(QPointF(size / 2.0, size * 0.965 + bob * 0.4),
                                size * 0.30, size * 0.05)

        painter.translate(size / 2.0, size * 0.54 + bob)
        sway = math.sin(t * 1.6) * (0.0 if state == PetState.SLEEP else 0.012)
        painter.rotate(sway * 180.0 / math.pi)

        if glow and self._glow is not None:
            radius = max(2.0, size * 0.016)
            for index in range(12):
                angle = math.radians(index * 30)
                painter.drawPixmap(
                    QPointF(-half_w + math.cos(angle) * radius,
                            -half_h + math.sin(angle) * radius),
                    self._glow)

        painter.drawPixmap(QRectF(-half_w, -half_h, draw_w, draw_h),
                           scaled, QRectF(scaled.rect()))
        painter.resetTransform()

        fade_top = size * 0.78
        fade = QLinearGradient(0.0, fade_top, 0.0, size)
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fade))
        painter.drawRect(QRectF(0.0, fade_top, size, size - fade_top))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        if state == PetState.SLEEP:
            self._draw_zzz(painter, size, bob)
        painter.end()
        return pm

    @staticmethod
    def _draw_zzz(painter, size, bob):
        big = QFont("Segoe UI", int(size * 0.16), QFont.Bold)
        small = QFont("Segoe UI", int(size * 0.11), QFont.Bold)
        painter.setFont(big)
        x, y = int(size * 0.66), int(size * 0.30 + bob)
        painter.setPen(QColor(255, 255, 255, 210))
        painter.drawText(x + 1, y + 1, "z")
        painter.setPen(QColor(70, 90, 130, 235))
        painter.drawText(x, y, "z")
        painter.setFont(small)
        x2, y2 = int(size * 0.78), int(size * 0.17 + bob)
        painter.setPen(QColor(255, 255, 255, 210))
        painter.drawText(x2 + 1, y2 + 1, "z")
        painter.setPen(QColor(70, 90, 130, 235))
        painter.drawText(x2, y2, "z")
